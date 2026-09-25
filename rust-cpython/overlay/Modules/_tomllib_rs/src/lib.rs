use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyErr_Clear, PyErr_SetString, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize,
    Py_ssize_t,
};
use serde::Serialize;
use serde_json::Value as JsonValue;
use toml_edit::{ArrayOfTables, DocumentMut, Formatted, Item, Table, Value};

const TAG_TABLE: u64 = 0;
const TAG_ARRAY: u64 = 1;
const TAG_STRING: u64 = 2;
const TAG_INTEGER: u64 = 3;
const TAG_FLOAT: u64 = 4;
const TAG_BOOLEAN: u64 = 5;
const TAG_DATETIME: u64 = 6;

fn raw_float(value: &Formatted<f64>) -> String {
    value
        .as_repr()
        .and_then(|repr| repr.as_raw().as_str())
        .map(str::to_owned)
        .unwrap_or_else(|| value.value().to_string())
}

fn raw_datetime(value: &Formatted<toml_edit::Datetime>) -> String {
    value
        .as_repr()
        .and_then(|repr| repr.as_raw().as_str())
        .map(str::to_owned)
        .unwrap_or_else(|| value.value().to_string())
}

fn tagged(tag: u64, payload: JsonValue) -> JsonValue {
    JsonValue::Array(vec![JsonValue::from(tag), payload])
}

fn convert_table(table: &Table) -> JsonValue {
    let mut entries = Vec::new();
    for (key, value) in table.iter() {
        if let Some(value) = convert_item(value) {
            entries.push(JsonValue::Array(vec![
                JsonValue::String(key.to_owned()),
                value,
            ]));
        }
    }
    tagged(TAG_TABLE, JsonValue::Array(entries))
}

fn convert_array_of_tables(tables: &ArrayOfTables) -> JsonValue {
    tagged(
        TAG_ARRAY,
        JsonValue::Array(tables.iter().map(convert_table).collect()),
    )
}

fn convert_item(item: &Item) -> Option<JsonValue> {
    match item {
        Item::None => None,
        Item::Value(value) => Some(convert_value(value)),
        Item::Table(table) => Some(convert_table(table)),
        Item::ArrayOfTables(tables) => Some(convert_array_of_tables(tables)),
    }
}

fn convert_value(value: &Value) -> JsonValue {
    match value {
        Value::String(value) => tagged(TAG_STRING, JsonValue::String(value.value().clone())),
        Value::Integer(value) => tagged(
            TAG_INTEGER,
            JsonValue::Number((*value.value()).into()),
        ),
        Value::Float(value) => tagged(TAG_FLOAT, JsonValue::String(raw_float(value))),
        Value::Boolean(value) => tagged(TAG_BOOLEAN, JsonValue::Bool(*value.value())),
        Value::Datetime(value) => {
            let datetime = value.value();
            let kind = if datetime.date.is_some() && datetime.time.is_some() {
                2
            } else if datetime.date.is_some() {
                0
            } else {
                1
            };
            tagged(
                TAG_DATETIME,
                JsonValue::Array(vec![
                    JsonValue::from(kind),
                    JsonValue::String(raw_datetime(value)),
                ]),
            )
        }
        Value::Array(array) => tagged(
            TAG_ARRAY,
            JsonValue::Array(array.iter().map(convert_value).collect()),
        ),
        Value::InlineTable(table) => {
            let mut entries = Vec::new();
            for (key, value) in table.iter() {
                entries.push(JsonValue::Array(vec![
                    JsonValue::String(key.to_owned()),
                    convert_value(value),
                ]));
            }
            tagged(TAG_TABLE, JsonValue::Array(entries))
        }
    }
}

unsafe fn py_none() -> *mut PyObject {
    let none = ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct);
    unsafe { cpython_sys::Py_IncRef(none) };
    none
}

unsafe fn parse_document(source: *mut PyObject) -> *mut PyObject {
    let mut source_len: Py_ssize_t = 0;
    let source_ptr = unsafe { PyUnicode_AsUTF8AndSize(source, &mut source_len) };
    if source_ptr.is_null() {
        unsafe { PyErr_Clear() };
        return unsafe { py_none() };
    }
    let source_bytes = unsafe {
        std::slice::from_raw_parts(source_ptr.cast::<u8>(), source_len as usize)
    };
    let source = match std::str::from_utf8(source_bytes) {
        Ok(source) => source,
        Err(_) => {
            unsafe {
                PyErr_SetString(
                    cpython_sys::PyExc_RuntimeError,
                    c"CPython returned non-UTF-8 TOML input".as_ptr(),
                );
            }
            return ptr::null_mut();
        }
    };
    let document = match source.parse::<DocumentMut>() {
        Ok(document) => document,
        Err(_) => return unsafe { py_none() },
    };

    let values = convert_table(document.as_table());
    let mut json = Vec::new();
    let mut serializer = serde_json::Serializer::new(&mut json);
    if values.serialize(&mut serializer).is_err() {
        unsafe {
            PyErr_SetString(
                cpython_sys::PyExc_RuntimeError,
                c"could not serialize parsed TOML values".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    unsafe { PyUnicode_FromStringAndSize(json.as_ptr().cast::<c_char>(), json.len() as Py_ssize_t) }
}

/// Parse one complete TOML document into recursively tagged JSON values.
///
/// Every TOML value is wrapped with its type so legal strings and keys cannot
/// collide with the boundary representation. Parsing and building the complete
/// TOML value tree happen in toml_edit.
pub unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(
                cpython_sys::PyExc_TypeError,
                c"_tomllib_rs.loads() takes exactly one argument".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    unsafe { parse_document(*args) }
}

pub extern "C" fn _tomllib_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _tomllib_rs_free(_o: *mut c_void) {}

pub struct ModuleDef {
    ffi: std::cell::UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _TOMLLIB_RS_MODULE_METHODS: [cpython_sys::PyMethodDef; 2] = [
    cpython_sys::PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: cpython_sys::PyMethodDefFuncPointer {
            PyCFunctionFast: loads,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a complete TOML document using toml_edit".as_ptr() as *mut c_char,
    },
    cpython_sys::PyMethodDef::zeroed(),
];

pub static _TOMLLIB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: std::cell::UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_tomllib_rs".as_ptr() as *mut _,
        m_doc: c"Rust implementation of complete TOML document parsing".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_TOMLLIB_RS_MODULE_METHODS as *const cpython_sys::PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_tomllib_rs_clear),
        m_free: Some(_tomllib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__tomllib_rs() -> *mut PyObject {
    _TOMLLIB_RS_MODULE.init_multi_phase()
}
