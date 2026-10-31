//! Percent-encoding and query-string parsing for `urllib.parse`.
//!
//! The crate is `no_std` and declares the few C-API entry points it uses
//! itself: linking Rust `std` (and `cpython-sys`, which depends on it) adds
//! hundreds of KiB of panic, backtrace, and I/O code that is mapped and
//! partly dirtied on every import of the extension. Results are written
//! straight into their `bytes` objects, so nothing allocates through Rust.
#![no_std]

use core::ffi::{c_int, c_void};
use core::mem::MaybeUninit;
use core::ptr;
use core::slice;

use cpython_binding::ffi::{
    PyBytes_AsString, PyBytes_FromStringAndSize, PyBytes_Size, PyBytes_Type, PyErr_Clear,
    PyErr_SetString, PyExc_TypeError, PyList_New, PyList_SetItem, PyMethodDef, PyObject,
    PyTuple_New, PyTuple_SetItem, PyTypeObject, PyUnicode_AsUTF8AndSize, PyUnicode_DecodeUTF8,
    PyUnicode_FromStringAndSize, PyUnicode_Type, Py_DecRef, Py_GetConstant, Py_ssize_t,
};
use cpython_binding::{
    Borrowed, BytesWriter, Exception, Module, Outcome, Owned, Stop, fastcall, fastcall_arguments,
    into_return, method_table_end, raise, single_argument,
};

unsafe fn bytes_argument<'a>(object: *mut PyObject) -> Option<&'a [u8]> {
    let length = unsafe { PyBytes_Size(object) };
    if length < 0 {
        return None;
    }
    let data = unsafe { PyBytes_AsString(object) };
    if data.is_null() {
        return None;
    }
    Some(unsafe { core::slice::from_raw_parts(data.cast::<u8>(), length as usize) })
}

fn argument_error(message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

/// A new `bytes` of `length` bytes that `fill` fully initializes in place.
unsafe fn bytes_with(length: usize, fill: impl FnOnce(*mut u8)) -> *mut PyObject {
    BytesWriter::create(length)
        .and_then(|mut writer| {
            fill(writer.uninit().as_mut_ptr().cast());
            unsafe { writer.finish(length) }
        })
        .map_or(ptr::null_mut(), Owned::into_raw)
}

unsafe fn bytes_object(value: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(value.as_ptr().cast(), value.len() as Py_ssize_t) }
}

const HEX: &[u8; 16] = b"0123456789ABCDEF";

fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

/// The bytes of `input` with valid `%XX` escapes decoded, and optionally
/// `+` read as a space; an invalid escape keeps its `%` literally.
struct Decoded<'a> {
    input: &'a [u8],
    plus: bool,
}

/// Writes the decoding of `input` to the front of `out`, which holds at
/// least `input.len()` bytes, and returns the decoded length.
fn decode_into<const PLUS: bool>(input: &[u8], out: &mut [MaybeUninit<u8>]) -> usize {
    let mut rest = input;
    let mut at = 0;
    loop {
        let run = rest
            .iter()
            .position(|&byte| byte == b'%' || (PLUS && byte == b'+'))
            .unwrap_or(rest.len());
        let (literal, tail) = rest.split_at(run);
        for (slot, &byte) in out[at..at + run].iter_mut().zip(literal) {
            slot.write(byte);
        }
        at += run;
        let Some((&special, after)) = tail.split_first() else {
            return at;
        };
        rest = after;
        if special == b'+' {
            out[at].write(b' ');
            at += 1;
        } else if let [high, low, tail @ ..] = after
            && let (Some(high), Some(low)) = (hex_value(*high), hex_value(*low))
        {
            out[at].write(high << 4 | low);
            at += 1;
            rest = tail;
        } else {
            out[at].write(b'%');
            at += 1;
        }
    }
}

fn decode_to_stack<'a>(
    decoded: &Decoded,
    buffer: &'a mut [MaybeUninit<u8>; STACK_BYTES],
) -> &'a [u8] {
    let written = if decoded.plus {
        decode_into::<true>(decoded.input, buffer)
    } else {
        decode_into::<false>(decoded.input, buffer)
    };
    unsafe { slice::from_raw_parts(buffer.as_ptr().cast::<u8>(), written) }
}

unsafe fn decoded_bytes(decoded: &Decoded) -> *mut PyObject {
    if decoded.input.len() <= STACK_BYTES {
        let mut buffer = [MaybeUninit::<u8>::uninit(); STACK_BYTES];
        let bytes = decode_to_stack(decoded, &mut buffer);
        return unsafe { bytes_object(bytes) };
    }
    BytesWriter::create(decoded.input.len())
        .and_then(|mut writer| {
            let written = if decoded.plus {
                decode_into::<true>(decoded.input, writer.uninit())
            } else {
                decode_into::<false>(decoded.input, writer.uninit())
            };
            unsafe { writer.finish(written) }
        })
        .map_or(ptr::null_mut(), Owned::into_raw)
}

const ESCAPE: u8 = 0xFF;
const STACK_BYTES: usize = 1024;

const fn unreserved_map() -> [u8; 256] {
    let mut map = [ESCAPE; 256];
    let mut byte = 0;
    while byte < 256 {
        let value = byte as u8;
        if value.is_ascii_alphanumeric() || matches!(value, b'_' | b'.' | b'-' | b'~') {
            map[byte] = value;
        }
        byte += 1;
    }
    map
}

const UNRESERVED: [u8; 256] = unreserved_map();

/// Maps each input byte to its single output byte, or `ESCAPE` when it is
/// written as `%XX`.
struct Quoter {
    map: [u8; 256],
}

impl Quoter {
    fn new(safe: &[u8], space: Space) -> Self {
        let mut map = UNRESERVED;
        for &byte in safe {
            if byte < 128 {
                map[byte as usize] = byte;
            }
        }
        if let Space::Plus = space {
            map[b' ' as usize] = b'+';
        }
        Self { map }
    }

    fn quoted_len(&self, input: &[u8]) -> usize {
        let escaped = input
            .iter()
            .filter(|&&byte| self.map[byte as usize] == ESCAPE)
            .count();
        input.len() + 2 * escaped
    }

    /// Writes the quoting of `input` to `out` and returns the written length.
    ///
    /// # Safety
    /// `out` has room for `quoted_len(input)` bytes.
    unsafe fn write(&self, input: &[u8], out: *mut u8) -> usize {
        let mut at = 0;
        for &byte in input {
            let mapped = self.map[byte as usize];
            if mapped == ESCAPE {
                unsafe {
                    *out.add(at) = b'%';
                    *out.add(at + 1) = HEX[(byte >> 4) as usize];
                    *out.add(at + 2) = HEX[(byte & 15) as usize];
                }
                at += 3;
            } else {
                unsafe { *out.add(at) = mapped };
                at += 1;
            }
        }
        at
    }

    fn quote(&self, input: &[u8]) -> Outcome<Owned> {
        if input.len() <= STACK_BYTES / 3 {
            let mut buffer = [MaybeUninit::<u8>::uninit(); STACK_BYTES];
            let written = unsafe { self.write(input, buffer.as_mut_ptr().cast()) };
            let text = unsafe { slice::from_raw_parts(buffer.as_ptr().cast::<u8>(), written) };
            return ascii_text(text);
        }
        let length = self.quoted_len(input);
        let mut writer = BytesWriter::create(length)?;
        unsafe { self.write(input, writer.uninit().as_mut_ptr().cast()) };
        let quoted = unsafe { writer.finish(length)? };
        let data = unsafe { PyBytes_AsString(quoted.as_ptr()) };
        let text = unsafe { slice::from_raw_parts(data.cast::<u8>(), length) };
        ascii_text(text)
    }
}

#[derive(Clone, Copy)]
enum Space {
    Escaped,
    Plus,
}

fn ascii_text(text: &[u8]) -> Outcome<Owned> {
    let object =
        unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast(), text.len() as Py_ssize_t) };
    unsafe { Owned::from_new_reference(object) }
}

fn is_exact(object: Borrowed<'_>, expected: *mut PyTypeObject) -> bool {
    unsafe { (*object.as_ptr()).ob_type == expected }
}

fn exact_bytes<'a>(object: Borrowed<'a>) -> Outcome<&'a [u8]> {
    if !is_exact(object, &raw mut PyBytes_Type) {
        return Err(Stop::Unsupported);
    }
    unsafe { bytes_argument(object.as_ptr()) }.ok_or(Stop::Unsupported)
}

fn exact_text<'a>(object: Borrowed<'a>) -> Outcome<&'a [u8]> {
    if !is_exact(object, &raw mut PyUnicode_Type) {
        return Err(Stop::Unsupported);
    }
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object.as_ptr(), &mut size) };
    if data.is_null() {
        unsafe { PyErr_Clear() };
        return Err(Stop::Unsupported);
    }
    Ok(unsafe { slice::from_raw_parts(data.cast::<u8>(), size as usize) })
}

fn safe_characters<'a>(object: Borrowed<'a>) -> Outcome<&'a [u8]> {
    if is_exact(object, &raw mut PyBytes_Type) {
        exact_bytes(object)
    } else {
        exact_text(object)
    }
}

fn quote_arguments<'a>(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> Outcome<(Borrowed<'a>, &'a [u8])> {
    let arguments = unsafe { fastcall_arguments::<'a>(args, nargs) };
    let [subject, safe] = arguments else {
        return Err(raise(
            Exception::TypeError,
            c"quote functions take exactly two arguments",
        ));
    };
    Ok((*subject, safe_characters(*safe)?))
}

fn quote_text(args: *mut *mut PyObject, nargs: Py_ssize_t, space: Space) -> Outcome<Owned> {
    let (subject, safe) = quote_arguments(args, nargs)?;
    let input = exact_text(subject)?;
    if input.is_empty() {
        return Ok(subject.to_owned());
    }
    Quoter::new(safe, space).quote(input)
}

unsafe extern "C" fn quote_str(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(quote_text(args, nargs, Space::Escaped))
}

unsafe extern "C" fn quote_plus_str(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(quote_text(args, nargs, Space::Plus))
}

unsafe extern "C" fn quote_from_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let quoted = quote_arguments(args, nargs)
        .and_then(|(subject, safe)| Quoter::new(safe, Space::Escaped).quote(exact_bytes(subject)?));
    into_return(quoted)
}

fn decoded_object(input: &[u8]) -> Outcome<Owned> {
    unsafe {
        Owned::from_new_reference(decoded_bytes(&Decoded {
            input,
            plus: false,
        }))
    }
}

fn unquote_subject(subject: Borrowed<'_>) -> Outcome<Owned> {
    if is_exact(subject, &raw mut PyBytes_Type) {
        let input = exact_bytes(subject)?;
        return if input.contains(&b'%') {
            decoded_object(input)
        } else {
            Ok(subject.to_owned())
        };
    }
    let input = exact_text(subject)?;
    if input.contains(&b'%') {
        decoded_object(input)
    } else {
        BytesWriter::copy_of(input)
    }
}

unsafe extern "C" fn unquote_to_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let arguments = unsafe { fastcall_arguments(args, nargs) };
    let [subject] = arguments else {
        return argument_error(c"unquote_to_bytes() takes exactly one argument");
    };
    into_return(unquote_subject(*subject))
}

/// `unquote()` of a `str` with UTF-8 and `replace`: escapes decoded across
/// the whole text (a literal non-ASCII character is always complete UTF-8,
/// so it cannot join a decoded byte). `None` when the text has no UTF-8
/// form (lone surrogates), which the Python path handles.
unsafe extern "C" fn unquote_str(_module: *mut PyObject, text: *mut PyObject) -> *mut PyObject {
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(text, &mut size) };
    if data.is_null() {
        unsafe { PyErr_Clear() };
        return unsafe { Py_GetConstant(0) };
    }
    let input = unsafe { core::slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    let decoded = Decoded {
        input,
        plus: false,
    };
    if input.len() <= STACK_BYTES {
        let mut buffer = [MaybeUninit::<u8>::uninit(); STACK_BYTES];
        let bytes = decode_to_stack(&decoded, &mut buffer);
        return unsafe {
            PyUnicode_DecodeUTF8(
                bytes.as_ptr().cast(),
                bytes.len() as Py_ssize_t,
                c"replace".as_ptr(),
            )
        };
    }
    let bytes = unsafe { decoded_bytes(&decoded) };
    if bytes.is_null() {
        return bytes;
    }
    let result = unsafe {
        PyUnicode_DecodeUTF8(
            PyBytes_AsString(bytes),
            PyBytes_Size(bytes),
            c"replace".as_ptr(),
        )
    };
    unsafe { Py_DecRef(bytes) };
    result
}

/// The non-empty fields of `query` between `separator`s, each split at its
/// first `=` into a name and a value (empty when there is no `=`).
struct Fields<'a> {
    rest: Option<&'a [u8]>,
    separator: &'a [u8],
}

impl<'a> Fields<'a> {
    fn new(query: &'a [u8], separator: &'a [u8]) -> Self {
        Fields {
            rest: if separator.is_empty() { None } else { Some(query) },
            separator,
        }
    }
}

impl<'a> Iterator for Fields<'a> {
    type Item = (&'a [u8], &'a [u8]);

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            let remaining = self.rest?;
            let boundary = if let [byte] = self.separator {
                remaining.iter().position(|candidate| candidate == byte)
            } else {
                remaining
                    .windows(self.separator.len())
                    .position(|window| window == self.separator)
            };
            let field = match boundary {
                Some(index) => {
                    self.rest = remaining.get(index + self.separator.len()..);
                    remaining.get(..index)?
                }
                None => {
                    self.rest = None;
                    remaining
                }
            };
            if field.is_empty() {
                continue;
            }
            return Some(match field.iter().position(|byte| *byte == b'=') {
                Some(index) => (field.get(..index)?, field.get(index + 1..)?),
                None => (field, field.get(field.len()..)?),
            });
        }
    }
}

/// A `(name, value)` tuple; the tuple takes ownership of both objects.
unsafe fn pair_object(name: *mut PyObject, value: *mut PyObject) -> *mut PyObject {
    if name.is_null() || value.is_null() {
        unsafe {
            if !name.is_null() {
                Py_DecRef(name);
            }
            if !value.is_null() {
                Py_DecRef(value);
            }
        }
        return ptr::null_mut();
    }
    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        unsafe {
            Py_DecRef(name);
            Py_DecRef(value);
        }
        return ptr::null_mut();
    }
    unsafe {
        PyTuple_SetItem(tuple, 0, name);
        PyTuple_SetItem(tuple, 1, value);
    }
    tuple
}

/// The list of `(make(name), make(value))` tuples for every field.
unsafe fn pairs_object(
    query: &[u8],
    separator: &[u8],
    make: unsafe fn(&[u8]) -> *mut PyObject,
) -> *mut PyObject {
    let count = Fields::new(query, separator).count();
    let list = unsafe { PyList_New(count as Py_ssize_t) };
    if list.is_null() {
        return ptr::null_mut();
    }
    for (index, (name, value)) in Fields::new(query, separator).enumerate() {
        let pair = unsafe { pair_object(make(name), make(value)) };
        if pair.is_null() {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
        unsafe { PyList_SetItem(list, index as Py_ssize_t, pair) };
    }
    list
}

unsafe extern "C" fn parse_qsl(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return argument_error(c"parse_qsl() takes exactly two arguments");
    }
    let Some(query) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    let Some(separator) = (unsafe { bytes_argument(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    unsafe { pairs_object(query, separator, bytes_object) }
}

/// A form component (`+` is a space, escapes decoded) as valid UTF-8 bytes,
/// replacing each maximal invalid sequence with U+FFFD.
unsafe fn form_component(part: &[u8]) -> *mut PyObject {
    let object = unsafe {
        decoded_bytes(&Decoded {
            input: part,
            plus: true,
        })
    };
    if object.is_null() {
        return object;
    }
    let decoded = unsafe { bytes_argument(object) }.unwrap_or(&[]);
    if core::str::from_utf8(decoded).is_ok() {
        return object;
    }
    let mut length = 0;
    for chunk in decoded.utf8_chunks() {
        length += chunk.valid().len();
        if !chunk.invalid().is_empty() {
            length += 3;
        }
    }
    let lossy = unsafe {
        bytes_with(length, |target| {
            let mut at = 0;
            for chunk in decoded.utf8_chunks() {
                for byte in chunk.valid().as_bytes() {
                    *target.add(at) = *byte;
                    at += 1;
                }
                if !chunk.invalid().is_empty() {
                    for byte in b"\xEF\xBF\xBD" {
                        *target.add(at) = *byte;
                        at += 1;
                    }
                }
            }
        })
    };
    unsafe { Py_DecRef(object) };
    lossy
}

unsafe extern "C" fn parse_qsl_utf8(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return argument_error(c"parse_qsl_utf8() takes exactly one argument");
    }
    let Some(query) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    unsafe { pairs_object(query, b"&", form_component) }
}

extern "C" fn _urllib_parse_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn _urllib_parse_rs_free(_module: *mut c_void) {}

static MODULE_METHODS: [PyMethodDef; 8] = [
    single_argument(
        c"unquote_str",
        unquote_str,
        c"Percent-decode a str as UTF-8 with replacement",
    ),
    fastcall(
        c"quote_str",
        quote_str,
        c"Percent-encode a str as UTF-8, or None outside the fast path",
    ),
    fastcall(
        c"quote_plus_str",
        quote_plus_str,
        c"Percent-encode a str as UTF-8 with spaces as plus, or None outside the fast path",
    ),
    fastcall(
        c"quote_from_bytes",
        quote_from_bytes,
        c"Percent-encode bytes to a str, or None outside the fast path",
    ),
    fastcall(
        c"unquote_to_bytes",
        unquote_to_bytes,
        c"Decode valid percent escapes without interpreting text",
    ),
    fastcall(
        c"parse_qsl",
        parse_qsl,
        c"Split query fields and retain their percent-encoded byte pairs",
    ),
    fastcall(
        c"parse_qsl_utf8",
        parse_qsl_utf8,
        c"Parse UTF-8 form query fields",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_urllib_parse_rs",
    c"Rust percent-encoding and query parsing for urllib.parse",
    &MODULE_METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__urllib_parse_rs() -> *mut PyObject {
    MODULE.init()
}
