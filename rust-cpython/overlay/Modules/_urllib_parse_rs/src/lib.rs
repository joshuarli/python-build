//! Percent-encoding and query-string parsing for `urllib.parse`.
//!
//! The crate is `no_std` and declares the few C-API entry points it uses
//! itself: linking Rust `std` (and `cpython-sys`, which depends on it) adds
//! hundreds of KiB of panic, backtrace, and I/O code that is mapped and
//! partly dirtied on every import of the extension. Results are written
//! straight into their `bytes` objects, so nothing allocates through Rust.
#![no_std]

use core::ffi::{c_int, c_void};
use core::ptr;

use cpython_binding::ffi::{
    PyBytes_AsString, PyBytes_FromStringAndSize, PyBytes_Size, PyErr_Clear, PyErr_SetString,
    PyExc_TypeError, PyList_New, PyList_SetItem, PyMethodDef, PyObject, PyTuple_New,
    PyTuple_SetItem, PyUnicode_AsUTF8AndSize, PyUnicode_DecodeUTF8, Py_DecRef, Py_GetConstant,
    Py_ssize_t,
};
use cpython_binding::{
    BytesWriter, Module, Owned, fastcall, method_table_end, single_argument,
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

impl<'a> Decoded<'a> {
    fn iter(&self) -> DecodedIter<'a> {
        DecodedIter {
            input: self.input,
            plus: self.plus,
        }
    }
}

struct DecodedIter<'a> {
    input: &'a [u8],
    plus: bool,
}

impl Iterator for DecodedIter<'_> {
    type Item = u8;

    fn next(&mut self) -> Option<u8> {
        let (&byte, rest) = self.input.split_first()?;
        if byte == b'%' {
            if let [high, low, tail @ ..] = rest {
                if let (Some(high), Some(low)) = (hex_value(*high), hex_value(*low)) {
                    self.input = tail;
                    return Some(high << 4 | low);
                }
            }
        }
        self.input = rest;
        Some(if self.plus && byte == b'+' { b' ' } else { byte })
    }
}

unsafe fn decoded_bytes(decoded: &Decoded) -> *mut PyObject {
    unsafe {
        bytes_with(decoded.iter().count(), |target| {
            for (index, byte) in decoded.iter().enumerate() {
                *target.add(index) = byte;
            }
        })
    }
}

unsafe extern "C" fn quote_from_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return argument_error(c"quote_from_bytes() takes exactly two arguments");
    }
    let Some(input) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    let Some(safe) = (unsafe { bytes_argument(*args.add(1)) }) else {
        return ptr::null_mut();
    };

    let mut keep = [false; 256];
    for byte in 0..=255u8 {
        keep[byte as usize] =
            byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'-' | b'~');
    }
    for byte in safe {
        keep[*byte as usize] = true;
    }

    let mut length = 0;
    for byte in input {
        length += if keep[*byte as usize] { 1 } else { 3 };
    }
    unsafe {
        bytes_with(length, |target| {
            let mut at = 0;
            for byte in input {
                if keep[*byte as usize] {
                    *target.add(at) = *byte;
                    at += 1;
                } else {
                    *target.add(at) = b'%';
                    *target.add(at + 1) = HEX[(*byte >> 4) as usize];
                    *target.add(at + 2) = HEX[(*byte & 15) as usize];
                    at += 3;
                }
            }
        })
    }
}

unsafe extern "C" fn unquote_to_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return argument_error(c"unquote_to_bytes() takes exactly one argument");
    }
    let Some(input) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    unsafe { decoded_bytes(&Decoded { input, plus: false }) }
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

static MODULE_METHODS: [PyMethodDef; 6] = [
    single_argument(
        c"unquote_str",
        unquote_str,
        c"Percent-decode a str as UTF-8 with replacement",
    ),
    fastcall(
        c"quote_from_bytes",
        quote_from_bytes,
        c"Percent-encode bytes with a dynamic safe set",
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
