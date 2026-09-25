use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use base64::engine::general_purpose::{
    GeneralPurpose, GeneralPurposeConfig, STANDARD, STANDARD_NO_PAD, URL_SAFE,
    URL_SAFE_NO_PAD,
};
use base64::engine::DecodePaddingMode;
use base64::{alphabet, Engine};
use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::Py_NewRef;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::_Py_NoneStruct;
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
    let input = unsafe { slice::from_raw_parts(buffer.as_ptr(), input_len) };
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

fn bytes_from_slice(data: &[u8]) -> *mut PyObject {
    if data.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(data.as_ptr().cast(), data.len() as Py_ssize_t) }
}

fn bytes_from_vec(data: Vec<u8>) -> *mut PyObject {
    bytes_from_slice(&data)
}

fn borrowed_bytes(source: &PyObject, operation: &'static [u8]) -> Result<(BorrowedBuffer, Vec<u8>), ()> {
    let buffer = BorrowedBuffer::from_object(source)?;
    let len = buffer.len();
    if len < 0 {
        unsafe { PyErr_SetString(PyExc_TypeError, operation.as_ptr().cast()) };
        return Err(());
    }
    let input = unsafe { slice::from_raw_parts(buffer.as_ptr(), len as usize) }.to_vec();
    Ok((buffer, input))
}

unsafe fn none_ref() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

fn encode_data_encoding(
    source: &PyObject,
    encoding: &'static Encoding,
) -> *mut PyObject {
    let (buffer, input) = match borrowed_bytes(source, b"base encoding argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    let output = encoding.encode(&input);
    bytes_from_slice(output.as_bytes())
}

fn decode_data_encoding(
    source: &PyObject,
    encoding: &'static Encoding,
) -> *mut PyObject {
    let (buffer, input) = match borrowed_bytes(source, b"base decoding argument has negative length\0") {
        Ok(data) => data,
        Err(()) => return ptr::null_mut(),
    };
    drop(buffer);
    match encoding.decode(&input) {
        Ok(output) => bytes_from_vec(output),
        Err(_) => unsafe { none_ref() },
    }
}

fn encode_base85(input: &[u8], padded: bool, alphabet: &[u8; 85]) -> Vec<u8> {
    let complete_len = input.len() / 4 * 5;
    let remainder = input.len() % 4;
    let output_len = complete_len + if remainder == 0 { 0 } else if padded { 5 } else { remainder + 1 };
    let mut output = Vec::with_capacity(output_len);
    for chunk in input.chunks(4) {
        let mut bytes = [0u8; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0u8; 5];
        for slot in encoded.iter_mut().rev() {
            *slot = alphabet[(value % 85) as usize];
            value /= 85;
        }
        let count = if chunk.len() == 4 || padded { 5 } else { chunk.len() + 1 };
        output.extend_from_slice(&encoded[..count]);
    }
    output
}

const B85_ALPHABET: &[u8; 85] = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
const Z85_ALPHABET: &[u8; 85] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#";

fn decode_base85(input: &[u8], alphabet: &[u8; 85]) -> Option<Vec<u8>> {
    let mut output = Vec::with_capacity(input.len() / 5 * 4 + input.len() % 5);
    let mut chunks = input.chunks_exact(5);
    for chunk in &mut chunks {
        let value = chunk.iter().try_fold(0u64, |value, byte| {
            let digit = alphabet.iter().position(|candidate| candidate == byte)? as u64;
            value.checked_mul(85)?.checked_add(digit)
        })?;
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes());
    }
    let remainder = chunks.remainder();
    if remainder.len() == 1 {
        return None;
    }
    if !remainder.is_empty() {
        let mut value = 0u64;
        for &byte in remainder {
            let digit = alphabet.iter().position(|candidate| *candidate == byte)? as u64;
            value = value.checked_mul(85)?.checked_add(digit)?;
        }
        for _ in remainder.len()..5 {
            value = value.checked_mul(85)?.checked_add(84)?;
        }
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes()[..remainder.len() - 1]);
    }
    Some(output)
}

fn encode_ascii85(input: &[u8]) -> Vec<u8> {
    let mut output = Vec::with_capacity(input.len() / 4 * 5 + input.len() % 4 + usize::from(input.len() % 4 != 0));
    for chunk in input.chunks(4) {
        if chunk == [0, 0, 0, 0] {
            output.push(b'z');
            continue;
        }
        let mut bytes = [0u8; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0u8; 5];
        for slot in encoded.iter_mut().rev() {
            *slot = b'!' + (value % 85) as u8;
            value /= 85;
        }
        let count = if chunk.len() == 4 { 5 } else { chunk.len() + 1 };
        output.extend_from_slice(&encoded[..count]);
    }
    output
}

fn decode_ascii85(input: &[u8]) -> Option<Vec<u8>> {
    let mut output = Vec::with_capacity(input.len() * 4 / 5);
    let mut group = [84u8; 5];
    let mut count = 0usize;
    for &byte in input {
        if matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b) {
            continue;
        }
        if byte == b'z' {
            if count != 0 {
                return None;
            }
            output.extend_from_slice(&[0, 0, 0, 0]);
            continue;
        }
        if !(b'!'..=b'u').contains(&byte) {
            return None;
        }
        group[count] = byte - b'!';
        count += 1;
        if count == 5 {
            let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
            if value > u32::MAX as u64 {
                return None;
            }
            output.extend_from_slice(&(value as u32).to_be_bytes());
            group = [84; 5];
            count = 0;
        }
    }
    if count == 1 {
        return None;
    }
    if count > 1 {
        let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes()[..count - 1]);
    }
    Some(output)
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
    bytes_from_vec(encode_base85(&input, padded, alphabet))
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
    match decode_base85(&input, alphabet) {
        Some(output) => bytes_from_vec(output),
        None => unsafe { none_ref() },
    }
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
    bytes_from_vec(encode_ascii85(&input))
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
    match decode_ascii85(&input) {
        Some(output) => bytes_from_vec(output),
        None => unsafe { none_ref() },
    }
}

pub extern "C" fn _base64_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _base64_free(_obj: *mut c_void) {}

/// # Safety
/// `module` must be a valid pointer of PyObject representing the module.
/// `args` must be a valid pointer to an array of valid PyObject pointers with length `nargs`.
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
    let input_len = buffer.len();
    if input_len < 0 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"base64 decode argument has negative length".as_ptr());
        }
        return ptr::null_mut();
    }
    let input = unsafe { slice::from_raw_parts(buffer.as_ptr(), input_len as usize) };

    let mut cleaned = Vec::with_capacity(input.len());
    for &byte in input {
        let standard_character = byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/');
        if standard_character || (padded && byte == b'=') {
            cleaned.push(byte);
        } else if validate {
            return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
        }
    }

    let engine = if padded {
        &STANDARD_COMPAT
    } else {
        &STANDARD_NO_PAD_COMPAT
    };
    match engine.decode(&cleaned) {
        Ok(decoded) if decoded.len() <= isize::MAX as usize => unsafe {
            PyBytes_FromStringAndSize(decoded.as_ptr().cast(), decoded.len() as Py_ssize_t)
        },
        Ok(_) => unsafe {
            PyErr_NoMemory();
            ptr::null_mut()
        },
        Err(_) => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
    }
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
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe {
            PyBuffer_Release(&mut self.view);
        }
    }
}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
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
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_base64".as_ptr() as *mut _,
            m_doc: c"Rust encoding engines used by base64".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_BASE64_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: std::ptr::null_mut(),
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
