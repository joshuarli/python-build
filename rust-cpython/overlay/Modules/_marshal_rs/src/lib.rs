use std::cell::UnsafeCell;
use std::collections::{HashMap, HashSet};
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyBool_Type, PyBytes_AsString, PyBytes_FromStringAndSize,
    PyBytes_Size, PyComplex_FromDoubles, PyComplex_ImagAsDouble,
    PyComplex_RealAsDouble, PyComplex_Type, PyCode_Type, Py_DecRef, PyDict_New, PyDict_Next,
    PyDict_SetItem, PyDict_Type, PyErr_Clear, PyErr_NoMemory, PyErr_Occurred, PyFloat_AsDouble,
    PyFloat_FromDouble, PyFloat_Type, PyFrozenSet_New, PyFrozenSet_Type,
    PyList_GetItem, PyList_New, PyList_SetItem, PyList_Size, PyList_Type,
    PyLong_AsLongLong, PyLong_FromLongLong,
    PyLong_FromString, PyLong_Type, PyMethodDef, PyMethodDefFuncPointer,
    PyModuleDef, PyModuleDef_Slot, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    Py_NewRef, PyObject,
    PyObject_GetIter, PyObject_IsTrue, PyObject_Str, PyObject_Type, PySet_Add, PySet_New,
    PySet_Type,
    PyTuple_GetItem, PyTuple_New, PyTuple_SetItem, PyTuple_Size, PyTuple_Type,
    PyTypeObject, PyUnicode_AsEncodedString, PyUnicode_DecodeUTF8,
    PyUnicode_InternInPlace, PyUnicode_Type, PyIter_Next, Py_ssize_t,
    PyBytes_Type, _Py_NoneStruct,
    _Py_NotImplementedStruct,
};

const FORMAT_VERSION: i64 = 6;
const FLAG_REF: u8 = 0x80;
const MAX_DEPTH: usize = 128;
const MAX_RECORD_SIZE: usize = 1 << 28;

unsafe extern "C" {
    fn _PyMarshal_RustUnicodeIsInterned(value: *mut PyObject) -> c_int;
    fn _PyMarshal_RustCodeFields(value: *mut PyObject) -> *mut PyObject;
    fn _PyMarshal_RustBuildCode(fields: *mut PyObject) -> *mut PyObject;
    fn _PyMarshal_RustTupleSetItem(
        tuple: *mut PyObject,
        index: Py_ssize_t,
        item: *mut PyObject,
    );
}

struct PyRef(*mut PyObject);

impl PyRef {
    unsafe fn from_raw(value: *mut PyObject) -> Option<Self> {
        (!value.is_null()).then_some(Self(value))
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }

    fn clone_ref(&self) -> Self {
        unsafe { Self(Py_NewRef(self.0)) }
    }

    fn into_raw(self) -> *mut PyObject {
        let value = self.0;
        std::mem::forget(self);
        value
    }
}

impl Drop for PyRef {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) }
        }
    }
}

fn unsupported() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NotImplementedStruct)) }
}

unsafe fn exact_type(value: *mut PyObject, expected: *mut PyTypeObject) -> bool {
    let actual = unsafe { PyObject_Type(value) };
    if actual.is_null() {
        unsafe { PyErr_Clear() };
        return false;
    }
    let matches = actual == expected.cast::<PyObject>();
    unsafe { Py_DecRef(actual) };
    matches
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Bool,
    Int,
    Float,
    Complex,
    Bytes,
    Unicode,
    Tuple,
    List,
    Dict,
    Set,
    FrozenSet,
    Code,
}

unsafe fn kind_of(value: *mut PyObject) -> Option<Kind> {
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyBool_Type)) } {
        return Some(Kind::Bool);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyLong_Type)) } {
        return Some(Kind::Int);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyFloat_Type)) } {
        return Some(Kind::Float);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyComplex_Type)) } {
        return Some(Kind::Complex);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyBytes_Type)) } {
        return Some(Kind::Bytes);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyUnicode_Type)) } {
        return Some(Kind::Unicode);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyTuple_Type)) } {
        return Some(Kind::Tuple);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyList_Type)) } {
        return Some(Kind::List);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyDict_Type)) } {
        return Some(Kind::Dict);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PySet_Type)) } {
        return Some(Kind::Set);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyFrozenSet_Type)) } {
        return Some(Kind::FrozenSet);
    }
    if unsafe { exact_type(value, ptr::addr_of_mut!(PyCode_Type)) } {
        return Some(Kind::Code);
    }
    None
}

struct Encoder {
    output: Vec<u8>,
    references: HashMap<usize, u32>,
    active: HashSet<usize>,
    allow_code: bool,
}

impl Encoder {
    fn new() -> Self {
        Self {
            output: Vec::new(),
            references: HashMap::new(),
            active: HashSet::new(),
            allow_code: true,
        }
    }

    fn byte(&mut self, value: u8) {
        self.output.push(value);
    }

    fn i32(&mut self, value: i32) {
        self.output.extend_from_slice(&value.to_le_bytes());
    }

    fn u32(&mut self, value: u32) {
        self.output.extend_from_slice(&value.to_le_bytes());
    }

    fn record(&mut self, tag: u8, reference: bool) {
        self.byte(tag | if reference { FLAG_REF } else { 0 });
    }

    fn counted(&mut self, tag: u8, reference: bool, value: &[u8]) -> Result<(), ()> {
        if value.len() > i32::MAX as usize || value.len() > MAX_RECORD_SIZE {
            return Err(());
        }
        self.record(tag, reference);
        self.i32(value.len() as i32);
        self.output.extend_from_slice(value);
        Ok(())
    }

    unsafe fn write_object(&mut self, value: *mut PyObject, depth: usize) -> Result<(), ()> {
        if depth >= MAX_DEPTH || self.output.len() > MAX_RECORD_SIZE {
            return Err(());
        }
        if value == ptr::addr_of_mut!(_Py_NoneStruct) {
            self.byte(b'N');
            return Ok(());
        }
        let kind = unsafe { kind_of(value) }.ok_or(())?;
        if kind == Kind::Bool {
            let truth = unsafe { PyObject_IsTrue(value) };
            if truth < 0 {
                return Err(());
            }
            self.byte(if truth != 0 { b'T' } else { b'F' });
            return Ok(());
        }

        let identity = value as usize;
        let aggregate = matches!(
            kind,
            Kind::Tuple | Kind::List | Kind::Dict | Kind::Set | Kind::FrozenSet | Kind::Code
        );
        if kind == Kind::Code && self.active.contains(&identity) {
            return Err(());
        }
        if let Some(index) = self.references.get(&identity).copied() {
            self.byte(b'r');
            self.u32(index);
            return Ok(());
        }
        let index = u32::try_from(self.references.len()).map_err(|_| ())?;
        self.references.insert(identity, index);
        if aggregate {
            self.active.insert(identity);
        }

        let result = match kind {
            Kind::Bool => unreachable!(),
            Kind::Int => unsafe { self.write_int(value) },
            Kind::Float => unsafe {
                let number = PyFloat_AsDouble(value);
                if number == -1.0 && !PyErr_Occurred().is_null() {
                    Err(())
                } else {
                    self.record(b'g', true);
                    self.output.extend_from_slice(&number.to_le_bytes());
                    Ok(())
                }
            },
            Kind::Complex => unsafe {
                let real = PyComplex_RealAsDouble(value);
                if real == -1.0 && !PyErr_Occurred().is_null() {
                    Err(())
                } else {
                    let imaginary = PyComplex_ImagAsDouble(value);
                    if imaginary == -1.0 && !PyErr_Occurred().is_null() {
                        Err(())
                    } else {
                        self.record(b'y', true);
                        self.output.extend_from_slice(&real.to_le_bytes());
                        self.output.extend_from_slice(&imaginary.to_le_bytes());
                        Ok(())
                    }
                }
            },
            Kind::Bytes => unsafe { self.write_bytes(value) },
            Kind::Unicode => unsafe { self.write_unicode(value) },
            Kind::Tuple => unsafe { self.write_sequence(value, depth, true) },
            Kind::List => unsafe { self.write_sequence(value, depth, false) },
            Kind::Dict => unsafe { self.write_dict(value, depth) },
            Kind::Set | Kind::FrozenSet => unsafe { self.write_set(value, depth, kind) },
            Kind::Code => unsafe { self.write_code(value, depth) },
        };
        if aggregate {
            self.active.remove(&identity);
        }
        result
    }

    unsafe fn write_int(&mut self, value: *mut PyObject) -> Result<(), ()> {
        let small = unsafe { PyLong_AsLongLong(value) };
        if !(small == -1 && !unsafe { PyErr_Occurred() }.is_null()) {
            if (i32::MIN as i64..=i32::MAX as i64).contains(&small) {
                self.record(b'i', true);
                self.i32(small as i32);
                return Ok(());
            }
        } else {
            unsafe { PyErr_Clear() };
        }

        let text = unsafe { PyObject_Str(value) };
        let text = unsafe { PyRef::from_raw(text) }.ok_or(())?;
        let mut length = 0;
        let pointer = unsafe { cpython_sys::PyUnicode_AsUTF8AndSize(text.as_ptr(), &mut length) };
        if pointer.is_null() || length < 0 {
            return Err(());
        }
        let decimal = unsafe { slice::from_raw_parts(pointer.cast::<u8>(), length as usize) };
        let negative = decimal.first() == Some(&b'-');
        let mut digits = Vec::<u16>::new();
        for byte in decimal.iter().copied().skip(usize::from(negative)) {
            if !byte.is_ascii_digit() {
                return Err(());
            }
            let mut carry = (byte - b'0') as u32;
            for digit in &mut digits {
                let value = (*digit as u32) * 10 + carry;
                *digit = (value & 0x7fff) as u16;
                carry = value >> 15;
            }
            while carry != 0 {
                digits.push((carry & 0x7fff) as u16);
                carry >>= 15;
            }
        }
        if digits.is_empty() {
            self.record(b'i', true);
            self.i32(0);
            return Ok(());
        }
        if digits.len() > i32::MAX as usize || digits.len() * 2 > MAX_RECORD_SIZE {
            return Err(());
        }
        let count = digits.len() as i32 * if negative { -1 } else { 1 };
        self.record(b'l', true);
        self.i32(count);
        for digit in digits {
            self.output.extend_from_slice(&digit.to_le_bytes());
        }
        Ok(())
    }

    unsafe fn write_bytes(&mut self, value: *mut PyObject) -> Result<(), ()> {
        let length = unsafe { PyBytes_Size(value) };
        if length < 0 {
            return Err(());
        }
        let pointer = unsafe { PyBytes_AsString(value) };
        if pointer.is_null() {
            return Err(());
        }
        let bytes = unsafe { slice::from_raw_parts(pointer.cast::<u8>(), length as usize) };
        self.counted(b's', true, bytes)
    }

    unsafe fn write_unicode(&mut self, value: *mut PyObject) -> Result<(), ()> {
        let encoded = unsafe {
            PyUnicode_AsEncodedString(value, c"utf-8".as_ptr(), c"surrogatepass".as_ptr())
        };
        let encoded = unsafe { PyRef::from_raw(encoded) }.ok_or(())?;
        let length = unsafe { PyBytes_Size(encoded.as_ptr()) };
        if length < 0 || length as usize > MAX_RECORD_SIZE {
            return Err(());
        }
        let pointer = unsafe { PyBytes_AsString(encoded.as_ptr()) };
        if pointer.is_null() {
            return Err(());
        }
        let bytes = unsafe { slice::from_raw_parts(pointer.cast::<u8>(), length as usize) };
        let interned = unsafe { _PyMarshal_RustUnicodeIsInterned(value) } != 0;
        if bytes.is_ascii() {
            let (tag, short) = match (interned, bytes.len() < 256) {
                (false, true) => (b'z', true),
                (true, true) => (b'Z', true),
                (false, false) => (b'a', false),
                (true, false) => (b'A', false),
            };
            if short {
                self.record(tag, true);
                self.byte(bytes.len() as u8);
                self.output.extend_from_slice(bytes);
                Ok(())
            } else {
                self.counted(tag, true, bytes)
            }
        } else {
            self.counted(if interned { b't' } else { b'u' }, true, bytes)
        }
    }

    unsafe fn write_sequence(
        &mut self,
        value: *mut PyObject,
        depth: usize,
        tuple: bool,
    ) -> Result<(), ()> {
        let length = if tuple {
            unsafe { PyTuple_Size(value) }
        } else {
            unsafe { PyList_Size(value) }
        };
        if length < 0 || length as usize > MAX_RECORD_SIZE / 4 {
            return Err(());
        }
        if tuple && length < 256 {
            self.record(b')', true);
            self.byte(length as u8);
        } else {
            self.record(if tuple { b'(' } else { b'[' }, true);
            self.i32(length as i32);
        }
        for index in 0..length {
            let item = if tuple {
                unsafe { PyTuple_GetItem(value, index) }
            } else {
                unsafe { PyList_GetItem(value, index) }
            };
            if item.is_null() {
                return Err(());
            }
            unsafe { self.write_object(item, depth + 1) }?;
        }
        Ok(())
    }

    unsafe fn write_dict(&mut self, value: *mut PyObject, depth: usize) -> Result<(), ()> {
        self.record(b'{', true);
        let mut position = 0;
        loop {
            let mut key = ptr::null_mut();
            let mut item = ptr::null_mut();
            if unsafe { PyDict_Next(value, &mut position, &mut key, &mut item) } == 0 {
                break;
            }
            unsafe { self.write_object(key, depth + 1) }?;
            unsafe { self.write_object(item, depth + 1) }?;
        }
        self.byte(b'0');
        Ok(())
    }

    unsafe fn write_set(
        &mut self,
        value: *mut PyObject,
        depth: usize,
        kind: Kind,
    ) -> Result<(), ()> {
        let iterator = unsafe { PyObject_GetIter(value) };
        let iterator = unsafe { PyRef::from_raw(iterator) }.ok_or(())?;
        let mut values = Vec::<(Vec<u8>, PyRef)>::new();
        loop {
            let next = unsafe { PyIter_Next(iterator.as_ptr()) };
            if next.is_null() {
                if !unsafe { PyErr_Occurred() }.is_null() {
                    return Err(());
                }
                break;
            }
            let item = unsafe { PyRef(next) };
            let mut key_encoder = Encoder::new();
            key_encoder.allow_code = self.allow_code;
            unsafe { key_encoder.write_object(item.as_ptr(), 0) }?;
            values.push((key_encoder.output, item));
        }
        values.sort_by(|left, right| left.0.cmp(&right.0));
        if values.len() > i32::MAX as usize || values.len() > MAX_RECORD_SIZE / 4 {
            return Err(());
        }
        self.record(if kind == Kind::Set { b'<' } else { b'>' }, true);
        self.i32(values.len() as i32);
        for (_key, item) in values {
            unsafe { self.write_object(item.as_ptr(), depth + 1) }?;
        }
        Ok(())
    }

    unsafe fn write_code(&mut self, value: *mut PyObject, depth: usize) -> Result<(), ()> {
        if !self.allow_code {
            return Err(());
        }
        let fields = unsafe { _PyMarshal_RustCodeFields(value) };
        let fields = unsafe { PyRef::from_raw(fields) }.ok_or(())?;
        self.record(b'c', true);
        for index in 0..5 {
            let field = unsafe { PyTuple_GetItem(fields.as_ptr(), index) };
            if field.is_null() {
                return Err(());
            }
            let number = unsafe { PyLong_AsLongLong(field) };
            if number == -1 && !unsafe { PyErr_Occurred() }.is_null() {
                return Err(());
            }
            let number = i32::try_from(number).map_err(|_| ())?;
            self.i32(number);
        }
        for index in 5..13 {
            let field = unsafe { PyTuple_GetItem(fields.as_ptr(), index) };
            if field.is_null() {
                return Err(());
            }
            unsafe { self.write_object(field, depth + 1) }?;
        }
        let first_line = unsafe { PyTuple_GetItem(fields.as_ptr(), 13) };
        if first_line.is_null() {
            return Err(());
        }
        let first_line = unsafe { PyLong_AsLongLong(first_line) };
        if first_line == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            return Err(());
        }
        self.i32(i32::try_from(first_line).map_err(|_| ())?);
        for index in 14..16 {
            let field = unsafe { PyTuple_GetItem(fields.as_ptr(), index) };
            if field.is_null() {
                return Err(());
            }
            unsafe { self.write_object(field, depth + 1) }?;
        }
        Ok(())
    }
}

fn read_u8(input: &[u8], position: &mut usize) -> Result<u8, ()> {
    let byte = *input.get(*position).ok_or(())?;
    *position += 1;
    Ok(byte)
}

fn read_bytes<'a>(input: &'a [u8], position: &mut usize, size: usize) -> Result<&'a [u8], ()> {
    if size > MAX_RECORD_SIZE {
        return Err(());
    }
    let end = position.checked_add(size).ok_or(())?;
    let bytes = input.get(*position..end).ok_or(())?;
    *position = end;
    Ok(bytes)
}

fn read_i32(input: &[u8], position: &mut usize) -> Result<i32, ()> {
    let bytes: [u8; 4] = read_bytes(input, position, 4)?.try_into().map_err(|_| ())?;
    Ok(i32::from_le_bytes(bytes))
}

fn read_count(input: &[u8], position: &mut usize) -> Result<usize, ()> {
    let count = read_i32(input, position)?;
    if count < 0 || count as usize > MAX_RECORD_SIZE / 2 {
        return Err(());
    }
    Ok(count as usize)
}

fn int_from_decimal(mut digits: Vec<u32>, negative: bool) -> Result<PyRef, ()> {
    if digits.iter().any(|digit| *digit > 0x7fff) || digits.last() == Some(&0) {
        return Err(());
    }
    let mut decimal = vec![0u32];
    for digit in digits.drain(..).rev() {
        let mut carry = digit as u64;
        for chunk in &mut decimal {
            let value = (*chunk as u64) * 32768 + carry;
            *chunk = (value % 1_000_000_000) as u32;
            carry = value / 1_000_000_000;
        }
        while carry != 0 {
            decimal.push((carry % 1_000_000_000) as u32);
            carry /= 1_000_000_000;
        }
    }
    while decimal.len() > 1 && decimal.last() == Some(&0) {
        decimal.pop();
    }
    let mut text = String::new();
    if negative {
        text.push('-');
    }
    let last = *decimal.last().ok_or(())?;
    text.push_str(&last.to_string());
    for chunk in decimal.iter().rev().skip(1) {
        text.push_str(&format!("{chunk:09}"));
    }
    let mut text = text.into_bytes();
    text.push(0);
    let value = unsafe { PyLong_FromString(text.as_mut_ptr().cast(), ptr::null_mut(), 10) };
    unsafe { PyRef::from_raw(value) }.ok_or(())
}

struct Decoder {
    references: Vec<Option<PyRef>>,
    allow_code: bool,
}

impl Decoder {
    fn new(allow_code: bool) -> Self {
        Self {
            references: Vec::new(),
            allow_code,
        }
    }
}

enum Decoded {
    Object(PyRef),
    DictEnd,
}

impl Decoder {
    fn reserve(&mut self, flag: bool) -> Result<Option<usize>, ()> {
        if !flag {
            return Ok(None);
        }
        let index = self.references.len();
        if index >= 0x7fff_fffe {
            return Err(());
        }
        self.references.push(None);
        Ok(Some(index))
    }

    fn insert(&mut self, index: Option<usize>, value: &PyRef) {
        if let Some(index) = index {
            self.references[index] = Some(value.clone_ref());
        }
    }

    unsafe fn decode(
        &mut self,
        input: &[u8],
        position: &mut usize,
        depth: usize,
    ) -> Result<Decoded, ()> {
        if depth >= MAX_DEPTH {
            return Err(());
        }
        let code = read_u8(input, position)?;
        let flag = code & FLAG_REF != 0;
        let tag = code & !FLAG_REF;
        match tag {
            b'0' if !flag => Ok(Decoded::DictEnd),
            b'N' if !flag => Ok(Decoded::Object(unsafe {
                PyRef(Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)))
            })),
            b'T' | b'F' if !flag => {
                let value = unsafe { PyBool_FromLong(if tag == b'T' { 1 } else { 0 }) };
                Ok(Decoded::Object(unsafe { PyRef::from_raw(value) }.ok_or(())?))
            }
            b'i' => {
                let value = unsafe { PyLong_FromLongLong(read_i32(input, position)? as i64) };
                self.finish_scalar(flag, value)
            }
            b'I' => {
                let bytes: [u8; 8] = read_bytes(input, position, 8)?.try_into().map_err(|_| ())?;
                let value = unsafe { PyLong_FromLongLong(i64::from_le_bytes(bytes)) };
                self.finish_scalar(flag, value)
            }
            b'l' => {
                let signed_count = read_i32(input, position)?;
                let count = signed_count.checked_abs().ok_or(())? as usize;
                if count > MAX_RECORD_SIZE / 2 {
                    return Err(());
                }
                let mut digits = Vec::with_capacity(count);
                for _ in 0..count {
                    let pair: [u8; 2] = read_bytes(input, position, 2)?.try_into().map_err(|_| ())?;
                    digits.push(u16::from_le_bytes(pair) as u32);
                }
                if count == 0 {
                    return Err(());
                }
                let value = int_from_decimal(digits, signed_count < 0)?;
                self.finish_ref(flag, Ok(value))
            }
            b'g' => {
                let bytes: [u8; 8] = read_bytes(input, position, 8)?.try_into().map_err(|_| ())?;
                let value = unsafe { PyFloat_FromDouble(f64::from_le_bytes(bytes)) };
                self.finish_scalar(flag, value)
            }
            b'y' => {
                let real_bytes: [u8; 8] = read_bytes(input, position, 8)?.try_into().map_err(|_| ())?;
                let imaginary_bytes: [u8; 8] = read_bytes(input, position, 8)?.try_into().map_err(|_| ())?;
                let value = unsafe {
                    PyComplex_FromDoubles(
                        f64::from_le_bytes(real_bytes),
                        f64::from_le_bytes(imaginary_bytes),
                    )
                };
                self.finish_scalar(flag, value)
            }
            b's' => {
                let count = read_count(input, position)?;
                let value_bytes = read_bytes(input, position, count)?;
                let value = unsafe {
                    PyBytes_FromStringAndSize(value_bytes.as_ptr().cast(), count as Py_ssize_t)
                };
                self.finish_scalar(flag, value)
            }
            b'a' | b'A' | b'u' | b't' => {
                let count = read_count(input, position)?;
                let text = read_bytes(input, position, count)?;
                if (tag == b'a' || tag == b'A') && !text.is_ascii() {
                    return Err(());
                }
                let value = unsafe {
                    PyUnicode_DecodeUTF8(
                        text.as_ptr().cast(),
                        count as Py_ssize_t,
                        c"surrogatepass".as_ptr(),
                    )
                };
                let mut value = unsafe { PyRef::from_raw(value) }.ok_or(())?;
                if tag == b'A' || tag == b't' {
                    let mut pointer = value.into_raw();
                    unsafe { PyUnicode_InternInPlace(&mut pointer) };
                    value = unsafe { PyRef::from_raw(pointer) }.ok_or(())?;
                }
                self.finish_ref(flag, Ok(value))
            }
            b'z' | b'Z' => {
                let count = read_u8(input, position)? as usize;
                let text = read_bytes(input, position, count)?;
                if !text.is_ascii() {
                    return Err(());
                }
                let value = unsafe {
                    PyUnicode_DecodeUTF8(
                        text.as_ptr().cast(),
                        count as Py_ssize_t,
                        c"strict".as_ptr(),
                    )
                };
                let mut value = unsafe { PyRef::from_raw(value) }.ok_or(())?;
                if tag == b'Z' {
                    let mut pointer = value.into_raw();
                    unsafe { PyUnicode_InternInPlace(&mut pointer) };
                    value = unsafe { PyRef::from_raw(pointer) }.ok_or(())?;
                }
                self.finish_ref(flag, Ok(value))
            }
            b')' | b'(' | b'[' => {
                let count = if tag == b')' {
                    read_u8(input, position)? as usize
                } else {
                    read_count(input, position)?
                };
                let index = self.reserve(flag)?;
                let value = unsafe {
                    if tag == b'[' {
                        PyList_New(count as Py_ssize_t)
                    } else {
                        PyTuple_New(count as Py_ssize_t)
                    }
                };
                let value = unsafe { PyRef::from_raw(value) }.ok_or(())?;
                self.insert(index, &value);
                for offset in 0..count {
                    let item = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(item) => item,
                        Decoded::DictEnd => return Err(()),
                    };
                    let status = unsafe {
                        if tag == b'[' {
                            PyList_SetItem(value.as_ptr(), offset as Py_ssize_t, item.into_raw())
                        } else {
                            _PyMarshal_RustTupleSetItem(
                                value.as_ptr(),
                                offset as Py_ssize_t,
                                item.into_raw(),
                            );
                            0
                        }
                    };
                    if status != 0 {
                        return Err(());
                    }
                }
                Ok(Decoded::Object(value))
            }
            b'{' => {
                let index = self.reserve(flag)?;
                let value = unsafe { PyDict_New() };
                let value = unsafe { PyRef::from_raw(value) }.ok_or(())?;
                self.insert(index, &value);
                loop {
                    let key = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(key) => key,
                        Decoded::DictEnd => break,
                    };
                    let item = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(item) => item,
                        Decoded::DictEnd => return Err(()),
                    };
                    if unsafe { PyDict_SetItem(value.as_ptr(), key.as_ptr(), item.as_ptr()) } != 0 {
                        return Err(());
                    }
                }
                Ok(Decoded::Object(value))
            }
            b'c' => {
                if !self.allow_code {
                    return Err(());
                }
                let index = self.reserve(flag)?;
                let fields = unsafe { PyTuple_New(16) };
                let fields = unsafe { PyRef::from_raw(fields) }.ok_or(())?;
                for field_index in 0..5 {
                    let number = read_i32(input, position)? as i64;
                    let number = unsafe { PyLong_FromLongLong(number) };
                    let number = unsafe { PyRef::from_raw(number) }.ok_or(())?;
                    let status = unsafe {
                        PyTuple_SetItem(
                            fields.as_ptr(),
                            field_index,
                            number.into_raw(),
                        )
                    };
                    if status != 0 {
                        return Err(());
                    }
                }
                for field_index in 5..13 {
                    let value = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(value) => value,
                        Decoded::DictEnd => return Err(()),
                    };
                    let status = unsafe {
                        PyTuple_SetItem(
                            fields.as_ptr(),
                            field_index,
                            value.into_raw(),
                        )
                    };
                    if status != 0 {
                        return Err(());
                    }
                }
                let first_line = unsafe { PyLong_FromLongLong(read_i32(input, position)? as i64) };
                let first_line = unsafe { PyRef::from_raw(first_line) }.ok_or(())?;
                if unsafe {
                    PyTuple_SetItem(fields.as_ptr(), 13, first_line.into_raw())
                } != 0
                {
                    return Err(());
                }
                for field_index in 14..16 {
                    let value = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(value) => value,
                        Decoded::DictEnd => return Err(()),
                    };
                    let status = unsafe {
                        PyTuple_SetItem(
                            fields.as_ptr(),
                            field_index,
                            value.into_raw(),
                        )
                    };
                    if status != 0 {
                        return Err(());
                    }
                }
                let code = unsafe { _PyMarshal_RustBuildCode(fields.as_ptr()) };
                let code = unsafe { PyRef::from_raw(code) }.ok_or(())?;
                self.insert(index, &code);
                Ok(Decoded::Object(code))
            }
            b'<' | b'>' => {
                let count = read_count(input, position)?;
                let index = self.reserve(flag)?;
                let set = unsafe { PySet_New(ptr::null_mut()) };
                let set = unsafe { PyRef::from_raw(set) }.ok_or(())?;
                if tag == b'<' {
                    self.insert(index, &set);
                }
                for _ in 0..count {
                    let item = match unsafe { self.decode(input, position, depth + 1)? } {
                        Decoded::Object(item) => item,
                        Decoded::DictEnd => return Err(()),
                    };
                    if unsafe { PySet_Add(set.as_ptr(), item.as_ptr()) } != 0 {
                        return Err(());
                    }
                }
                if tag == b'<' {
                    Ok(Decoded::Object(set))
                } else {
                    let frozen = unsafe { PyFrozenSet_New(set.as_ptr()) };
                    let frozen = unsafe { PyRef::from_raw(frozen) }.ok_or(())?;
                    self.insert(index, &frozen);
                    Ok(Decoded::Object(frozen))
                }
            }
            b'r' if !flag => {
                let index = read_count(input, position)?;
                self.references
                    .get(index)
                    .and_then(Option::as_ref)
                    .map(|value| Decoded::Object(value.clone_ref()))
                    .ok_or(())
            }
            _ => Err(()),
        }
    }

    fn finish_scalar(&mut self, flag: bool, value: *mut PyObject) -> Result<Decoded, ()> {
        self.finish_ref(flag, unsafe { PyRef::from_raw(value) }.ok_or(()))
    }

    fn finish_ref(&mut self, flag: bool, value: Result<PyRef, ()>) -> Result<Decoded, ()> {
        let value = value?;
        if flag {
            self.references.push(Some(value.clone_ref()));
        }
        Ok(Decoded::Object(value))
    }
}

unsafe extern "C" fn dumps_if_supported(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsupported();
    }
    let version = unsafe { PyLong_AsLongLong(*args.add(1)) };
    let allow_code = unsafe { PyLong_AsLongLong(*args.add(2)) };
    if (version == -1 || allow_code == -1) && !unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return unsupported();
    }
    if version != FORMAT_VERSION {
        return unsupported();
    }
    let mut encoder = Encoder::new();
    encoder.allow_code = allow_code != 0;
    if unsafe { encoder.write_object(*args, 0) }.is_err() {
        if !unsafe { PyErr_Occurred() }.is_null() {
            unsafe { PyErr_Clear() };
        }
        return unsupported();
    }
    if encoder.output.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(
            encoder.output.as_ptr().cast(),
            encoder.output.len() as Py_ssize_t,
        )
    }
}

unsafe extern "C" fn loads_if_supported(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsupported();
    }
    let length = unsafe { PyBytes_Size(*args) };
    if length < 0 {
        unsafe { PyErr_Clear() };
        return unsupported();
    }
    let pointer = unsafe { PyBytes_AsString(*args) };
    if pointer.is_null() {
        unsafe { PyErr_Clear() };
        return unsupported();
    }
    let input = unsafe { slice::from_raw_parts(pointer.cast::<u8>(), length as usize) };
    let mut position = 0;
    let allow_code = unsafe { PyLong_AsLongLong(*args.add(2)) };
    if allow_code == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return unsupported();
    }
    let mut decoder = Decoder::new(allow_code != 0);
    let decoded = unsafe { decoder.decode(input, &mut position, 0) };
    match decoded {
        Ok(Decoded::Object(value)) => value.into_raw(),
        Ok(Decoded::DictEnd) | Err(()) => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                unsafe { PyErr_Clear() };
            }
            unsupported()
        }
    }
}

pub extern "C" fn _marshal_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _marshal_rs_free(_object: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_EXEC,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"dumps_if_supported".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: dumps_if_supported,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize supported version 6 marshal records".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"loads_if_supported".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: loads_if_supported,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Read supported version 6 marshal records".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_marshal_rs".as_ptr() as *mut _,
        m_doc: c"Rust support for Python marshal records".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(_marshal_rs_clear),
        m_free: Some(_marshal_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__marshal_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
