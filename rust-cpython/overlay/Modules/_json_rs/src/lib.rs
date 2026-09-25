use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::io::{self, Write};
use std::ptr;
use std::slice;
use std::collections::HashMap;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyDict_New;
use cpython_sys::PyDict_Next;
use cpython_sys::PyDict_SetItem;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyFloat_FromDouble;
use cpython_sys::PyList_GetItem;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyLong_FromString;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_Repr;
use cpython_sys::PyObject_Str;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_IncRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;
use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};
use serde_json::value::RawValue;
use serde_json::Value;

const MAX_DEPTH: usize = 128;

enum JsonValue {
    Null,
    Bool(bool),
    Number(String),
    String(String),
    Array(Vec<JsonValue>),
    Object(Vec<(String, JsonValue)>),
}

impl Serialize for JsonValue {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match self {
            Self::Null => serializer.serialize_unit(),
            Self::Bool(value) => serializer.serialize_bool(*value),
            Self::Number(value) => {
                let raw = RawValue::from_string(value.clone()).map_err(serde::ser::Error::custom)?;
                raw.serialize(serializer)
            }
            Self::String(value) => serializer.serialize_str(value),
            Self::Array(values) => {
                let mut sequence = serializer.serialize_seq(Some(values.len()))?;
                for value in values {
                    sequence.serialize_element(value)?;
                }
                sequence.end()
            }
            Self::Object(values) => {
                let mut map = serializer.serialize_map(Some(values.len()))?;
                for (key, value) in values {
                    map.serialize_entry(key, value)?;
                }
                map.end()
            }
        }
    }
}

struct PythonFormatter;

impl serde_json::ser::Formatter for PythonFormatter {
    fn write_string_fragment<W>(&mut self, writer: &mut W, fragment: &str) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        for character in fragment.chars() {
            let codepoint = character as u32;
            if codepoint <= 0x7e {
                let mut bytes = [0; 4];
                writer.write_all(character.encode_utf8(&mut bytes).as_bytes())?;
            } else if codepoint <= 0xffff {
                write!(writer, "\\u{codepoint:04x}")?;
            } else {
                let scalar = codepoint - 0x1_0000;
                let high = 0xd800 + (scalar >> 10);
                let low = 0xdc00 + (scalar & 0x3ff);
                write!(writer, "\\u{high:04x}\\u{low:04x}")?;
            }
        }
        Ok(())
    }

    fn begin_array<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b"[")
    }

    fn end_array<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b"]")
    }

    fn begin_array_value<W>(&mut self, writer: &mut W, first: bool) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        if first { Ok(()) } else { writer.write_all(b", ") }
    }

    fn begin_object<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b"{")
    }

    fn end_object<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b"}")
    }

    fn begin_object_key<W>(&mut self, writer: &mut W, first: bool) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        if first { Ok(()) } else { writer.write_all(b", ") }
    }

    fn begin_object_value<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b": ")
    }
}

struct PythonText {
    text: String,
}

impl PythonText {
    unsafe fn from_unicode(object: *mut PyObject) -> Result<Self, ()> {
        let mut length = 0;
        let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
        if data.is_null() {
            // A lone surrogate cannot be represented as UTF-8; let CPython's
            // encoder report its native UnicodeEncodeError instead.
            unsafe { PyErr_Clear() };
            return Err(());
        }
        if length < 0 {
            return Err(());
        }
        let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
        let text = unsafe { std::str::from_utf8_unchecked(bytes) }.to_owned();
        Ok(Self { text })
    }

    unsafe fn from_repr(object: *mut PyObject, repr: bool) -> Result<Self, ()> {
        let text = unsafe {
            if repr {
                PyObject_Repr(object)
            } else {
                PyObject_Str(object)
            }
        };
        if text.is_null() {
            return Err(());
        }
        let result = unsafe { Self::from_unicode(text) };
        unsafe { Py_DecRef(text) };
        result
    }
}

unsafe fn class_name(object: *mut PyObject) -> Result<String, ()> {
    let class = unsafe { PyObject_GetAttrString(object, c"__class__".as_ptr()) };
    if class.is_null() {
        return Err(());
    }
    let name = unsafe { PyObject_GetAttrString(class, c"__name__".as_ptr()) };
    unsafe { Py_DecRef(class) };
    if name.is_null() {
        return Err(());
    }
    let result = unsafe { PythonText::from_unicode(name) };
    unsafe { Py_DecRef(name) };
    result.map(|name| name.text)
}

unsafe fn encode_value(object: *mut PyObject, depth: usize) -> Result<JsonValue, ()> {
    if depth > MAX_DEPTH {
        return Err(());
    }
    match unsafe { class_name(object) }?.as_str() {
        "NoneType" => Ok(JsonValue::Null),
        "bool" => {
            let truth = unsafe { cpython_sys::PyObject_IsTrue(object) };
            if truth < 0 {
                Err(())
            } else {
                Ok(JsonValue::Bool(truth != 0))
            }
        }
        "str" => unsafe { PythonText::from_unicode(object) }.map(|text| JsonValue::String(text.text)),
        "int" => unsafe { PythonText::from_repr(object, false) }.map(|text| JsonValue::Number(text.text)),
        "float" => {
            let text = unsafe { PythonText::from_repr(object, true) }?.text;
            if matches!(text.as_str(), "nan" | "inf" | "-inf") {
                return Err(());
            }
            RawValue::from_string(text.clone()).map_err(|_| ())?;
            Ok(JsonValue::Number(text))
        }
        "list" | "tuple" => {
            let length = unsafe {
                if class_name(object)?.as_str() == "list" {
                    cpython_sys::PyList_Size(object)
                } else {
                    cpython_sys::PyTuple_Size(object)
                }
            };
            if length < 0 {
                return Err(());
            }
            let is_list = unsafe { class_name(object)?.as_str() == "list" };
            let mut values = Vec::with_capacity(length as usize);
            for index in 0..length {
                let item = unsafe {
                    if is_list {
                        PyList_GetItem(object, index)
                    } else {
                        cpython_sys::PyTuple_GetItem(object, index)
                    }
                };
                if item.is_null() {
                    return Err(());
                }
                values.push(unsafe { encode_value(item, depth + 1) }?);
            }
            Ok(JsonValue::Array(values))
        }
        "dict" => {
            let mut position = 0;
            let mut entries = Vec::new();
            loop {
                let mut key = ptr::null_mut();
                let mut value = ptr::null_mut();
                if unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } == 0 {
                    break;
                }
                if unsafe { class_name(key) }?.as_str() != "str" {
                    return Err(());
                }
                let key_text = unsafe { PythonText::from_unicode(key) }?.text;
                entries.push((key_text, unsafe { encode_value(value, depth + 1) }?));
            }
            Ok(JsonValue::Object(entries))
        }
        _ => Err(()),
    }
}

fn encode_document(value: &JsonValue) -> Result<String, serde_json::Error> {
    let mut output = Vec::new();
    {
        let mut serializer = serde_json::Serializer::with_formatter(&mut output, PythonFormatter);
        value.serialize(&mut serializer)?;
    }
    // The serializer emits ASCII because escape_non_ascii is set.
    Ok(String::from_utf8(output).expect("ASCII JSON output is valid UTF-8"))
}

unsafe fn new_unicode(text: &str) -> *mut PyObject {
    if text.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
}

unsafe fn new_none() -> *mut PyObject {
    let none = ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>();
    unsafe { Py_IncRef(none) };
    none
}

unsafe fn status_pair(ok: bool, value: *mut PyObject) -> *mut PyObject {
    if value.is_null() {
        return ptr::null_mut();
    }
    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        unsafe { Py_DecRef(value) };
        return ptr::null_mut();
    }
    let flag = unsafe { PyBool_FromLong(if ok { 1 } else { 0 }) };
    if flag.is_null() {
        unsafe {
            Py_DecRef(value);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, flag) } != 0 {
        unsafe {
            Py_DecRef(value);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 1, value) } != 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

unsafe fn decode_value(
    value: Value,
    depth: usize,
    key_memo: &mut HashMap<String, *mut PyObject>,
) -> Result<*mut PyObject, ()> {
    if depth > MAX_DEPTH {
        return Err(());
    }
    match value {
        Value::Null => Ok(unsafe { new_none() }),
        Value::Bool(value) => {
            let result = unsafe { PyBool_FromLong(if value { 1 } else { 0 }) };
            if result.is_null() { Err(()) } else { Ok(result) }
        }
        Value::Number(number) => {
            let text = number.to_string();
            if text.bytes().any(|byte| matches!(byte, b'.' | b'e' | b'E')) {
                let value = text.parse::<f64>().map_err(|_| ())?;
                let result = unsafe { PyFloat_FromDouble(value) };
                if result.is_null() { Err(()) } else { Ok(result) }
            } else {
                let mut text = std::ffi::CString::new(text).map_err(|_| ())?.into_bytes_with_nul();
                let result = unsafe { PyLong_FromString(text.as_mut_ptr().cast(), ptr::null_mut(), 10) };
                if result.is_null() { Err(()) } else { Ok(result) }
            }
        }
        Value::String(value) => {
            let result = unsafe { new_unicode(&value) };
            if result.is_null() { Err(()) } else { Ok(result) }
        }
        Value::Array(values) => {
            if values.len() > Py_ssize_t::MAX as usize {
                unsafe { PyErr_NoMemory() };
                return Err(());
            }
            let result = unsafe { PyList_New(values.len() as Py_ssize_t) };
            if result.is_null() {
                return Err(());
            }
            for (index, item) in values.into_iter().enumerate() {
                let item = match unsafe { decode_value(item, depth + 1, key_memo) } {
                    Ok(item) => item,
                    Err(()) => {
                        unsafe { Py_DecRef(result) };
                        return Err(());
                    }
                };
                if unsafe { PyList_SetItem(result, index as Py_ssize_t, item) } != 0 {
                    unsafe { Py_DecRef(result) };
                    return Err(());
                }
            }
            Ok(result)
        }
        Value::Object(values) => {
            let result = unsafe { PyDict_New() };
            if result.is_null() {
                return Err(());
            }
            for (key, item) in values {
                let key_object = match key_memo.get(&key) {
                    Some(key_object) => *key_object,
                    None => {
                        let key_object = unsafe { new_unicode(&key) };
                        if key_object.is_null() {
                            unsafe { Py_DecRef(result) };
                            return Err(());
                        }
                        key_memo.insert(key, key_object);
                        key_object
                    }
                };
                let item = match unsafe { decode_value(item, depth + 1, key_memo) } {
                    Ok(item) => item,
                    Err(()) => {
                        unsafe { Py_DecRef(result) };
                        return Err(());
                    }
                };
                let status = unsafe { PyDict_SetItem(result, key_object, item) };
                unsafe { Py_DecRef(item) };
                if status != 0 {
                    unsafe { Py_DecRef(result) };
                    return Err(());
                }
            }
            Ok(result)
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
    let value = match unsafe { encode_value(*args, 0) } {
        Ok(value) => value,
        Err(()) => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            return unsafe { new_none() };
        }
    };
    match encode_document(&value) {
        Ok(text) => unsafe { new_unicode(&text) },
        Err(_) => unsafe { new_none() },
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
    let document = match unsafe { PythonText::from_unicode(*args) } {
        Ok(document) => document.text,
        Err(()) => return unsafe { status_pair(false, new_none()) },
    };
    let value = match serde_json::from_str::<Value>(&document) {
        Ok(value) => value,
        Err(_) => return unsafe { status_pair(false, new_none()) },
    };
    let mut key_memo = HashMap::new();
    let decoded = unsafe { decode_value(value, 0, &mut key_memo) };
    for key in key_memo.into_values() {
        unsafe { Py_DecRef(key) };
    }
    match decoded {
        Ok(value) => unsafe { status_pair(true, value) },
        Err(()) => {
            // Conversion limits and allocation failures should be reported by
            // CPython's decoder after this Rust fast path declines the input.
            unsafe { PyErr_Clear() };
            unsafe { status_pair(false, new_none()) }
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
