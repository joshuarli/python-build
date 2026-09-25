use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::io::Cursor;
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize, PyErr_Occurred,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyLong_AsLongLong, Py_NewRef, PyUnicode_AsUTF8AndSize,
    PyUnicode_FromStringAndSize, Py_ssize_t, _Py_NoneStruct,
};
use plist::{Date, Dictionary, Integer, Uid, Value};
use serde_json::{Value as JsonValue, json};

const XML_FORMAT: i64 = 0;
const BINARY_FORMAT: i64 = 1;

unsafe fn python_bytes(object: *mut PyObject) -> Option<Vec<u8>> {
    let mut data = ptr::null_mut();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(bytes.to_vec())
}

unsafe fn python_string(object: *mut PyObject) -> Option<String> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(String::from_utf8(bytes.to_vec()).expect("CPython UTF-8 is valid"))
}

unsafe fn python_result_json(value: &str) -> *mut PyObject {
    unsafe { PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t) }
}

unsafe fn python_result_bytes(value: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t) }
}

unsafe fn none_result() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

fn encoded_value(value: &Value) -> Option<JsonValue> {
    match value {
        Value::Array(values) => Some(json!([
            "a",
            values.iter().map(encoded_value).collect::<Option<Vec<_>>>()?
        ])),
        Value::Dictionary(values) => Some(json!([
            "o",
            values
                .iter()
                .map(|(key, item)| Some(json!([key, encoded_value(item)?])))
                .collect::<Option<Vec<_>>>()?
        ])),
        Value::Boolean(value) => Some(json!(["b", value])),
        Value::Data(value) => {
            let mut encoded = String::with_capacity(value.len() * 2);
            for byte in value {
                use std::fmt::Write;
                write!(&mut encoded, "{byte:02x}").ok()?;
            }
            Some(json!(["d", encoded]))
        }
        Value::Date(value) => Some(json!(["t", value.to_xml_format()])),
        Value::Real(value) => Some(json!(["f", value.to_string()])),
        Value::Integer(value) => {
            if let Some(signed) = value.as_signed() {
                Some(json!(["i", signed.to_string()]))
            } else {
                Some(json!(["i", value.as_unsigned()?.to_string()]))
            }
        }
        Value::String(value) => Some(json!(["s", value])),
        Value::Uid(value) => Some(json!(["u", value.get().to_string()])),
        _ => None,
    }
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if !value.len().is_multiple_of(2) {
        return None;
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let high = (pair[0] as char).to_digit(16)? as u8;
            let low = (pair[1] as char).to_digit(16)? as u8;
            Some((high << 4) | low)
        })
        .collect()
}

fn decoded_value(value: &JsonValue) -> Option<Value> {
    let fields = value.as_array()?;
    let tag = fields.first()?.as_str()?;
    let payload = fields.get(1)?;
    match tag {
        "a" => Some(Value::Array(
            payload
                .as_array()?
                .iter()
                .map(decoded_value)
                .collect::<Option<Vec<_>>>()?,
        )),
        "o" => {
            let mut dictionary = Dictionary::new();
            for pair in payload.as_array()? {
                let pair = pair.as_array()?;
                let key = pair.first()?.as_str()?.to_owned();
                let item = decoded_value(pair.get(1)?)?;
                dictionary.insert(key, item);
            }
            Some(Value::Dictionary(dictionary))
        }
        "b" => Some(Value::Boolean(payload.as_bool()?)),
        "d" => Some(Value::Data(decode_hex(payload.as_str()?)?)),
        "f" => Some(Value::Real(payload.as_str()?.parse().ok()?)),
        "i" => {
            let integer = payload.as_str()?;
            if let Ok(value) = integer.parse::<i64>() {
                Some(Value::Integer(Integer::from(value)))
            } else {
                Some(Value::Integer(Integer::from(integer.parse::<u64>().ok()?)))
            }
        }
        "s" => Some(Value::String(payload.as_str()?.to_owned())),
        "t" => Some(Value::Date(Date::from_xml_format(payload.as_str()?).ok()?)),
        "u" => Some(Value::Uid(Uid::new(payload.as_str()?.parse().ok()?))),
        _ => None,
    }
}

fn parse_plist(data: &[u8], format: i64) -> Option<Value> {
    match format {
        XML_FORMAT => Value::from_reader_xml(Cursor::new(data)).ok(),
        BINARY_FORMAT if data.starts_with(b"bplist00") => {
            Value::from_reader(Cursor::new(data)).ok()
        }
        _ => None,
    }
}

unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { return none_result() };
    }
    let Some(data) = (unsafe { python_bytes(*args) }) else {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { none_result() };
    };
    let format = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if format == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let Some(value) = parse_plist(&data, format) else {
        return unsafe { none_result() };
    };
    let Some(encoded) = encoded_value(&value) else {
        return unsafe { none_result() };
    };
    match serde_json::to_string(&encoded) {
        Ok(json) => unsafe { python_result_json(&json) },
        Err(_) => unsafe { none_result() },
    }
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { return none_result() };
    }
    let Some(encoded) = (unsafe { python_string(*args) }) else {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { none_result() };
    };
    let format = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if format == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let Ok(json) = serde_json::from_str::<JsonValue>(&encoded) else {
        return unsafe { none_result() };
    };
    let Some(value) = decoded_value(&json) else {
        return unsafe { none_result() };
    };
    let mut output = Vec::new();
    let result = match format {
        XML_FORMAT => value.to_writer_xml(&mut output),
        BINARY_FORMAT => value.to_writer_binary(&mut output),
        _ => return unsafe { none_result() },
    };
    if result.is_err() {
        return unsafe { none_result() };
    }
    if format == XML_FORMAT && !output.ends_with(b"\n") {
        output.push(b'\n');
    }
    unsafe { python_result_bytes(&output) }
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
        ml_doc: c"Parse a complete property list using the Rust plist library".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"dumps".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dumps },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a complete property list using the Rust plist library".as_ptr()
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
