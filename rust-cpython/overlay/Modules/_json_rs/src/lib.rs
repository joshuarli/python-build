use std::cell::UnsafeCell;
use std::collections::HashMap;
use std::ffi::{c_char, c_int, c_void};
use std::hash::{BuildHasherDefault, Hasher};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_Type;
use cpython_sys::PyDict_New;
use cpython_sys::PyDict_Next;
use cpython_sys::PyDict_SetItem;
use cpython_sys::PyDict_Type;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyFloat_AsDouble;
use cpython_sys::PyFloat_FromDouble;
use cpython_sys::PyFloat_Type;
use cpython_sys::PyList_GetItem;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyList_Size;
use cpython_sys::PyList_Type;
use cpython_sys::PyLong_AsLongLongAndOverflow;
use cpython_sys::PyLong_FromLongLong;
use cpython_sys::PyLong_FromString;
use cpython_sys::PyLong_Type;
use cpython_sys::PyMem_Free;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyOS_double_to_string;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyObject_Str;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTypeObject;
use cpython_sys::_object;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyTuple_Type;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_DATA;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::PyUnicode_KIND;
use cpython_sys::PyUnicode_New;
use cpython_sys::PyUnicode_Type;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_IncRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_FalseStruct;
use cpython_sys::_Py_NoneStruct;
use cpython_sys::_Py_NotImplementedStruct;
use cpython_sys::_Py_TrueStruct;

const MAX_DEPTH: usize = 128;
const HEX: &[u8; 16] = b"0123456789abcdef";

unsafe fn type_of(object: *mut PyObject) -> *mut PyTypeObject {
    unsafe { (*object.cast::<_object>()).ob_type }
}

unsafe fn none() -> *mut PyObject {
    ptr::addr_of_mut!(_Py_NoneStruct)
}

unsafe fn new_none() -> *mut PyObject {
    let none = unsafe { none() };
    unsafe { Py_IncRef(none) };
    none
}

unsafe fn decline() -> *mut PyObject {
    let marker = ptr::addr_of_mut!(_Py_NotImplementedStruct);
    unsafe { Py_IncRef(marker) };
    marker
}

unsafe fn new_unicode(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

// ---------------------------------------------------------------------------
// Encoding: walk the Python object graph once, writing ASCII JSON directly.
// Only exact built-in types are handled; anything else declines so CPython's
// encoder keeps every other behavior.

// The document is encoded twice through the same walk: once to count bytes,
// then straight into the final str, so no intermediate buffer is ever grown.
trait Sink {
    fn push(&mut self, byte: u8);
    fn extend_from_slice(&mut self, bytes: &[u8]);
    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]);
}

struct Counter(usize);

impl Sink for Counter {
    fn push(&mut self, _byte: u8) {
        self.0 += 1;
    }

    fn extend_from_slice(&mut self, bytes: &[u8]) {
        self.0 += bytes.len();
    }

    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.0 += units.len();
    }
}

struct Buffer {
    data: *mut u8,
    capacity: usize,
    length: usize,
}

impl Sink for Buffer {
    fn push(&mut self, byte: u8) {
        if self.length < self.capacity {
            unsafe { *self.data.add(self.length) = byte };
        }
        self.length += 1;
    }

    fn extend_from_slice(&mut self, bytes: &[u8]) {
        if self.length + bytes.len() <= self.capacity {
            unsafe { ptr::copy_nonoverlapping(bytes.as_ptr(), self.data.add(self.length), bytes.len()) };
        }
        self.length += bytes.len();
    }

    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        if self.length + units.len() <= self.capacity {
            for (offset, unit) in units.iter().enumerate() {
                let byte: u32 = (*unit).into();
                unsafe { *self.data.add(self.length + offset) = byte as u8 };
            }
        }
        self.length += units.len();
    }
}

struct Encoder<S: Sink> {
    out: S,
}

impl<S: Sink> Encoder<S> {
    fn write_integer(&mut self, mut value: i64) {
        let mut buffer = [0u8; 20];
        let mut index = buffer.len();
        let negative = value < 0;
        // Work in the negative range so i64::MIN needs no special case.
        if !negative {
            value = -value;
        }
        loop {
            index -= 1;
            buffer[index] = b'0' + (-(value % 10)) as u8;
            value /= 10;
            if value == 0 {
                break;
            }
        }
        if negative {
            self.out.push(b'-');
        }
        self.out.extend_from_slice(&buffer[index..]);
    }

    fn write_escape(&mut self, codepoint: u32) {
        match codepoint {
            0x22 => self.out.extend_from_slice(b"\\\""),
            0x5c => self.out.extend_from_slice(b"\\\\"),
            0x08 => self.out.extend_from_slice(b"\\b"),
            0x0c => self.out.extend_from_slice(b"\\f"),
            0x0a => self.out.extend_from_slice(b"\\n"),
            0x0d => self.out.extend_from_slice(b"\\r"),
            0x09 => self.out.extend_from_slice(b"\\t"),
            _ if codepoint <= 0xffff => self.write_unit(codepoint),
            _ => {
                let scalar = codepoint - 0x1_0000;
                self.write_unit(0xd800 + (scalar >> 10));
                self.write_unit(0xdc00 + (scalar & 0x3ff));
            }
        }
    }

    fn write_unit(&mut self, unit: u32) {
        self.out.extend_from_slice(&[
            b'\\',
            b'u',
            HEX[((unit >> 12) & 0xf) as usize],
            HEX[((unit >> 8) & 0xf) as usize],
            HEX[((unit >> 4) & 0xf) as usize],
            HEX[(unit & 0xf) as usize],
        ]);
    }

    fn write_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.out.push(b'"');
        let mut run = 0;
        for (index, unit) in units.iter().enumerate() {
            let codepoint: u32 = (*unit).into();
            if (0x20..=0x7e).contains(&codepoint) && codepoint != 0x22 && codepoint != 0x5c {
                continue;
            }
            if run < index {
                self.push_run(&units[run..index]);
            }
            self.write_escape(codepoint);
            run = index + 1;
        }
        if run < units.len() {
            self.push_run(&units[run..]);
        }
        self.out.push(b'"');
    }

    fn push_run<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.out.extend_units(units);
    }

    unsafe fn write_string(&mut self, object: *mut PyObject) -> Result<(), ()> {
        let length = unsafe { PyUnicode_GetLength(object) };
        if length < 0 {
            return Err(());
        }
        let length = length as usize;
        let data = unsafe { PyUnicode_DATA(object) };
        match unsafe { PyUnicode_KIND(object) } {
            1 => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u8>(), length) }),
            2 => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u16>(), length) }),
            _ => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u32>(), length) }),
        }
        Ok(())
    }

    unsafe fn write_object(&mut self, object: *mut PyObject, depth: usize) -> Result<(), ()> {
        if depth > MAX_DEPTH {
            return Err(());
        }
        let object_type = unsafe { type_of(object) };
        if object_type == ptr::addr_of_mut!(PyUnicode_Type) {
            unsafe { self.write_string(object) }
        } else if object_type == ptr::addr_of_mut!(PyLong_Type) {
            let mut overflow = 0;
            let value = unsafe { PyLong_AsLongLongAndOverflow(object, &mut overflow) };
            if overflow == 0 {
                if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
                    return Err(());
                }
                self.write_integer(value);
                return Ok(());
            }
            let text = unsafe { PyObject_Str(object) };
            if text.is_null() {
                return Err(());
            }
            let mut length = 0;
            let data = unsafe { PyUnicode_AsUTF8AndSize(text, &mut length) };
            let result = if data.is_null() || length < 0 {
                Err(())
            } else {
                self.out.extend_from_slice(unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) });
                Ok(())
            };
            unsafe { Py_DecRef(text) };
            result
        } else if object_type == ptr::addr_of_mut!(PyDict_Type) {
            self.out.push(b'{');
            let mut position = 0;
            let mut first = true;
            loop {
                let mut key = ptr::null_mut();
                let mut value = ptr::null_mut();
                if unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } == 0 {
                    break;
                }
                if unsafe { type_of(key) } != ptr::addr_of_mut!(PyUnicode_Type) {
                    return Err(());
                }
                if !first {
                    self.out.extend_from_slice(b", ");
                }
                first = false;
                unsafe { self.write_string(key) }?;
                self.out.extend_from_slice(b": ");
                unsafe { self.write_object(value, depth + 1) }?;
            }
            self.out.push(b'}');
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyList_Type)
            || object_type == ptr::addr_of_mut!(PyTuple_Type)
        {
            let is_list = object_type == ptr::addr_of_mut!(PyList_Type);
            let length = unsafe {
                if is_list { PyList_Size(object) } else { PyTuple_Size(object) }
            };
            if length < 0 {
                return Err(());
            }
            self.out.push(b'[');
            for index in 0..length {
                let item = unsafe {
                    if is_list { PyList_GetItem(object, index) } else { PyTuple_GetItem(object, index) }
                };
                if item.is_null() {
                    return Err(());
                }
                if index > 0 {
                    self.out.extend_from_slice(b", ");
                }
                unsafe { self.write_object(item, depth + 1) }?;
            }
            self.out.push(b']');
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyFloat_Type) {
            let value = unsafe { PyFloat_AsDouble(object) };
            if !value.is_finite() {
                return Err(());
            }
            // Py_DTSF_ADD_DOT_0 gives float.__repr__ formatting.
            let text = unsafe { PyOS_double_to_string(value, b'r' as c_char, 0, 2, ptr::null_mut()) };
            if text.is_null() {
                return Err(());
            }
            let length = unsafe { std::ffi::CStr::from_ptr(text) }.to_bytes().len();
            self.out.extend_from_slice(unsafe { slice::from_raw_parts(text.cast::<u8>(), length) });
            unsafe { PyMem_Free(text.cast::<c_void>()) };
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyBool_Type) {
            let truth = unsafe { PyObject_IsTrue(object) };
            if truth < 0 {
                return Err(());
            }
            self.out.extend_from_slice(if truth != 0 { b"true" } else { b"false" });
            Ok(())
        } else if object == unsafe { none() } {
            self.out.extend_from_slice(b"null");
            Ok(())
        } else {
            Err(())
        }
    }
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"dumps() takes exactly one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let mut counter = Encoder { out: Counter(0) };
    if unsafe { counter.write_object(*args, 0) }.is_err() {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { new_none() };
    }
    let size = counter.out.0;
    if size > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    // The output is ASCII, so the str is a compact one-byte-per-character object.
    let text = unsafe { PyUnicode_New(size as Py_ssize_t, 127) };
    if text.is_null() {
        return ptr::null_mut();
    }
    let mut writer = Encoder {
        out: Buffer { data: unsafe { PyUnicode_DATA(text) }.cast::<u8>(), capacity: size, length: 0 },
    };
    if unsafe { writer.write_object(*args, 0) }.is_err() || writer.out.length != size {
        unsafe { Py_DecRef(text) };
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { new_none() };
    }
    text
}

// ---------------------------------------------------------------------------
// Decoding: a strict JSON parser that builds Python objects directly. Every
// input CPython's decoder treats differently (NaN/Infinity, lone surrogates,
// errors, depth or size limits) declines so CPython reports its own result.

#[derive(Default)]
struct FastHasher(u64);

impl Hasher for FastHasher {
    fn finish(&self) -> u64 {
        self.0
    }

    fn write(&mut self, bytes: &[u8]) {
        let mut hash = self.0 ^ 0xcbf2_9ce4_8422_2325;
        for byte in bytes {
            hash = (hash ^ u64::from(*byte)).wrapping_mul(0x0000_0100_0000_01b3);
        }
        self.0 = hash;
    }
}

struct Parser<'a> {
    input: &'a [u8],
    position: usize,
    // Owned references not yet attached to a parent; released on failure.
    stack: Vec<*mut PyObject>,
    keys: HashMap<&'a [u8], *mut PyObject, BuildHasherDefault<FastHasher>>,
    scratch: Vec<u8>,
}

impl<'a> Parser<'a> {
    fn skip_whitespace(&mut self) {
        while let Some(byte) = self.input.get(self.position) {
            if matches!(byte, b' ' | b'\t' | b'\n' | b'\r') {
                self.position += 1;
            } else {
                break;
            }
        }
    }

    fn expect(&mut self, literal: &[u8]) -> Result<(), ()> {
        if self.input[self.position..].starts_with(literal) {
            self.position += literal.len();
            Ok(())
        } else {
            Err(())
        }
    }

    unsafe fn parse_value(&mut self, depth: usize) -> Result<*mut PyObject, ()> {
        if depth > MAX_DEPTH {
            return Err(());
        }
        self.skip_whitespace();
        let byte = *self.input.get(self.position).ok_or(())?;
        match byte {
            b'"' => {
                let text = unsafe { self.parse_string_object(false) }?;
                Ok(text)
            }
            b'{' => unsafe { self.parse_object(depth) },
            b'[' => unsafe { self.parse_array(depth) },
            b't' => {
                self.expect(b"true")?;
                let value = ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>();
                unsafe { Py_IncRef(value) };
                Ok(value)
            }
            b'f' => {
                self.expect(b"false")?;
                let value = ptr::addr_of_mut!(_Py_FalseStruct).cast::<PyObject>();
                unsafe { Py_IncRef(value) };
                Ok(value)
            }
            b'n' => {
                self.expect(b"null")?;
                Ok(unsafe { new_none() })
            }
            b'-' | b'0'..=b'9' => unsafe { self.parse_number() },
            _ => Err(()),
        }
    }

    unsafe fn parse_array(&mut self, depth: usize) -> Result<*mut PyObject, ()> {
        self.position += 1;
        let base = self.stack.len();
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b']') {
            self.position += 1;
        } else {
            loop {
                let item = unsafe { self.parse_value(depth + 1) }?;
                self.stack.push(item);
                self.skip_whitespace();
                match self.input.get(self.position) {
                    Some(b',') => self.position += 1,
                    Some(b']') => {
                        self.position += 1;
                        break;
                    }
                    _ => return Err(()),
                }
            }
        }
        let count = self.stack.len() - base;
        let list = unsafe { PyList_New(count as Py_ssize_t) };
        if list.is_null() {
            return Err(());
        }
        for (index, item) in self.stack.drain(base..).enumerate() {
            // PyList_SetItem steals the reference.
            unsafe { PyList_SetItem(list, index as Py_ssize_t, item) };
        }
        Ok(list)
    }

    unsafe fn parse_object(&mut self, depth: usize) -> Result<*mut PyObject, ()> {
        self.position += 1;
        let dict = unsafe { PyDict_New() };
        if dict.is_null() {
            return Err(());
        }
        self.stack.push(dict);
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b'}') {
            self.position += 1;
            self.stack.pop();
            return Ok(dict);
        }
        loop {
            self.skip_whitespace();
            if self.input.get(self.position) != Some(&b'"') {
                return Err(());
            }
            let key = unsafe { self.parse_string_object(true) }?;
            self.stack.push(key);
            self.skip_whitespace();
            if self.input.get(self.position) != Some(&b':') {
                return Err(());
            }
            self.position += 1;
            let value = unsafe { self.parse_value(depth + 1) }?;
            let status = unsafe { PyDict_SetItem(dict, key, value) };
            unsafe { Py_DecRef(value) };
            if status != 0 {
                return Err(());
            }
            self.stack.pop();
            unsafe { Py_DecRef(key) };
            self.skip_whitespace();
            match self.input.get(self.position) {
                Some(b',') => self.position += 1,
                Some(b'}') => {
                    self.position += 1;
                    break;
                }
                _ => return Err(()),
            }
        }
        self.stack.pop();
        Ok(dict)
    }

    /// Parse the string at `position` (an opening quote) into a new reference.
    /// Keys without escapes are shared within one document.
    unsafe fn parse_string_object(&mut self, is_key: bool) -> Result<*mut PyObject, ()> {
        let input = self.input;
        let start = self.position + 1;
        let mut end = start;
        loop {
            match input.get(end) {
                Some(b'"') => {
                    let text: &'a [u8] = &input[start..end];
                    self.position = end + 1;
                    if !is_key {
                        let object = unsafe { new_unicode(text) };
                        return if object.is_null() { Err(()) } else { Ok(object) };
                    }
                    if let Some(object) = self.keys.get(text) {
                        unsafe { Py_IncRef(*object) };
                        return Ok(*object);
                    }
                    let object = unsafe { new_unicode(text) };
                    if object.is_null() {
                        return Err(());
                    }
                    unsafe { Py_IncRef(object) };
                    self.keys.insert(text, object);
                    return Ok(object);
                }
                Some(b'\\') => break,
                Some(byte) if *byte < 0x20 => return Err(()),
                Some(_) => end += 1,
                None => return Err(()),
            }
        }
        // Slow path: the string contains escapes.
        self.scratch.clear();
        self.scratch.extend_from_slice(&input[start..end]);
        let mut index = end;
        loop {
            match input.get(index) {
                Some(b'"') => {
                    self.position = index + 1;
                    let object = unsafe { new_unicode(&self.scratch) };
                    return if object.is_null() { Err(()) } else { Ok(object) };
                }
                Some(b'\\') => {
                    index += 1;
                    let escape = *input.get(index).ok_or(())?;
                    index += 1;
                    let replacement = match escape {
                        b'"' => b'"',
                        b'\\' => b'\\',
                        b'/' => b'/',
                        b'b' => 0x08,
                        b'f' => 0x0c,
                        b'n' => b'\n',
                        b'r' => b'\r',
                        b't' => b'\t',
                        b'u' => {
                            let mut codepoint = Self::hex4(input, index)?;
                            index += 4;
                            if (0xd800..0xdc00).contains(&codepoint) {
                                if input.get(index) != Some(&b'\\') || input.get(index + 1) != Some(&b'u') {
                                    return Err(());
                                }
                                let low = Self::hex4(input, index + 2)?;
                                if !(0xdc00..0xe000).contains(&low) {
                                    return Err(());
                                }
                                index += 6;
                                codepoint = 0x1_0000 + ((codepoint - 0xd800) << 10) + (low - 0xdc00);
                            } else if (0xdc00..0xe000).contains(&codepoint) {
                                return Err(());
                            }
                            let character = char::from_u32(codepoint).ok_or(())?;
                            let mut buffer = [0; 4];
                            self.scratch.extend_from_slice(character.encode_utf8(&mut buffer).as_bytes());
                            continue;
                        }
                        _ => return Err(()),
                    };
                    self.scratch.push(replacement);
                }
                Some(byte) if *byte < 0x20 => return Err(()),
                Some(byte) => {
                    self.scratch.push(*byte);
                    index += 1;
                }
                None => return Err(()),
            }
        }
    }

    fn hex4(input: &[u8], index: usize) -> Result<u32, ()> {
        let digits = input.get(index..index + 4).ok_or(())?;
        let mut value = 0;
        for digit in digits {
            value = value * 16
                + match digit {
                    b'0'..=b'9' => u32::from(digit - b'0'),
                    b'a'..=b'f' => u32::from(digit - b'a' + 10),
                    b'A'..=b'F' => u32::from(digit - b'A' + 10),
                    _ => return Err(()),
                };
        }
        Ok(value)
    }

    unsafe fn parse_number(&mut self) -> Result<*mut PyObject, ()> {
        let input = self.input;
        let start = self.position;
        let mut index = start;
        if input.get(index) == Some(&b'-') {
            index += 1;
        }
        match input.get(index) {
            Some(b'0') => index += 1,
            Some(b'1'..=b'9') => {
                while matches!(input.get(index), Some(b'0'..=b'9')) {
                    index += 1;
                }
            }
            _ => return Err(()),
        }
        let integer_end = index;
        let mut is_float = false;
        if input.get(index) == Some(&b'.') {
            index += 1;
            let digits = index;
            while matches!(input.get(index), Some(b'0'..=b'9')) {
                index += 1;
            }
            if index == digits {
                return Err(());
            }
            is_float = true;
        }
        if matches!(input.get(index), Some(b'e' | b'E')) {
            index += 1;
            if matches!(input.get(index), Some(b'+' | b'-')) {
                index += 1;
            }
            let digits = index;
            while matches!(input.get(index), Some(b'0'..=b'9')) {
                index += 1;
            }
            if index == digits {
                return Err(());
            }
            is_float = true;
        }
        self.position = index;
        let text = &input[start..index];
        let object = if is_float {
            let text = unsafe { std::str::from_utf8_unchecked(text) };
            let value = text.parse::<f64>().map_err(|_| ())?;
            unsafe { PyFloat_FromDouble(value) }
        } else if integer_end - start <= 18 {
            let negative = text[0] == b'-';
            let mut value: i64 = 0;
            for digit in &text[usize::from(negative)..] {
                value = value * 10 + i64::from(digit - b'0');
            }
            unsafe { PyLong_FromLongLong(if negative { -value } else { value }) }
        } else {
            self.scratch.clear();
            self.scratch.extend_from_slice(text);
            self.scratch.push(0);
            unsafe { PyLong_FromString(self.scratch.as_ptr().cast::<c_char>(), ptr::null_mut(), 10) }
        };
        if object.is_null() { Err(()) } else { Ok(object) }
    }
}

unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"loads() takes exactly one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let mut length = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(*args, &mut length) };
    if data.is_null() {
        // A lone surrogate cannot be represented as UTF-8; let CPython's
        // decoder handle it.
        unsafe { PyErr_Clear() };
        return unsafe { decline() };
    }
    if length < 0 {
        return unsafe { decline() };
    }
    let input = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let mut parser = Parser {
        input,
        position: 0,
        stack: Vec::new(),
        keys: HashMap::default(),
        scratch: Vec::new(),
    };
    let mut result = unsafe { parser.parse_value(0) };
    if let Ok(value) = result {
        parser.skip_whitespace();
        if parser.position != input.len() {
            unsafe { Py_DecRef(value) };
            result = Err(());
        }
    }
    for object in parser.stack.drain(..) {
        unsafe { Py_DecRef(object) };
    }
    for object in parser.keys.drain().map(|(_, object)| object) {
        unsafe { Py_DecRef(object) };
    }
    match result {
        Ok(value) => value,
        Err(()) => {
            // Conversion limits and allocation failures should be reported by
            // CPython's decoder after this Rust fast path declines the input.
            unsafe { PyErr_Clear() };
            unsafe { decline() }
        }
    }
}

pub extern "C" fn _json_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _json_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _JSON_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"dumps".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dumps },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a supported Python document".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: loads },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a complete JSON document".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _JSON_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_json_rs".as_ptr() as *mut _,
        m_doc: c"Rust JSON document codec".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_JSON_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_json_rs_clear),
        m_free: Some(_json_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__json_rs() -> *mut PyObject {
    _JSON_RS_MODULE.init_multi_phase()
}
