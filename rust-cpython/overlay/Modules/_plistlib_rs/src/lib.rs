//! Rust property-list reader and writer for `plistlib`.
//!
//! `loads` parses XML and binary plists straight into Python objects, and
//! `dumps` serializes Python objects straight to XML or binary bytes, with no
//! intermediate tree. Both accept exactly the well-formed subset whose result
//! is byte-for-byte or object-for-object what `plistlib` produces, and return
//! `NotImplemented` for anything else so the Python implementation handles the
//! remaining inputs and raises the exact exceptions.

use std::cell::UnsafeCell;
use std::collections::HashMap;
use std::ffi::{CString, c_char, c_int, c_void};
use std::io::Write;
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyBool_Type, PyByteArray_AsString, PyByteArray_Size,
    PyByteArray_Type, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize, PyBytes_Type,
    PyDict_New, PyDict_Next, PyDict_SetItem, PyDict_Type, PyErr_Clear, PyErr_Occurred, PyFloat_AsDouble,
    PyFloat_FromDouble, PyFloat_FromString, PyFloat_Type, PyList_Append, PyList_GetItem,
    PyList_New, PyList_Size, PyList_Type, PyLong_AsLongLongAndOverflow,
    PyLong_AsUnsignedLongLong, PyLong_FromLongLong, PyLong_FromString,
    PyLong_FromUnsignedLongLong, PyLong_Type, PyMapping_Items, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject,
    PyObject_CallOneArg, PyObject_GetAttrString, PyObject_Hash, PyObject_Repr,
    PyObject_RichCompareBool, PyObject_Vectorcall, PyTuple_GetItem, PyTuple_Size, PyTuple_Type,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, PyUnicode_Type, Py_DecRef, Py_EQ,
    Py_NewRef, Py_ssize_t, _Py_NoneStruct, _Py_NotImplementedStruct, _Py_TrueStruct,
};

const XML_FORMAT: i64 = 0;
const BINARY_FORMAT: i64 = 1;

/// The input is outside the subset handled here; Python takes over.
struct Decline;
type R<T> = Result<T, Decline>;

/// An owned Python reference.
struct Owned(*mut PyObject);

impl Owned {
    fn new(object: *mut PyObject) -> R<Owned> {
        if object.is_null() {
            unsafe { PyErr_Clear() };
            return Err(Decline);
        }
        Ok(Owned(object))
    }

    fn ptr(&self) -> *mut PyObject {
        self.0
    }

    fn into_raw(self) -> *mut PyObject {
        let object = self.0;
        std::mem::forget(self);
        object
    }
}

impl Drop for Owned {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) };
    }
}

fn type_of(object: *mut PyObject) -> *mut PyObject {
    unsafe { (*object.cast::<cpython_sys::_object>()).ob_type }.cast::<PyObject>()
}

fn str_type() -> *mut PyObject {
    ptr::addr_of_mut!(PyUnicode_Type).cast::<PyObject>()
}

fn new_str(text: &str) -> R<Owned> {
    Owned::new(unsafe {
        PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t)
    })
}

fn new_bytes(data: &[u8]) -> R<Owned> {
    Owned::new(unsafe {
        PyBytes_FromStringAndSize(data.as_ptr().cast::<c_char>(), data.len() as Py_ssize_t)
    })
}

fn new_long(value: i64) -> R<Owned> {
    Owned::new(unsafe { PyLong_FromLongLong(value) })
}

fn new_float(value: f64) -> R<Owned> {
    Owned::new(unsafe { PyFloat_FromDouble(value) })
}

fn call_one(callable: *mut PyObject, argument: *mut PyObject) -> R<Owned> {
    Owned::new(unsafe { PyObject_CallOneArg(callable, argument) })
}

fn call_many(callable: *mut PyObject, arguments: &[*mut PyObject]) -> R<Owned> {
    Owned::new(unsafe {
        PyObject_Vectorcall(callable, arguments.as_ptr(), arguments.len(), ptr::null_mut())
    })
}

fn declined() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NotImplementedStruct)) }
}

/// The UTF-8 bytes of a `str`, or `None` (error cleared) for lone surrogates.
fn utf8_of<'a>(object: *mut PyObject) -> Option<&'a str> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(unsafe { std::str::from_utf8_unchecked(bytes) })
}

fn bytes_of<'a>(object: *mut PyObject) -> Option<&'a [u8]> {
    let mut data = ptr::null_mut();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    Some(unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) })
}

const MAX_DEPTH: usize = 200;

fn big_endian(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0u64, |value, &byte| (value << 8) | u64::from(byte))
}

// ---------------------------------------------------------------- binary load

struct BinaryLoader<'a> {
    data: &'a [u8],
    ref_size: usize,
    offsets: Vec<usize>,
    /// Owned references, one per object reference, null until first read.
    objects: Vec<*mut PyObject>,
    uid_class: *mut PyObject,
    bin_date: *mut PyObject,
}

impl Drop for BinaryLoader<'_> {
    fn drop(&mut self) {
        for &object in &self.objects {
            if !object.is_null() {
                unsafe { Py_DecRef(object) };
            }
        }
    }
}

impl BinaryLoader<'_> {
    fn take(&self, position: usize, length: usize) -> R<&[u8]> {
        let end = position.checked_add(length).ok_or(Decline)?;
        self.data.get(position..end).ok_or(Decline)
    }

    /// The size field after a token, and the position after it.
    fn size(&self, low: u8, position: usize) -> R<(usize, usize)> {
        if low != 0xF {
            return Ok((usize::from(low), position));
        }
        let marker = *self.data.get(position).ok_or(Decline)?;
        let width = 1usize << (marker & 0x3);
        let value = big_endian(self.take(position + 1, width)?);
        Ok((usize::try_from(value).map_err(|_| Decline)?, position + 1 + width))
    }

    fn refs(&self, count: usize, position: usize) -> R<Vec<usize>> {
        let length = count.checked_mul(self.ref_size).ok_or(Decline)?;
        let bytes = self.take(position, length)?;
        Ok(bytes
            .chunks_exact(self.ref_size)
            .map(|chunk| big_endian(chunk) as usize)
            .collect())
    }

    /// The object for a reference, cached so shared references stay shared.
    /// The returned pointer is borrowed from the cache.
    fn read(&mut self, reference: usize, depth: usize) -> R<*mut PyObject> {
        let cached = *self.objects.get(reference).ok_or(Decline)?;
        if !cached.is_null() {
            return Ok(cached);
        }
        if depth > MAX_DEPTH {
            return Err(Decline);
        }
        let offset = self.offsets[reference];
        let token = *self.data.get(offset).ok_or(Decline)?;
        let (high, low) = (token & 0xF0, token & 0x0F);
        let position = offset + 1;
        let object = match (token, high) {
            (0x00, _) => Owned::new(unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) })?,
            (0x08, _) => Owned::new(unsafe { PyBool_FromLong(0) })?,
            (0x09, _) => Owned::new(unsafe { PyBool_FromLong(1) })?,
            (0x0F, _) => new_bytes(b"")?,
            (_, 0x10) => {
                let width = match low {
                    0..=3 | 4 => 1usize << low,
                    _ => return Err(Decline),
                };
                let bytes = self.take(position, width)?;
                if low == 4 {
                    let value = i128::from_be_bytes(bytes.try_into().map_err(|_| Decline)?);
                    if let Ok(signed) = i64::try_from(value) {
                        new_long(signed)?
                    } else if let Ok(unsigned) = u64::try_from(value) {
                        Owned::new(unsafe { PyLong_FromUnsignedLongLong(unsigned) })?
                    } else {
                        return Err(Decline);
                    }
                } else if low == 3 {
                    new_long(i64::from_be_bytes(bytes.try_into().map_err(|_| Decline)?))?
                } else {
                    new_long(big_endian(bytes) as i64)?
                }
            }
            (0x22, _) => {
                let bytes = self.take(position, 4)?;
                new_float(f64::from(f32::from_be_bytes(bytes.try_into().map_err(|_| Decline)?)))?
            }
            (0x23, _) => {
                let bytes = self.take(position, 8)?;
                new_float(f64::from_be_bytes(bytes.try_into().map_err(|_| Decline)?))?
            }
            (0x33, _) => {
                let bytes = self.take(position, 8)?;
                let seconds = new_float(f64::from_be_bytes(bytes.try_into().map_err(|_| Decline)?))?;
                call_one(self.bin_date, seconds.ptr())?
            }
            (_, 0x40) => {
                let (length, start) = self.size(low, position)?;
                new_bytes(self.take(start, length)?)?
            }
            (_, 0x50) => {
                let (length, start) = self.size(low, position)?;
                let bytes = self.take(start, length)?;
                if !bytes.is_ascii() {
                    return Err(Decline);
                }
                new_str(unsafe { std::str::from_utf8_unchecked(bytes) })?
            }
            (_, 0x60) => {
                let (length, start) = self.size(low, position)?;
                let bytes = self.take(start, length.checked_mul(2).ok_or(Decline)?)?;
                let units: Vec<u16> = bytes
                    .chunks_exact(2)
                    .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
                    .collect();
                new_str(&String::from_utf16(&units).map_err(|_| Decline)?)?
            }
            (_, 0x80) => {
                if low > 7 {
                    return Err(Decline);
                }
                let value = big_endian(self.take(position, usize::from(low) + 1)?);
                let number = Owned::new(unsafe { PyLong_FromUnsignedLongLong(value) })?;
                call_one(self.uid_class, number.ptr())?
            }
            (_, 0xA0) => {
                let (count, start) = self.size(low, position)?;
                let refs = self.refs(count, start)?;
                let list = Owned::new(unsafe { PyList_New(0) })?;
                let raw = list.ptr();
                self.objects[reference] = list.into_raw();
                for item in refs {
                    let child = self.read(item, depth + 1)?;
                    if unsafe { PyList_Append(raw, child) } != 0 {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                }
                return Ok(raw);
            }
            (_, 0xD0) => {
                let (count, start) = self.size(low, position)?;
                let keys = self.refs(count, start)?;
                let values = self.refs(count, start + count * self.ref_size)?;
                let dict = Owned::new(unsafe { PyDict_New() })?;
                let raw = dict.ptr();
                self.objects[reference] = dict.into_raw();
                for (key, value) in keys.into_iter().zip(values) {
                    let value = self.read(value, depth + 1)?;
                    let key = self.read(key, depth + 1)?;
                    if unsafe { PyDict_SetItem(raw, key, value) } != 0 {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                }
                return Ok(raw);
            }
            _ => return Err(Decline),
        };
        let raw = object.ptr();
        self.objects[reference] = object.into_raw();
        Ok(raw)
    }
}

fn load_binary(data: &[u8], uid_class: *mut PyObject, bin_date: *mut PyObject) -> R<Owned> {
    if data.len() < 32 {
        return Err(Decline);
    }
    let trailer = &data[data.len() - 32..];
    let offset_size = usize::from(trailer[6]);
    let ref_size = usize::from(trailer[7]);
    let count = usize::try_from(big_endian(&trailer[8..16])).map_err(|_| Decline)?;
    let top = usize::try_from(big_endian(&trailer[16..24])).map_err(|_| Decline)?;
    let table = usize::try_from(big_endian(&trailer[24..32])).map_err(|_| Decline)?;
    if !(1..=8).contains(&offset_size) || !(1..=8).contains(&ref_size) || top >= count {
        return Err(Decline);
    }
    let length = count.checked_mul(offset_size).ok_or(Decline)?;
    let end = table.checked_add(length).ok_or(Decline)?;
    let bytes = data.get(table..end).ok_or(Decline)?;
    let offsets: Vec<usize> = bytes
        .chunks_exact(offset_size)
        .map(|chunk| big_endian(chunk) as usize)
        .collect();
    let mut loader = BinaryLoader {
        data,
        ref_size,
        offsets,
        objects: vec![ptr::null_mut(); count],
        uid_class,
        bin_date,
    };
    let root = loader.read(top, 0)?;
    Owned::new(unsafe { Py_NewRef(root) })
}

// ------------------------------------------------------------------- XML load

struct XmlLoader<'a> {
    data: &'a [u8],
    position: usize,
    date_factory: *mut PyObject,
}

fn is_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r')
}

fn valid_xml_char(code: u32) -> bool {
    matches!(code, 0x9 | 0xA | 0xD | 0x20..=0xD7FF | 0xE000..=0xFFFD | 0x10000..=0x10FFFF)
}

impl<'a> XmlLoader<'a> {
    fn skip_space(&mut self) {
        while self.position < self.data.len() && is_space(self.data[self.position]) {
            self.position += 1;
        }
    }

    fn eat(&mut self, literal: &[u8]) -> bool {
        if self.data[self.position..].starts_with(literal) {
            self.position += literal.len();
            return true;
        }
        false
    }

    fn quoted(&mut self) -> R<&'a [u8]> {
        let quote = *self.data.get(self.position).ok_or(Decline)?;
        if quote != b'"' && quote != b'\'' {
            return Err(Decline);
        }
        let start = self.position + 1;
        let length = self.data[start..].iter().position(|&byte| byte == quote).ok_or(Decline)?;
        self.position = start + length + 1;
        Ok(&self.data[start..start + length])
    }

    fn name(&mut self) -> R<&'a [u8]> {
        let start = self.position;
        while self.position < self.data.len()
            && (self.data[self.position].is_ascii_alphanumeric()
                || matches!(self.data[self.position], b'_' | b'-' | b'.' | b':'))
        {
            self.position += 1;
        }
        if self.position == start || self.data[start].is_ascii_digit() {
            return Err(Decline);
        }
        Ok(&self.data[start..self.position])
    }

    fn space1(&mut self) -> R<()> {
        let before = self.position;
        self.skip_space();
        if self.position == before { Err(Decline) } else { Ok(()) }
    }

    fn prolog(&mut self) -> R<()> {
        if self.eat(b"<?xml") {
            // version, then optional encoding, then optional standalone.
            let mut stage = 0;
            loop {
                let before = self.position;
                self.skip_space();
                if stage > 0 && self.eat(b"?>") {
                    break;
                }
                if self.position == before {
                    return Err(Decline);
                }
                let name = self.name()?;
                self.skip_space();
                if !self.eat(b"=") {
                    return Err(Decline);
                }
                self.skip_space();
                let value = self.quoted()?;
                let (accepted, next) = match name {
                    b"version" => (value == b"1.0", 1),
                    b"encoding" => (value.eq_ignore_ascii_case(b"utf-8"), 2),
                    b"standalone" => (value == b"yes" || value == b"no", 3),
                    _ => (false, 0),
                };
                if !accepted || next <= stage || (stage == 0 && next != 1) {
                    return Err(Decline);
                }
                stage = next;
            }
        }
        self.skip_space();
        if self.eat(b"<!DOCTYPE") {
            self.space1()?;
            self.name()?;
            let before = self.position;
            self.skip_space();
            if self.eat(b"PUBLIC") {
                if self.position == before {
                    return Err(Decline);
                }
                self.space1()?;
                let identifier = self.quoted()?;
                if !identifier.iter().all(|&byte| {
                    byte.is_ascii_alphanumeric() || b" -'()+,./:=?;!*#@$_%".contains(&byte)
                }) {
                    return Err(Decline);
                }
                self.space1()?;
                self.quoted()?;
            } else if self.eat(b"SYSTEM") {
                if self.position == before {
                    return Err(Decline);
                }
                self.space1()?;
                self.quoted()?;
            }
            self.skip_space();
            if !self.eat(b">") {
                return Err(Decline);
            }
            self.skip_space();
        }
        Ok(())
    }

    fn root(&mut self) -> R<Owned> {
        self.prolog()?;
        if !self.eat(b"<plist") {
            return Err(Decline);
        }
        let mut version_seen = false;
        loop {
            let before = self.position;
            self.skip_space();
            if self.eat(b">") {
                break;
            }
            if self.position == before {
                return Err(Decline);
            }
            let name = self.name()?;
            self.skip_space();
            if name != b"version" || version_seen || !self.eat(b"=") {
                return Err(Decline);
            }
            version_seen = true;
            self.skip_space();
            let value = self.quoted()?;
            if value.iter().any(|&byte| byte == b'<' || byte == b'&') {
                return Err(Decline);
            }
        }
        self.skip_space();
        let root = self.value(0)?;
        self.skip_space();
        if !self.eat(b"</plist>") {
            return Err(Decline);
        }
        self.skip_space();
        if self.position != self.data.len() {
            return Err(Decline);
        }
        Ok(root)
    }

    /// Character data up to `</name>`, with the predefined and numeric
    /// entities resolved. Anything else (markup, CDATA) declines.
    fn text(&mut self, name: &[u8]) -> R<std::borrow::Cow<'a, str>> {
        let start = self.position;
        let length = self.data[start..].iter().position(|&byte| byte == b'<').ok_or(Decline)?;
        let raw = &self.data[start..start + length];
        self.position = start + length;
        self.eat(b"</").then_some(()).ok_or(Decline)?;
        if !self.eat(name) || !self.eat(b">") {
            return Err(Decline);
        }
        // The input was validated as UTF-8 up front and `<` starts an ASCII
        // boundary, so the slice is valid UTF-8.
        let text = unsafe { std::str::from_utf8_unchecked(raw) };
        if text.contains("]]>") {
            return Err(Decline);
        }
        if !text.contains('&') {
            return Ok(std::borrow::Cow::Borrowed(text));
        }
        let mut decoded = String::with_capacity(text.len());
        let mut rest = text;
        while let Some(index) = rest.find('&') {
            decoded.push_str(&rest[..index]);
            rest = &rest[index + 1..];
            let end = rest.find(';').ok_or(Decline)?;
            let entity = &rest[..end];
            match entity {
                "amp" => decoded.push('&'),
                "lt" => decoded.push('<'),
                "gt" => decoded.push('>'),
                "quot" => decoded.push('"'),
                "apos" => decoded.push('\''),
                _ => {
                    let number = entity.strip_prefix('#').ok_or(Decline)?;
                    let code = if let Some(hex) = number.strip_prefix('x') {
                        if hex.is_empty() || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                            return Err(Decline);
                        }
                        u32::from_str_radix(hex, 16).map_err(|_| Decline)?
                    } else {
                        if number.is_empty() || !number.bytes().all(|byte| byte.is_ascii_digit()) {
                            return Err(Decline);
                        }
                        number.parse::<u32>().map_err(|_| Decline)?
                    };
                    if !valid_xml_char(code) {
                        return Err(Decline);
                    }
                    decoded.push(char::from_u32(code).ok_or(Decline)?);
                }
            }
            rest = &rest[end + 1..];
        }
        decoded.push_str(rest);
        Ok(std::borrow::Cow::Owned(decoded))
    }

    /// Consume `/>` or `>` after an element name. True for the empty form.
    fn tag_end(&mut self) -> R<bool> {
        if self.eat(b"/>") {
            return Ok(true);
        }
        if self.eat(b">") {
            return Ok(false);
        }
        Err(Decline)
    }

    fn value(&mut self, depth: usize) -> R<Owned> {
        if depth > MAX_DEPTH || !self.eat(b"<") {
            return Err(Decline);
        }
        let name = self.name()?;
        match name {
            b"dict" => {
                let dict = Owned::new(unsafe { PyDict_New() })?;
                if self.tag_end()? {
                    return Ok(dict);
                }
                loop {
                    self.skip_space();
                    if self.eat(b"</dict>") {
                        return Ok(dict);
                    }
                    if !self.eat(b"<key>") {
                        return Err(Decline);
                    }
                    let key = self.text(b"key")?;
                    if key.is_empty() {
                        return Err(Decline);
                    }
                    let key = new_str(&key)?;
                    self.skip_space();
                    let value = self.value(depth + 1)?;
                    if unsafe { PyDict_SetItem(dict.ptr(), key.ptr(), value.ptr()) } != 0 {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                }
            }
            b"array" => {
                let list = Owned::new(unsafe { PyList_New(0) })?;
                if self.tag_end()? {
                    return Ok(list);
                }
                loop {
                    self.skip_space();
                    if self.eat(b"</array>") {
                        return Ok(list);
                    }
                    let item = self.value(depth + 1)?;
                    if unsafe { PyList_Append(list.ptr(), item.ptr()) } != 0 {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                }
            }
            b"true" | b"false" => {
                let truth = name == b"true";
                if !self.tag_end()? && !self.eat(if truth { b"</true>" } else { b"</false>" }) {
                    return Err(Decline);
                }
                Owned::new(unsafe { PyBool_FromLong(truth as _) })
            }
            b"string" | b"data" => {
                if self.tag_end()? {
                    return if name == b"string" { new_str("") } else { new_bytes(b"") };
                }
                let text = self.text(name)?;
                if name == b"string" {
                    new_str(&text)
                } else {
                    new_bytes(&decode_base64(text.as_bytes())?)
                }
            }
            b"integer" | b"real" | b"date" => {
                if self.tag_end()? {
                    return Err(Decline);
                }
                let text = self.text(name)?;
                match name {
                    b"integer" => parse_integer(&text),
                    b"real" => parse_real(&text),
                    _ => self.parse_date(&text),
                }
            }
            _ => Err(Decline),
        }
    }

    fn parse_date(&self, text: &str) -> R<Owned> {
        let bytes = text.as_bytes();
        let digit = |index: usize| -> R<i64> {
            let byte = bytes[index];
            if byte.is_ascii_digit() { Ok(i64::from(byte - b'0')) } else { Err(Decline) }
        };
        let number = |start: usize, width: usize| -> R<i64> {
            let mut value = 0;
            for index in start..start + width {
                value = value * 10 + digit(index)?;
            }
            Ok(value)
        };
        if bytes.len() != 20
            || bytes[4] != b'-'
            || bytes[7] != b'-'
            || bytes[10] != b'T'
            || bytes[13] != b':'
            || bytes[16] != b':'
            || bytes[19] != b'Z'
        {
            return Err(Decline);
        }
        let parts = [
            number(0, 4)?,
            number(5, 2)?,
            number(8, 2)?,
            number(11, 2)?,
            number(14, 2)?,
            number(17, 2)?,
        ];
        let mut owned = Vec::with_capacity(6);
        for part in parts {
            owned.push(new_long(part)?);
        }
        let arguments: Vec<*mut PyObject> = owned.iter().map(Owned::ptr).collect();
        call_many(self.date_factory, &arguments)
    }
}

fn parse_integer(text: &str) -> R<Owned> {
    let (digits, base) = match text.strip_prefix("0x").or_else(|| text.strip_prefix("0X")) {
        Some(hex) => {
            if hex.is_empty() || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                return Err(Decline);
            }
            (hex, 16)
        }
        None => {
            let magnitude = text.strip_prefix('-').unwrap_or(text);
            if magnitude.is_empty() || !magnitude.bytes().all(|byte| byte.is_ascii_digit()) {
                return Err(Decline);
            }
            (text, 10)
        }
    };
    let digits = CString::new(digits).map_err(|_| Decline)?;
    Owned::new(unsafe { PyLong_FromString(digits.as_ptr(), ptr::null_mut(), base) })
}

fn parse_real(text: &str) -> R<Owned> {
    if text.is_empty() || !text.bytes().all(|byte| byte.is_ascii_digit() || b"+-.eE".contains(&byte)) {
        return Err(Decline);
    }
    let text = new_str(text)?;
    Owned::new(unsafe { PyFloat_FromString(text.ptr()) })
}

const BASE64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn decode_base64(text: &[u8]) -> R<Vec<u8>> {
    let mut output = Vec::with_capacity(text.len() / 4 * 3);
    let mut accumulator = 0u32;
    let mut bits = 0u32;
    let mut padding = 0usize;
    let mut symbols = 0usize;
    for &byte in text {
        if matches!(byte, b' ' | b'\t' | b'\n') {
            continue;
        }
        if byte == b'=' {
            padding += 1;
            symbols += 1;
            continue;
        }
        if padding != 0 {
            return Err(Decline);
        }
        let value = match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return Err(Decline),
        };
        symbols += 1;
        accumulator = (accumulator << 6) | u32::from(value);
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            output.push((accumulator >> bits) as u8);
            accumulator &= (1 << bits) - 1;
        }
    }
    if symbols % 4 != 0 || padding > 2 || accumulator != 0 {
        return Err(Decline);
    }
    Ok(output)
}

fn load_xml(data: &[u8], date_factory: *mut PyObject) -> R<Owned> {
    if std::str::from_utf8(data).is_err() {
        return Err(Decline);
    }
    // Bytes whose treatment differs from expat: carriage returns (line-end
    // normalization), control characters, and the U+FFFE/U+FFFF non-characters.
    if data.iter().any(|&byte| byte == b'\r' || (byte < 0x20 && byte != b'\t' && byte != b'\n'))
        || data.windows(3).any(|window| window == [0xEF, 0xBF, 0xBE] || window == [0xEF, 0xBF, 0xBF])
    {
        return Err(Decline);
    }
    let mut loader = XmlLoader { data, position: 0, date_factory };
    loader.root()
}

unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 5 {
        return declined();
    }
    let arguments = unsafe { std::slice::from_raw_parts(args, 5) };
    let Some(data) = bytes_of(arguments[0]) else {
        return declined();
    };
    let mut overflow: c_int = 0;
    let format = unsafe { PyLong_AsLongLongAndOverflow(arguments[1], &mut overflow) };
    if overflow != 0 {
        unsafe { PyErr_Clear() };
        return declined();
    }
    let result = match format as i64 {
        XML_FORMAT => load_xml(data, arguments[3]),
        BINARY_FORMAT => load_binary(data, arguments[2], arguments[4]),
        _ => Err(Decline),
    };
    match result {
        Ok(object) => object.into_raw(),
        Err(Decline) => declined(),
    }
}

// ----------------------------------------------------------------- dump common

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Str,
    Bool,
    Int,
    Float,
    Dict,
    Frozen,
    Bytes,
    ByteArray,
    Datetime,
    List,
    Tuple,
    Uid,
    Other,
}

struct Context {
    sort_keys: bool,
    aware: *mut PyObject,
    uid_class: *mut PyObject,
    frozendict_class: *mut PyObject,
    datetime_class: *mut PyObject,
    date_convert: *mut PyObject,
}

impl Context {
    fn kind(&self, object: *mut PyObject) -> Kind {
        let kind = type_of(object);
        if kind == str_type() {
            Kind::Str
        } else if kind == ptr::addr_of_mut!(PyBool_Type).cast::<PyObject>() {
            Kind::Bool
        } else if kind == ptr::addr_of_mut!(PyLong_Type).cast::<PyObject>() {
            Kind::Int
        } else if kind == ptr::addr_of_mut!(PyFloat_Type).cast::<PyObject>() {
            Kind::Float
        } else if kind == ptr::addr_of_mut!(PyDict_Type).cast::<PyObject>() {
            Kind::Dict
        } else if kind == self.frozendict_class {
            Kind::Frozen
        } else if kind == ptr::addr_of_mut!(PyBytes_Type).cast::<PyObject>() {
            Kind::Bytes
        } else if kind == ptr::addr_of_mut!(PyByteArray_Type).cast::<PyObject>() {
            Kind::ByteArray
        } else if kind == self.datetime_class {
            Kind::Datetime
        } else if kind == ptr::addr_of_mut!(PyList_Type).cast::<PyObject>() {
            Kind::List
        } else if kind == ptr::addr_of_mut!(PyTuple_Type).cast::<PyObject>() {
            Kind::Tuple
        } else if kind == self.uid_class {
            Kind::Uid
        } else {
            Kind::Other
        }
    }

    /// The mapping's `(key, value)` pairs in serialization order. Every key
    /// must be an exact `str`; other keys (skipped, sorted against, or
    /// rejected by `plistlib`) decline. The owner keeps borrowed pointers alive.
    fn entries(
        &self,
        object: *mut PyObject,
        frozen: bool,
    ) -> R<(Vec<(*mut PyObject, *mut PyObject)>, Option<Owned>)> {
        let mut entries = Vec::new();
        let mut owner = None;
        if frozen {
            let items = Owned::new(unsafe { PyMapping_Items(object) })?;
            let length = unsafe { PyList_Size(items.ptr()) };
            for index in 0..length.max(0) {
                let pair = unsafe { PyList_GetItem(items.ptr(), index) };
                let key = unsafe { PyTuple_GetItem(pair, 0) };
                let value = unsafe { PyTuple_GetItem(pair, 1) };
                if key.is_null() || value.is_null() {
                    unsafe { PyErr_Clear() };
                    return Err(Decline);
                }
                entries.push((key, value));
            }
            owner = Some(items);
        } else {
            let mut position: Py_ssize_t = 0;
            let mut key = ptr::null_mut();
            let mut value = ptr::null_mut();
            while unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } != 0 {
                entries.push((key, value));
            }
        }
        if entries.iter().any(|&(key, _)| type_of(key) != str_type()) {
            return Err(Decline);
        }
        if self.sort_keys {
            let mut keyed = Vec::with_capacity(entries.len());
            for &(key, value) in &entries {
                keyed.push((utf8_of(key).ok_or(Decline)?, key, value));
            }
            keyed.sort_by(|left, right| left.0.cmp(right.0));
            entries = keyed.into_iter().map(|(_, key, value)| (key, value)).collect();
        }
        Ok((entries, owner))
    }

    fn integer(&self, object: *mut PyObject) -> R<i128> {
        let mut overflow: c_int = 0;
        let signed = unsafe { PyLong_AsLongLongAndOverflow(object, &mut overflow) };
        if overflow == 0 {
            if signed == -1 {
                unsafe { PyErr_Clear() };
            }
            return Ok(i128::from(signed));
        }
        if overflow < 0 {
            return Err(Decline);
        }
        let unsigned = unsafe { PyLong_AsUnsignedLongLong(object) };
        if unsigned == u64::MAX && !unsafe { PyErr_Occurred() }.is_null() {
            unsafe { PyErr_Clear() };
            return Err(Decline);
        }
        Ok(i128::from(unsigned))
    }

    fn date_call(&self, object: *mut PyObject) -> R<Owned> {
        call_many(self.date_convert, &[object, self.aware])
    }
}

// ------------------------------------------------------------------- XML dump

struct XmlWriter<'a> {
    context: &'a Context,
    out: Vec<u8>,
}

fn base64_encode(data: &[u8], line: usize, out: &mut Vec<u8>, level: usize) {
    let mut column = 0;
    let start_line = |out: &mut Vec<u8>| {
        out.extend(std::iter::repeat_n(b'\t', level));
    };
    if !data.is_empty() {
        start_line(out);
    }
    let mut emit = |symbol: u8, out: &mut Vec<u8>| {
        if column == line {
            out.push(b'\n');
            start_line(out);
            column = 0;
        }
        out.push(symbol);
        column += 1;
    };
    for chunk in data.chunks(3) {
        let value = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        emit(BASE64[(value >> 18) as usize & 63], out);
        emit(BASE64[(value >> 12) as usize & 63], out);
        emit(if chunk.len() > 1 { BASE64[(value >> 6) as usize & 63] } else { b'=' }, out);
        emit(if chunk.len() > 2 { BASE64[value as usize & 63] } else { b'=' }, out);
    }
    if !data.is_empty() {
        out.push(b'\n');
    }
}

impl XmlWriter<'_> {
    fn indent(&mut self, level: usize) {
        self.out.extend(std::iter::repeat_n(b'\t', level));
    }

    fn escaped(&mut self, text: &str) -> R<()> {
        let bytes = text.as_bytes();
        let mut index = 0;
        while index < bytes.len() {
            let byte = bytes[index];
            match byte {
                0x00..=0x08 | 0x0B | 0x0C | 0x0E..=0x1F => return Err(Decline),
                b'\r' => {
                    self.out.push(b'\n');
                    if bytes.get(index + 1) == Some(&b'\n') {
                        index += 1;
                    }
                }
                b'&' => self.out.extend_from_slice(b"&amp;"),
                b'<' => self.out.extend_from_slice(b"&lt;"),
                b'>' => self.out.extend_from_slice(b"&gt;"),
                _ => self.out.push(byte),
            }
            index += 1;
        }
        Ok(())
    }

    fn simple(&mut self, level: usize, element: &str, text: &str) -> R<()> {
        self.indent(level);
        self.out.push(b'<');
        self.out.extend_from_slice(element.as_bytes());
        self.out.push(b'>');
        self.escaped(text)?;
        self.out.extend_from_slice(b"</");
        self.out.extend_from_slice(element.as_bytes());
        self.out.extend_from_slice(b">\n");
        Ok(())
    }

    fn empty(&mut self, level: usize, element: &str) {
        self.indent(level);
        self.out.push(b'<');
        self.out.extend_from_slice(element.as_bytes());
        self.out.extend_from_slice(b"/>\n");
    }

    fn value(&mut self, object: *mut PyObject, level: usize) -> R<()> {
        if level > MAX_DEPTH {
            return Err(Decline);
        }
        match self.context.kind(object) {
            Kind::Str => {
                let text = utf8_of(object).ok_or(Decline)?;
                self.simple(level, "string", text)
            }
            Kind::Bool => {
                let truth = object == ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>();
                self.empty(level, if truth { "true" } else { "false" });
                Ok(())
            }
            Kind::Int => {
                let value = self.context.integer(object)?;
                if value < -(1i128 << 63) || value >= 1i128 << 64 {
                    return Err(Decline);
                }
                self.indent(level);
                let _ = write!(self.out, "<integer>{value}</integer>\n");
                Ok(())
            }
            Kind::Float => {
                let text = Owned::new(unsafe { PyObject_Repr(object) })?;
                let text = utf8_of(text.ptr()).ok_or(Decline)?;
                self.simple(level, "real", text)
            }
            Kind::Dict | Kind::Frozen => {
                let frozen = self.context.kind(object) == Kind::Frozen;
                let (entries, _owner) = self.context.entries(object, frozen)?;
                if entries.is_empty() {
                    self.empty(level, "dict");
                    return Ok(());
                }
                self.indent(level);
                self.out.extend_from_slice(b"<dict>\n");
                for (key, value) in entries {
                    let text = utf8_of(key).ok_or(Decline)?;
                    self.simple(level + 1, "key", text)?;
                    self.value(value, level + 1)?;
                }
                self.indent(level);
                self.out.extend_from_slice(b"</dict>\n");
                Ok(())
            }
            Kind::Bytes | Kind::ByteArray => {
                let data = if self.context.kind(object) == Kind::Bytes {
                    bytes_of(object).ok_or(Decline)?
                } else {
                    let length = unsafe { PyByteArray_Size(object) };
                    let data = unsafe { PyByteArray_AsString(object) };
                    if length < 0 || data.is_null() {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                    unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) }
                };
                self.indent(level);
                self.out.extend_from_slice(b"<data>\n");
                let columns = 76usize.saturating_sub(8 * level).max(16);
                base64_encode(data, columns / 4 * 4, &mut self.out, level);
                self.indent(level);
                self.out.extend_from_slice(b"</data>\n");
                Ok(())
            }
            Kind::Datetime => {
                let text = self.context.date_call(object)?;
                if type_of(text.ptr()) != str_type() {
                    return Err(Decline);
                }
                let text = utf8_of(text.ptr()).ok_or(Decline)?;
                self.simple(level, "date", text)
            }
            Kind::List | Kind::Tuple => {
                let is_list = self.context.kind(object) == Kind::List;
                let length = unsafe {
                    if is_list { PyList_Size(object) } else { PyTuple_Size(object) }
                };
                if length <= 0 {
                    self.empty(level, "array");
                    return Ok(());
                }
                self.indent(level);
                self.out.extend_from_slice(b"<array>\n");
                for index in 0..length {
                    let item = unsafe {
                        if is_list { PyList_GetItem(object, index) } else { PyTuple_GetItem(object, index) }
                    };
                    if item.is_null() {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                    self.value(item, level + 1)?;
                }
                self.indent(level);
                self.out.extend_from_slice(b"</array>\n");
                Ok(())
            }
            Kind::Uid | Kind::Other => Err(Decline),
        }
    }
}

const XML_HEADER: &[u8] = b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n";

fn dump_xml(context: &Context, value: *mut PyObject) -> R<Vec<u8>> {
    let mut writer = XmlWriter { context, out: Vec::with_capacity(4096) };
    writer.out.extend_from_slice(XML_HEADER);
    writer.out.extend_from_slice(b"<plist version=\"1.0\">\n");
    writer.value(value, 0)?;
    writer.out.extend_from_slice(b"</plist>\n");
    Ok(writer.out)
}

// ----------------------------------------------------------------- binary dump

enum Node {
    Pending,
    None,
    Bool(bool),
    Int(i128),
    Float(f64),
    Date(f64),
    Bytes(*const u8, usize),
    Str(*const u8, usize),
    Uid(u64),
    List(Vec<u32>),
    Dict(Vec<u32>, Vec<u32>),
}

/// Flattens the object graph in `plistlib`'s order, deduplicating scalars by
/// (type, value) and everything else by identity.
struct Flattener<'a> {
    context: &'a Context,
    nodes: Vec<Node>,
    strings: HashMap<&'static [u8], u32>,
    byte_strings: HashMap<&'static [u8], u32>,
    integers: HashMap<i128, u32>,
    floats: HashMap<u64, u32>,
    booleans: [Option<u32>; 2],
    identities: HashMap<usize, u32>,
    dates: HashMap<isize, Vec<(*mut PyObject, u32)>>,
    /// Keeps date conversion results and frozendict snapshots alive.
    keep: Vec<Owned>,
}

impl Flattener<'_> {
    fn add(&mut self, node: Node) -> u32 {
        self.nodes.push(node);
        (self.nodes.len() - 1) as u32
    }

    fn flatten(&mut self, object: *mut PyObject, depth: usize) -> R<u32> {
        if depth > MAX_DEPTH {
            return Err(Decline);
        }
        match self.context.kind(object) {
            Kind::Str => {
                let text = utf8_of(object).ok_or(Decline)?;
                let key: &'static [u8] = unsafe { std::mem::transmute(text.as_bytes()) };
                if let Some(&existing) = self.strings.get(key) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Str(key.as_ptr(), key.len()));
                self.strings.insert(key, reference);
                Ok(reference)
            }
            Kind::Bytes => {
                let data = bytes_of(object).ok_or(Decline)?;
                let key: &'static [u8] = unsafe { std::mem::transmute(data) };
                if let Some(&existing) = self.byte_strings.get(key) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Bytes(key.as_ptr(), key.len()));
                self.byte_strings.insert(key, reference);
                Ok(reference)
            }
            Kind::Bool => {
                let truth = object == ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>();
                if let Some(existing) = self.booleans[truth as usize] {
                    return Ok(existing);
                }
                let reference = self.add(Node::Bool(truth));
                self.booleans[truth as usize] = Some(reference);
                Ok(reference)
            }
            Kind::Int => {
                let value = self.context.integer(object)?;
                if value < -(1i128 << 63) || value >= 1i128 << 64 {
                    return Err(Decline);
                }
                if let Some(&existing) = self.integers.get(&value) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Int(value));
                self.integers.insert(value, reference);
                Ok(reference)
            }
            Kind::Float => {
                let value = unsafe { PyFloat_AsDouble(object) };
                if value.is_nan() {
                    return Err(Decline);
                }
                // Equal floats (0.0 and -0.0) share the first one's entry.
                let key = if value == 0.0 { 0 } else { value.to_bits() };
                if let Some(&existing) = self.floats.get(&key) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Float(value));
                self.floats.insert(key, reference);
                Ok(reference)
            }
            Kind::Datetime => {
                let hash = unsafe { PyObject_Hash(object) };
                if hash == -1 {
                    unsafe { PyErr_Clear() };
                    return Err(Decline);
                }
                if let Some(bucket) = self.dates.get(&hash) {
                    for &(other, reference) in bucket {
                        let equal = unsafe { PyObject_RichCompareBool(other, object, Py_EQ as c_int) };
                        if equal < 0 {
                            unsafe { PyErr_Clear() };
                            return Err(Decline);
                        }
                        if equal == 1 {
                            return Ok(reference);
                        }
                    }
                }
                let seconds = self.context.date_call(object)?;
                if type_of(seconds.ptr()) != ptr::addr_of_mut!(PyFloat_Type).cast::<PyObject>() {
                    return Err(Decline);
                }
                let value = unsafe { PyFloat_AsDouble(seconds.ptr()) };
                let reference = self.add(Node::Date(value));
                // Only the graph's own objects are kept: they outlive the call.
                self.dates.entry(hash).or_default().push((object, reference));
                Ok(reference)
            }
            Kind::Uid => {
                if let Some(&existing) = self.identities.get(&(object as usize)) {
                    return Ok(existing);
                }
                let data = Owned::new(unsafe { PyObject_GetAttrString(object, c"data".as_ptr()) })?;
                if type_of(data.ptr()) != ptr::addr_of_mut!(PyLong_Type).cast::<PyObject>() {
                    return Err(Decline);
                }
                let value = self.context.integer(data.ptr())?;
                let value = u64::try_from(value).map_err(|_| Decline)?;
                let reference = self.add(Node::Uid(value));
                self.identities.insert(object as usize, reference);
                Ok(reference)
            }
            Kind::ByteArray => {
                if let Some(&existing) = self.identities.get(&(object as usize)) {
                    return Ok(existing);
                }
                let length = unsafe { PyByteArray_Size(object) };
                let data = unsafe { PyByteArray_AsString(object) };
                if length < 0 || data.is_null() {
                    unsafe { PyErr_Clear() };
                    return Err(Decline);
                }
                let reference = self.add(Node::Bytes(data.cast::<u8>(), length as usize));
                self.identities.insert(object as usize, reference);
                Ok(reference)
            }
            Kind::List | Kind::Tuple => {
                if let Some(&existing) = self.identities.get(&(object as usize)) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Pending);
                self.identities.insert(object as usize, reference);
                let is_list = self.context.kind(object) == Kind::List;
                let length = unsafe {
                    if is_list { PyList_Size(object) } else { PyTuple_Size(object) }
                };
                let mut refs = Vec::with_capacity(length.max(0) as usize);
                for index in 0..length.max(0) {
                    let item = unsafe {
                        if is_list { PyList_GetItem(object, index) } else { PyTuple_GetItem(object, index) }
                    };
                    if item.is_null() {
                        unsafe { PyErr_Clear() };
                        return Err(Decline);
                    }
                    refs.push(self.flatten(item, depth + 1)?);
                }
                self.nodes[reference as usize] = Node::List(refs);
                Ok(reference)
            }
            Kind::Dict | Kind::Frozen => {
                if let Some(&existing) = self.identities.get(&(object as usize)) {
                    return Ok(existing);
                }
                let reference = self.add(Node::Pending);
                self.identities.insert(object as usize, reference);
                let frozen = self.context.kind(object) == Kind::Frozen;
                let (entries, owner) = self.context.entries(object, frozen)?;
                if let Some(owner) = owner {
                    self.keep.push(owner);
                }
                let mut keys = Vec::with_capacity(entries.len());
                let mut values = Vec::with_capacity(entries.len());
                for &(key, _) in &entries {
                    keys.push(self.flatten(key, depth + 1)?);
                }
                for &(_, value) in &entries {
                    values.push(self.flatten(value, depth + 1)?);
                }
                self.nodes[reference as usize] = Node::Dict(keys, values);
                Ok(reference)
            }
            Kind::Other => {
                // `None` is the only other type `plistlib` writes, by identity.
                if object == ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>() {
                    if let Some(&existing) = self.identities.get(&(object as usize)) {
                        return Ok(existing);
                    }
                    let reference = self.add(Node::None);
                    self.identities.insert(object as usize, reference);
                    return Ok(reference);
                }
                Err(Decline)
            }
        }
    }
}

fn count_to_size(count: u64) -> usize {
    if count < 1 << 8 {
        1
    } else if count < 1 << 16 {
        2
    } else if count < 1 << 32 {
        4
    } else {
        8
    }
}

fn push_sized(out: &mut Vec<u8>, value: u64, size: usize) {
    out.extend_from_slice(&value.to_be_bytes()[8 - size..]);
}

fn write_size(out: &mut Vec<u8>, token: u8, size: usize) {
    let size = size as u64;
    if size < 15 {
        out.push(token | size as u8);
    } else if size < 1 << 8 {
        out.extend_from_slice(&[token | 0xF, 0x10, size as u8]);
    } else if size < 1 << 16 {
        out.extend_from_slice(&[token | 0xF, 0x11]);
        push_sized(out, size, 2);
    } else if size < 1 << 32 {
        out.extend_from_slice(&[token | 0xF, 0x12]);
        push_sized(out, size, 4);
    } else {
        out.extend_from_slice(&[token | 0xF, 0x13]);
        push_sized(out, size, 8);
    }
}

fn dump_binary(context: &Context, value: *mut PyObject) -> R<Vec<u8>> {
    let mut flattener = Flattener {
        context,
        nodes: Vec::new(),
        strings: HashMap::new(),
        byte_strings: HashMap::new(),
        integers: HashMap::new(),
        floats: HashMap::new(),
        booleans: [None, None],
        identities: HashMap::new(),
        dates: HashMap::new(),
        keep: Vec::new(),
    };
    let top = flattener.flatten(value, 0)?;
    let nodes = std::mem::take(&mut flattener.nodes);
    let ref_size = count_to_size(nodes.len() as u64);
    let mut out = Vec::with_capacity(4096);
    out.extend_from_slice(b"bplist00");
    let mut offsets = Vec::with_capacity(nodes.len());
    for node in &nodes {
        offsets.push(out.len() as u64);
        match node {
            Node::Pending => return Err(Decline),
            Node::None => out.push(0x00),
            Node::Bool(false) => out.push(0x08),
            Node::Bool(true) => out.push(0x09),
            Node::Int(value) => {
                let value = *value;
                if value < 0 {
                    out.push(0x13);
                    out.extend_from_slice(&(value as i64).to_be_bytes());
                } else if value < 1 << 8 {
                    out.push(0x10);
                    push_sized(&mut out, value as u64, 1);
                } else if value < 1 << 16 {
                    out.push(0x11);
                    push_sized(&mut out, value as u64, 2);
                } else if value < 1 << 32 {
                    out.push(0x12);
                    push_sized(&mut out, value as u64, 4);
                } else if value < 1 << 63 {
                    out.push(0x13);
                    push_sized(&mut out, value as u64, 8);
                } else {
                    out.push(0x14);
                    out.extend_from_slice(&value.to_be_bytes());
                }
            }
            Node::Float(value) => {
                out.push(0x23);
                out.extend_from_slice(&value.to_be_bytes());
            }
            Node::Date(value) => {
                out.push(0x33);
                out.extend_from_slice(&value.to_be_bytes());
            }
            Node::Bytes(data, length) => {
                write_size(&mut out, 0x40, *length);
                out.extend_from_slice(unsafe { std::slice::from_raw_parts(*data, *length) });
            }
            Node::Str(data, length) => {
                let text = unsafe {
                    std::str::from_utf8_unchecked(std::slice::from_raw_parts(*data, *length))
                };
                if text.is_ascii() {
                    write_size(&mut out, 0x50, text.len());
                    out.extend_from_slice(text.as_bytes());
                } else {
                    let units: Vec<u16> = text.encode_utf16().collect();
                    write_size(&mut out, 0x60, units.len());
                    for unit in units {
                        out.extend_from_slice(&unit.to_be_bytes());
                    }
                }
            }
            Node::Uid(value) => {
                if *value < 1 << 8 {
                    out.push(0x80);
                    push_sized(&mut out, *value, 1);
                } else if *value < 1 << 16 {
                    out.push(0x81);
                    push_sized(&mut out, *value, 2);
                } else if *value < 1 << 32 {
                    out.push(0x83);
                    push_sized(&mut out, *value, 4);
                } else {
                    out.push(0x87);
                    push_sized(&mut out, *value, 8);
                }
            }
            Node::List(refs) => {
                write_size(&mut out, 0xA0, refs.len());
                for &reference in refs {
                    push_sized(&mut out, u64::from(reference), ref_size);
                }
            }
            Node::Dict(keys, values) => {
                write_size(&mut out, 0xD0, keys.len());
                for &reference in keys.iter().chain(values) {
                    push_sized(&mut out, u64::from(reference), ref_size);
                }
            }
        }
    }
    let table = out.len() as u64;
    let offset_size = count_to_size(table);
    for offset in offsets {
        push_sized(&mut out, offset, offset_size);
    }
    out.extend_from_slice(&[0; 5]);
    out.extend_from_slice(&[0, offset_size as u8, ref_size as u8]);
    out.extend_from_slice(&(nodes.len() as u64).to_be_bytes());
    out.extend_from_slice(&u64::from(top).to_be_bytes());
    out.extend_from_slice(&table.to_be_bytes());
    Ok(out)
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 9 {
        return declined();
    }
    let arguments = unsafe { std::slice::from_raw_parts(args, 9) };
    let mut overflow: c_int = 0;
    let format = unsafe { PyLong_AsLongLongAndOverflow(arguments[1], &mut overflow) };
    if overflow != 0 {
        unsafe { PyErr_Clear() };
        return declined();
    }
    let context = Context {
        sort_keys: arguments[2] == ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>(),
        aware: arguments[4],
        uid_class: arguments[5],
        frozendict_class: arguments[6],
        datetime_class: arguments[7],
        date_convert: arguments[8],
    };
    let result = match format as i64 {
        XML_FORMAT => dump_xml(&context, arguments[0]),
        BINARY_FORMAT => dump_binary(&context, arguments[0]),
        _ => Err(Decline),
    };
    match result.and_then(|output| new_bytes(&output)) {
        Ok(object) => object.into_raw(),
        Err(Decline) => declined(),
    }
}

pub extern "C" fn _plistlib_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _plistlib_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _PLISTLIB_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: loads },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a complete property list, or return NotImplemented".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"dumps".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dumps },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a complete property list, or return NotImplemented".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _PLISTLIB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_plistlib_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust parser and serializer for complete property lists".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: _PLISTLIB_RS_MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_plistlib_rs_clear),
        m_free: Some(_plistlib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__plistlib_rs() -> *mut PyObject {
    _PLISTLIB_RS_MODULE.init_multi_phase()
}
