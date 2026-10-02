use core::ffi::{c_char, c_int, c_void};
use core::mem::MaybeUninit;
use core::ptr;
use core::slice;

use base64::engine::general_purpose::{
    GeneralPurpose, GeneralPurposeConfig, STANDARD, STANDARD_NO_PAD, URL_SAFE,
    URL_SAFE_NO_PAD,
};
use base64::engine::DecodePaddingMode;
use base64::{alphabet, DecodeSliceError, Engine};
use crate::abi::*;
use data_encoding::{
    Encoding, BASE32, BASE32HEX, BASE32HEX_NOPAD, BASE32_NOPAD, HEXUPPER,
};

const PYBUF_SIMPLE: c_int = 0;

const STANDARD_COMPAT: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new().with_decode_allow_trailing_bits(true),
);
const STANDARD_NO_PAD_COMPAT: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new()
        .with_decode_allow_trailing_bits(true)
        .with_decode_padding_mode(DecodePaddingMode::RequireNone),
);
static HEXUPPER_ENCODING: Encoding = HEXUPPER;
static BASE32_ENCODING: Encoding = BASE32;
static BASE32_NOPAD_ENCODING: Encoding = BASE32_NOPAD;
static BASE32HEX_ENCODING: Encoding = BASE32HEX;
static BASE32HEX_NOPAD_ENCODING: Encoding = BASE32HEX_NOPAD;

#[inline]
fn encoded_output_len(input_len: usize, padded: bool) -> Option<usize> {
    let full_groups = (input_len / 3).checked_mul(4)?;
    match (input_len % 3, padded) {
        (0, _) => Some(full_groups),
        (_, true) => full_groups.checked_add(4),
        (remainder, false) => full_groups.checked_add(remainder + 1),
    }
}

fn encode_with<E: Engine>(source: &PyObject, engine: &E, padded: bool) -> Result<*mut PyObject, ()> {
    let buffer = BorrowedBuffer::from_object(source)?;
    let view_len = buffer.len();
    if view_len < 0 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"base64 encode argument has negative length".as_ptr(),
            );
        }
        return Err(());
    }

    let input_len = view_len as usize;
    let input = buffer.as_slice().unwrap_or(&[]);
    let Some(output_len) = encoded_output_len(input_len, padded) else {
        unsafe {
            PyErr_NoMemory();
        }
        return Err(());
    };
    if output_len > isize::MAX as usize {
        unsafe {
            PyErr_NoMemory();
        }
        return Err(());
    }

    let result = unsafe { PyBytes_FromStringAndSize(ptr::null(), output_len as Py_ssize_t) };
    if result.is_null() {
        return Err(());
    }
    let dest_ptr = unsafe { PyBytes_AsString(result) };
    if dest_ptr.is_null() {
        unsafe {
            Py_DecRef(result);
        }
        return Err(());
    }
    let dest = unsafe { slice::from_raw_parts_mut(dest_ptr.cast::<u8>(), output_len) };
    match engine.encode_slice(input, dest) {
        Ok(written) if written == output_len => Ok(result),
        _ => {
            unsafe {
                Py_DecRef(result);
                PyErr_NoMemory();
            }
            Err(())
        }
    }
}

// Snapshot ownership is fallible and stays in CPython's memory domain.
// Base85 releases the exporter before allocating its result, as before.
struct Snapshot { ptr: *mut u8, len: usize }
impl Snapshot {
    fn allocate(len: usize) -> Result<Self, ()> {
        let ptr = if len == 0 { core::ptr::NonNull::<u8>::dangling().as_ptr() }
                  else { unsafe { PyMem_Malloc(len) }.cast::<u8>() };
        if ptr.is_null() { unsafe { PyErr_NoMemory() }; return Err(()); }
        Ok(Self { ptr, len })
    }
    fn copy(input: &[u8]) -> Result<Self, ()> {
        let result = Self::allocate(input.len())?;
        unsafe { ptr::copy_nonoverlapping(input.as_ptr(), result.ptr, input.len()); }
        Ok(result)
    }
    fn filtered(input: &[u8], keep: impl Fn(u8) -> bool) -> Result<Self, ()> {
        let len = input.iter().filter(|&&byte| keep(byte)).count();
        let result = Self::allocate(len)?;
        let mut position = 0;
        for &byte in input {
            if keep(byte) { unsafe { *result.ptr.add(position) = byte; } position += 1; }
        }
        Ok(result)
    }
    fn as_slice(&self) -> &[u8] { unsafe { slice::from_raw_parts(self.ptr, self.len) } }
}
impl Drop for Snapshot {
    fn drop(&mut self) { if self.len != 0 { unsafe { PyMem_Free(self.ptr.cast()); } } }
}
fn borrowed_bytes(source: &PyObject, operation: &'static [u8]) -> Result<(BorrowedBuffer, Snapshot), ()> {
    let buffer = BorrowedBuffer::from_object(source)?;
    if buffer.len() < 0 {
        unsafe { PyErr_SetString(PyExc_TypeError, operation.as_ptr().cast()) };
        return Err(());
    }
    let input = Snapshot::copy(buffer.as_slice().unwrap_or(&[]))?;
    Ok((buffer, input))
}

unsafe fn none_ref() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

/// Allocate an uninitialized bytes object of `len` bytes.
unsafe fn new_bytes(len: usize) -> Result<(*mut PyObject, *mut u8), ()> {
    if len > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    let result = unsafe { PyBytes_FromStringAndSize(ptr::null(), len as Py_ssize_t) };
    if result.is_null() {
        return Err(());
    }
    Ok((result, unsafe { PyBytes_AsString(result) }.cast::<u8>()))
}

/// Shrink a freshly built bytes object to `len` bytes.
unsafe fn shrink_bytes(result: *mut PyObject, len: usize) -> *mut PyObject {
    let mut result = result;
    if unsafe { _PyBytes_Resize(&mut result, len as Py_ssize_t) } != 0 {
        return ptr::null_mut();
    }
    result
}

fn encode_data_encoding(
    source: &PyObject,
    encoding: &'static Encoding,
) -> *mut PyObject {
    let buffer = match BorrowedBuffer::from_object(source) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let Some(input) = buffer.as_slice() else {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"base encoding argument has negative length".as_ptr())
        };
        return ptr::null_mut();
    };
    let output_len = if ptr::eq(encoding, &HEXUPPER_ENCODING) {
        input.len().checked_mul(2)
    } else {
        let padded = ptr::eq(encoding, &BASE32_ENCODING)
            || ptr::eq(encoding, &BASE32HEX_ENCODING);
        let remainder = input.len() % 5;
        let tail = if remainder == 0 { 0 } else if padded { 8 }
                   else { (remainder * 8 + 4) / 5 };
        (input.len() / 5).checked_mul(8).and_then(|len| len.checked_add(tail))
    };
    let Some(output_len) = output_len else {
        unsafe { PyErr_NoMemory() }; return ptr::null_mut();
    };
    let Ok((result, dest_ptr)) = (unsafe { new_bytes(output_len) }) else {
        return ptr::null_mut();
    };
    let dest = unsafe { slice::from_raw_parts_mut(dest_ptr, output_len) };
    encoding.encode_mut(input, dest);
    result
}

fn decode_data_encoding(
    source: &PyObject,
    encoding: &'static Encoding,
) -> *mut PyObject {
    let buffer = match BorrowedBuffer::from_object(source) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let Some(input) = buffer.as_slice() else {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"base decoding argument has negative length".as_ptr())
        };
        return ptr::null_mut();
    };
    let Ok(capacity) = encoding.decode_len(input.len()) else {
        return unsafe { none_ref() };
    };
    let Ok((result, dest_ptr)) = (unsafe { new_bytes(capacity) }) else {
        return ptr::null_mut();
    };
    let dest = unsafe { slice::from_raw_parts_mut(dest_ptr, capacity) };
    match encoding.decode_mut(input, dest) {
        Ok(written) if written == capacity => result,
        Ok(written) => unsafe { shrink_bytes(result, written) },
        Err(_) => {
            unsafe { Py_DecRef(result) };
            unsafe { none_ref() }
        }
    }
}

const B85_ALPHABET: &[u8; 85] = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
const Z85_ALPHABET: &[u8; 85] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#";

fn encode_base85(input: &[u8], padded: bool, alphabet: &[u8; 85]) -> *mut PyObject {
    let remainder = input.len() % 4;
    let tail = if remainder == 0 { 0 } else if padded { 5 } else { remainder + 1 };
    let Some(len) = (input.len() / 4).checked_mul(5).and_then(|n| n.checked_add(tail)) else {
        unsafe { PyErr_NoMemory() }; return ptr::null_mut();
    };
    let Ok((result, dest)) = (unsafe { new_bytes(len) }) else { return ptr::null_mut(); };
    let mut position = 0;
    for chunk in input.chunks(4) {
        let mut bytes = [0; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0; 5];
        for slot in encoded.iter_mut().rev() {
            *slot = alphabet[(value % 85) as usize]; value /= 85;
        }
        let count = if chunk.len() == 4 || padded { 5 } else { chunk.len() + 1 };
        unsafe { ptr::copy_nonoverlapping(encoded.as_ptr(), dest.add(position), count); }
        position += count;
    }
    result
}

fn decode_base85(input: &[u8], alphabet: &[u8; 85]) -> *mut PyObject {
    let remainder = input.len() % 5;
    if remainder == 1 { return unsafe { none_ref() }; }
    let len = input.len() / 5 * 4 + remainder.saturating_sub(1);
    let Ok((result, dest)) = (unsafe { new_bytes(len) }) else { return ptr::null_mut(); };
    let mut position = 0;
    for chunk in input.chunks(5) {
        let mut value = 0u64;
        for &byte in chunk {
            let Some(digit) = alphabet.iter().position(|candidate| *candidate == byte) else {
                unsafe { Py_DecRef(result) }; return unsafe { none_ref() };
            };
            value = value * 85 + digit as u64;
        }
        for _ in chunk.len()..5 { value = value * 85 + 84; }
        if value > u32::MAX as u64 {
            unsafe { Py_DecRef(result) }; return unsafe { none_ref() };
        }
        let bytes = (value as u32).to_be_bytes();
        let count = if chunk.len() == 5 { 4 } else { chunk.len() - 1 };
        unsafe { ptr::copy_nonoverlapping(bytes.as_ptr(), dest.add(position), count); }
        position += count;
    }
    result
}

fn encode_ascii85(input: &[u8]) -> *mut PyObject {
    let mut len = 0usize;
    for chunk in input.chunks(4) {
        let count = if chunk == [0, 0, 0, 0] { 1 } else { chunk.len() + 1 };
        let Some(next) = len.checked_add(count) else {
            unsafe { PyErr_NoMemory() }; return ptr::null_mut();
        };
        len = next;
    }
    let Ok((result, dest)) = (unsafe { new_bytes(len) }) else { return ptr::null_mut(); };
    let mut position = 0;
    for chunk in input.chunks(4) {
        if chunk == [0, 0, 0, 0] {
            unsafe { *dest.add(position) = b'z'; } position += 1; continue;
        }
        let mut bytes = [0; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0; 5];
        for slot in encoded.iter_mut().rev() { *slot = b'!' + (value % 85) as u8; value /= 85; }
        let count = chunk.len() + 1;
        unsafe { ptr::copy_nonoverlapping(encoded.as_ptr(), dest.add(position), count); }
        position += count;
    }
    result
}

// The first pass validates and counts, the second writes exactly that many
// bytes. This handles compressed zero groups without an oversized allocation.
fn ascii85_pass(input: &[u8], mut emit: impl FnMut(&[u8])) -> Option<usize> {
    let mut group = [84u8; 5];
    let mut count = 0usize;
    let mut written = 0usize;
    for &byte in input {
        if matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b) { continue; }
        if byte == b'z' {
            if count != 0 { return None; }
            written = written.checked_add(4)?; emit(&[0, 0, 0, 0]); continue;
        }
        if !(b'!'..=b'u').contains(&byte) { return None; }
        group[count] = byte - b'!'; count += 1;
        if count == 5 {
            let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
            if value > u32::MAX as u64 { return None; }
            written = written.checked_add(4)?; emit(&(value as u32).to_be_bytes());
            group = [84; 5]; count = 0;
        }
    }
    if count == 1 { return None; }
    if count > 1 {
        let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
        if value > u32::MAX as u64 { return None; }
        written = written.checked_add(count - 1)?;
        emit(&(value as u32).to_be_bytes()[..count - 1]);
    }
    Some(written)
}
fn decode_ascii85(input: &[u8]) -> *mut PyObject {
    let Some(len) = ascii85_pass(input, |_| {}) else { return unsafe { none_ref() }; };
    let Ok((result, dest)) = (unsafe { new_bytes(len) }) else { return ptr::null_mut(); };
    let mut position = 0;
    let written = ascii85_pass(input, |bytes| {
        unsafe { ptr::copy_nonoverlapping(bytes.as_ptr(), dest.add(position), bytes.len()); }
        position += bytes.len();
    });
    if written != Some(len) {
        unsafe { Py_DecRef(result) }; return unsafe { none_ref() };
    }
    result
}

unsafe fn encode_one_argument(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    name: *const c_char,
    encoding: &'static Encoding,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, name) };
        return ptr::null_mut();
    }
    encode_data_encoding(unsafe { &**args }, encoding)
}

unsafe fn decode_one_argument(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    name: *const c_char,
    encoding: &'static Encoding,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, name) };
        return ptr::null_mut();
    }
    decode_data_encoding(unsafe { &**args }, encoding)
}

pub unsafe extern "C" fn b16encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { encode_one_argument(args, nargs, c"b16encode() takes exactly one argument".as_ptr(), &HEXUPPER_ENCODING) }
}

pub unsafe extern "C" fn b16decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { decode_one_argument(args, nargs, c"b16decode() takes exactly one argument".as_ptr(), &HEXUPPER_ENCODING) }
}

unsafe fn b32_encode_dispatch(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    hex: bool,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"Base32 encode requires data and padded".as_ptr()) };
        return ptr::null_mut();
    }
    let padded = match truthy(unsafe { *args.add(1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let encoding = match (hex, padded) {
        (false, true) => &BASE32_ENCODING,
        (false, false) => &BASE32_NOPAD_ENCODING,
        (true, true) => &BASE32HEX_ENCODING,
        (true, false) => &BASE32HEX_NOPAD_ENCODING,
    };
    encode_data_encoding(unsafe { &**args }, encoding)
}

unsafe fn b32_decode_dispatch(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    hex: bool,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"Base32 decode requires data and padded".as_ptr()) };
        return ptr::null_mut();
    }
    let padded = match truthy(unsafe { *args.add(1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let encoding = match (hex, padded) {
        (false, true) => &BASE32_ENCODING,
        (false, false) => &BASE32_NOPAD_ENCODING,
        (true, true) => &BASE32HEX_ENCODING,
        (true, false) => &BASE32HEX_NOPAD_ENCODING,
    };
    decode_data_encoding(unsafe { &**args }, encoding)
}

pub unsafe extern "C" fn b32encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { b32_encode_dispatch(args, nargs, false) }
}

pub unsafe extern "C" fn b32decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { b32_decode_dispatch(args, nargs, false) }
}

pub unsafe extern "C" fn b32hexencode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { b32_encode_dispatch(args, nargs, true) }
}

pub unsafe extern "C" fn b32hexdecode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { b32_decode_dispatch(args, nargs, true) }
}

unsafe fn encode_85(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    alphabet: &'static [u8; 85],
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"Base85 encode requires data and pad".as_ptr()) };
        return ptr::null_mut();
    }
    let padded = match truthy(unsafe { *args.add(1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let (buffer, input) = match borrowed_bytes(unsafe { &**args }, b"base85 encode argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    encode_base85(input.as_slice(), padded, alphabet)
}

unsafe fn decode_85(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    alphabet: &'static [u8; 85],
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"Base85 decode requires one argument".as_ptr()) };
        return ptr::null_mut();
    }
    let (buffer, input) = match borrowed_bytes(unsafe { &**args }, b"base85 decode argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    decode_base85(input.as_slice(), alphabet)
}

pub unsafe extern "C" fn b85encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { encode_85(args, nargs, B85_ALPHABET) }
}

pub unsafe extern "C" fn b85decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { decode_85(args, nargs, B85_ALPHABET) }
}

pub unsafe extern "C" fn z85encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { encode_85(args, nargs, Z85_ALPHABET) }
}

pub unsafe extern "C" fn z85decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { decode_85(args, nargs, Z85_ALPHABET) }
}

pub unsafe extern "C" fn a85encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"a85encode() takes exactly one argument".as_ptr()) };
        return ptr::null_mut();
    }
    let (buffer, input) = match borrowed_bytes(unsafe { &**args }, b"Ascii85 encode argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    encode_ascii85(input.as_slice())
}

pub unsafe extern "C" fn a85decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"a85decode() takes exactly one argument".as_ptr()) };
        return ptr::null_mut();
    }
    let (buffer, input) = match borrowed_bytes(unsafe { &**args }, b"Ascii85 decode argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    decode_ascii85(input.as_slice())
}

pub unsafe extern "C" fn standard_b64encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 && nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"standard_b64encode() takes one or two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = unsafe { &**args };
    let padded = if nargs == 1 {
        true
    } else {
        match truthy(unsafe { *args.add(1) }) {
            Ok(value) => value,
            Err(()) => return ptr::null_mut(),
        }
    };
    let engine = if padded { &STANDARD } else { &STANDARD_NO_PAD };
    match encode_with(source, engine, padded) {
        Ok(result) => result,
        Err(()) => ptr::null_mut(),
    }
}

pub unsafe extern "C" fn urlsafe_b64encode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 && nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"urlsafe_b64encode() takes one or two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = unsafe { &**args };
    let padded = if nargs == 1 {
        true
    } else {
        match truthy(unsafe { *args.add(1) }) {
            Ok(value) => value,
            Err(()) => return ptr::null_mut(),
        }
    };
    let engine = if padded { &URL_SAFE } else { &URL_SAFE_NO_PAD };
    match encode_with(source, engine, padded) {
        Ok(result) => result,
        Err(()) => ptr::null_mut(),
    }
}

pub unsafe extern "C" fn b64decode(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"b64decode() takes exactly three arguments".as_ptr());
        }
        return ptr::null_mut();
    }

    let source = unsafe { &**args };
    let validate = match truthy(unsafe { *args.add(1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let padded = match truthy(unsafe { *args.add(2) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let buffer = match BorrowedBuffer::from_object(source) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let Some(input) = buffer.as_slice() else {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"base64 decode argument has negative length".as_ptr());
        }
        return ptr::null_mut();
    };

    // Discarded characters are rare: decode straight from the caller's
    // buffer when every byte is part of the alphabet, and only build a
    // cleaned copy when something has to be dropped.
    let is_clean = |byte: u8| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/') || (padded && byte == b'=')
    };
    let cleaned;
    let input = if input.iter().all(|&byte| is_clean(byte)) {
        input
    } else if validate {
        return unsafe { none_ref() };
    } else {
        cleaned = match Snapshot::filtered(input, is_clean) {
            Ok(snapshot) => snapshot,
            Err(()) => return ptr::null_mut(),
        };
        cleaned.as_slice()
    };

    let engine = if padded {
        &STANDARD_COMPAT
    } else {
        &STANDARD_NO_PAD_COMPAT
    };
    // Size the result exactly so a valid decode needs no shrink (a shrinking
    // realloc of a large bytes object can copy it); the crate's estimate is a
    // fallback if this count is ever too small.
    let estimate = (input.len() / 4 + usize::from(input.len() % 4 != 0)).saturating_mul(3);
    let exact = match input.len() % 4 {
        0 if padded => {
            let padding = input.iter().rev().take(2).take_while(|&&byte| byte == b'=').count();
            estimate - padding.min(estimate)
        }
        2 if !padded => estimate - 2,
        3 if !padded => estimate - 1,
        _ => estimate,
    };
    for capacity in [exact, estimate] {
        let Ok((result, dest_ptr)) = (unsafe { new_bytes(capacity) }) else {
            return ptr::null_mut();
        };
        let dest = unsafe { slice::from_raw_parts_mut(dest_ptr, capacity) };
        match engine.decode_slice(input, dest) {
            Ok(written) if written == capacity => return result,
            Ok(written) => return unsafe { shrink_bytes(result, written) },
            Err(DecodeSliceError::OutputSliceTooSmall) if capacity != estimate => {
                unsafe { Py_DecRef(result) };
            }
            Err(_) => {
                unsafe { Py_DecRef(result) };
                return unsafe { none_ref() };
            }
        }
    }
    unsafe { none_ref() }
}

fn truthy(value: *mut PyObject) -> Result<bool, ()> {
    let result = unsafe { PyObject_IsTrue(value) };
    if result < 0 {
        Err(())
    } else {
        Ok(result != 0)
    }
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(obj: &PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        let buffer = unsafe {
            if PyObject_GetBuffer(obj.as_raw(), view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return Err(());
            }
            Self {
                view: view.assume_init(),
            }
        };
        Ok(buffer)
    }

    fn len(&self) -> Py_ssize_t {
        self.view.len
    }

    fn as_ptr(&self) -> *const u8 {
        self.view.buf.cast::<u8>() as *const u8
    }

    /// The bytes of the view, or `None` for a negative length.
    fn as_slice(&self) -> Option<&[u8]> {
        if self.view.len < 0 {
            return None;
        }
        if self.view.len == 0 { return Some(&[]); }
        Some(unsafe { slice::from_raw_parts(self.as_ptr(), self.view.len as usize) })
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe {
            PyBuffer_Release(&mut self.view);
        }
    }
}

pub extern "C" fn _base64_clear(_obj: *mut PyObject) -> c_int { 0 }
pub extern "C" fn _base64_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: core::cell::UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

macro_rules! module_method {
    ($name:expr, $function:ident, $doc:expr) => {
        PyMethodDef {
            ml_name: $name.as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer {
                PyCFunctionFast: $function,
            },
            ml_flags: METH_FASTCALL,
            ml_doc: $doc.as_ptr() as *mut c_char,
        }
    };
}

pub static _BASE64_MODULE_METHODS: [PyMethodDef; 16] = [
    module_method!(c"standard_b64encode", standard_b64encode, c"Encode with the standard Base64 alphabet"),
    module_method!(c"urlsafe_b64encode", urlsafe_b64encode, c"Encode with the URL-safe Base64 alphabet"),
    module_method!(c"b64decode", b64decode, c"Decode Base64 data for the public base64 module"),
    module_method!(c"b16encode", b16encode, c"Encode with the Base16 alphabet"),
    module_method!(c"b16decode", b16decode, c"Decode Base16 data for the public base64 module"),
    module_method!(c"b32encode", b32encode, c"Encode with the Base32 alphabet"),
    module_method!(c"b32decode", b32decode, c"Decode Base32 data for the public base64 module"),
    module_method!(c"b32hexencode", b32hexencode, c"Encode with the Base32hex alphabet"),
    module_method!(c"b32hexdecode", b32hexdecode, c"Decode Base32hex data for the public base64 module"),
    module_method!(c"b85encode", b85encode, c"Encode with the Base85 alphabet"),
    module_method!(c"b85decode", b85decode, c"Decode Base85 data for the public base64 module"),
    module_method!(c"z85encode", z85encode, c"Encode with the Z85 alphabet"),
    module_method!(c"z85decode", z85decode, c"Decode Z85 data for the public base64 module"),
    module_method!(c"a85encode", a85encode, c"Encode with the Ascii85 alphabet"),
    module_method!(c"a85decode", a85decode, c"Decode Ascii85 data for the public base64 module"),
    PyMethodDef::zeroed(),
];

pub static _BASE64_MODULE: ModuleDef = {
    ModuleDef {
        ffi: core::cell::UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_base64".as_ptr() as *mut _,
            m_doc: c"Rust encoding engines used by base64".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_BASE64_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: core::ptr::null_mut(),
            m_traverse: None,
            m_clear: Some(_base64_clear),
            m_free: Some(_base64_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__base64() -> *mut PyObject {
    _BASE64_MODULE.init_multi_phase()
}
