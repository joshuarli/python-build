use std::collections::HashSet;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize,
    PyDict_New, PyDict_Next, PyDict_SetItem, PyErr_Clear, PyErr_ExceptionMatches,
    PyErr_NoMemory, PyErr_Occurred, PyErr_SetString, PyExc_TypeError,
    PyExc_UnicodeEncodeError, PyFloat_AsDouble, PyFloat_FromDouble, PyList_Append,
    PyList_GetItem, PyList_New, PyList_Size, PyLong_AsLong, PyLong_AsLongLong,
    PyLong_FromLongLong, PyMethodDef, PyMethodDefFuncPointer,
    PyABIInfo, PySlot, PySlot__bindgen_ty_1, PySlot__bindgen_ty_2,
    Py_mod_abi, Py_mod_doc, Py_mod_methods, Py_mod_name,
    Py_mod_state_clear, Py_mod_state_free, PySlot_INTPTR, PySlot_STATIC,
    PyObject, PyObject_Type, PyTuple_New,
    PyTuple_SetItem, PyTypeObject, PyUnicode_AsUTF8AndSize,
    PyUnicode_FromStringAndSize, Py_DecRef, Py_IncRef, PyBytes_Type, PyBool_Type,
    PyDict_Type, PyFloat_Type, PyList_Type, PyLong_Type, PyUnicode_Type, Py_ssize_t,
    _Py_NoneStruct,
};
use serde::de::{MapAccess, SeqAccess, Visitor};
use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};
use serde::{Deserialize, Deserializer};
use serde_pickle::{DeOptions, SerOptions, Value};

const MAX_DEPTH: usize = 128;
// Keep compact graphs on the Rust path. CPython's Pickler memoizes larger
// collections, so it retains its normal memo-table behavior beyond this size.
const MAX_GRAPH_NODES: usize = 100;
const MAX_VALUE_BYTES: usize = 32 * 1024;
const MAX_PICKLE_BYTES: usize = 32 * 1024;

#[derive(Default)]
struct EncodeBudget {
    nodes: usize,
    value_bytes: usize,
}

impl EncodeBudget {
    fn add_node(&mut self) -> bool {
        self.nodes += 1;
        self.nodes <= MAX_GRAPH_NODES
    }

    fn add_value_bytes(&mut self, size: usize) -> bool {
        let Some(total) = self.value_bytes.checked_add(size) else {
            return false;
        };
        self.value_bytes = total;
        total <= MAX_VALUE_BYTES
    }
}

/// A deliberately narrow value tree for common acyclic builtin containers.
/// `serde-pickle` owns opcode generation and parsing; objects outside this
/// tree stay with CPython's complete Pickler and Unpickler implementations.
enum PickleValue {
    None,
    Bool(bool),
    Int(i64),
    Float(f64),
    Bytes(Vec<u8>),
    String(String),
    List(Vec<PickleValue>),
    Dict(Vec<(PickleValue, PickleValue)>),
}

impl Serialize for PickleValue {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match self {
            Self::None => serializer.serialize_unit(),
            Self::Bool(value) => serializer.serialize_bool(*value),
            Self::Int(value) => serializer.serialize_i64(*value),
            Self::Float(value) => serializer.serialize_f64(*value),
            Self::Bytes(value) => serializer.serialize_bytes(value),
            Self::String(value) => serializer.serialize_str(value),
            Self::List(values) => {
                let mut sequence = serializer.serialize_seq(Some(values.len()))?;
                for value in values {
                    sequence.serialize_element(value)?;
                }
                sequence.end()
            }
            Self::Dict(entries) => {
                let mut map = serializer.serialize_map(Some(entries.len()))?;
                for (key, value) in entries {
                    map.serialize_entry(key, value)?;
                }
                map.end()
            }
        }
    }
}

impl<'de> Deserialize<'de> for PickleValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct PickleValueVisitor;

        impl<'de> Visitor<'de> for PickleValueVisitor {
            type Value = PickleValue;

            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("a supported builtin pickle value")
            }

            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(PickleValue::None)
            }

            fn visit_none<E>(self) -> Result<Self::Value, E> {
                Ok(PickleValue::None)
            }

            fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
                Ok(PickleValue::Bool(value))
            }

            fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
                Ok(PickleValue::Int(value))
            }

            fn visit_u64<E: serde::de::Error>(self, value: u64) -> Result<Self::Value, E> {
                i64::try_from(value)
                    .map(PickleValue::Int)
                    .map_err(serde::de::Error::custom)
            }

            fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E> {
                Ok(PickleValue::Float(value))
            }

            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
                Ok(PickleValue::String(value.to_owned()))
            }

            fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
                Ok(PickleValue::String(value))
            }

            fn visit_bytes<E>(self, value: &[u8]) -> Result<Self::Value, E> {
                Ok(PickleValue::Bytes(value.to_vec()))
            }

            fn visit_byte_buf<E>(self, value: Vec<u8>) -> Result<Self::Value, E> {
                Ok(PickleValue::Bytes(value))
            }

            fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(PickleValue::List(values))
            }

            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
                let mut entries = Vec::new();
                while let Some((key, value)) = map.next_entry()? {
                    entries.push((key, value));
                }
                Ok(PickleValue::Dict(entries))
            }
        }

        deserializer.deserialize_any(PickleValueVisitor)
    }
}

unsafe fn is_exact_type(object: *mut PyObject, expected: *mut PyTypeObject) -> Result<bool, ()> {
    let actual = unsafe { PyObject_Type(object) };
    if actual.is_null() {
        return Err(());
    }
    let matches = actual == expected.cast::<PyObject>();
    unsafe { Py_DecRef(actual) };
    Ok(matches)
}

unsafe fn encode_string(
    object: *mut PyObject,
    budget: &mut EncodeBudget,
) -> Result<Option<String>, ()> {
    let mut length = 0;
    let text = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if text.is_null() {
        if unsafe { PyErr_ExceptionMatches(PyExc_UnicodeEncodeError) } != 0 {
            unsafe { PyErr_Clear() };
            return Ok(None);
        }
        return Err(());
    }
    if length < 0 {
        unsafe { PyErr_Clear() };
        return Ok(None);
    }
    if !budget.add_value_bytes(length as usize) {
        return Ok(None);
    }
    let bytes = unsafe { slice::from_raw_parts(text.cast::<u8>(), length as usize) };
    match std::str::from_utf8(bytes) {
        Ok(text) => Ok(Some(text.to_owned())),
        Err(_) => Ok(None),
    }
}

unsafe fn encode_value(
    object: *mut PyObject,
    depth: usize,
    seen: &mut HashSet<usize>,
    budget: &mut EncodeBudget,
) -> Result<Option<PickleValue>, ()> {
    if depth > MAX_DEPTH || !budget.add_node() {
        return Ok(None);
    }
    if object == ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>() {
        return Ok(Some(PickleValue::None));
    }

    let bool_type = ptr::addr_of_mut!(PyBool_Type);
    if unsafe { is_exact_type(object, bool_type) }? {
        let value = unsafe { cpython_sys::PyObject_IsTrue(object) };
        return if value < 0 {
            Err(())
        } else {
            Ok(Some(PickleValue::Bool(value != 0)))
        };
    }

    let long_type = ptr::addr_of_mut!(PyLong_Type);
    if unsafe { is_exact_type(object, long_type) }? {
        let value = unsafe { PyLong_AsLongLong(object) };
        if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            unsafe { PyErr_Clear() };
            return Ok(None);
        }
        // The cached small integers are recreated as the same CPython
        // singletons; larger integers need memo identity preserved.
        if !(-5..=256).contains(&value) && !seen.insert(object as usize) {
            return Ok(None);
        }
        return Ok(Some(PickleValue::Int(value)));
    }

    let float_type = ptr::addr_of_mut!(PyFloat_Type);
    if unsafe { is_exact_type(object, float_type) }? {
        if !seen.insert(object as usize) {
            return Ok(None);
        }
        let value = unsafe { PyFloat_AsDouble(object) };
        if value == -1.0 && !unsafe { PyErr_Occurred() }.is_null() {
            return Err(());
        }
        return Ok(Some(PickleValue::Float(value)));
    }

    let unicode_type = ptr::addr_of_mut!(PyUnicode_Type);
    if unsafe { is_exact_type(object, unicode_type) }? {
        if !seen.insert(object as usize) {
            return Ok(None);
        }
        return unsafe { encode_string(object, budget) }.map(|text| text.map(PickleValue::String));
    }

    let bytes_type = ptr::addr_of_mut!(PyBytes_Type);
    if unsafe { is_exact_type(object, bytes_type) }? {
        if !seen.insert(object as usize) {
            return Ok(None);
        }
        let mut data = ptr::null_mut();
        let mut length = 0;
        if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
            return Err(());
        }
        if !budget.add_value_bytes(length as usize) {
            return Ok(None);
        }
        let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) }.to_vec();
        return Ok(Some(PickleValue::Bytes(bytes)));
    }

    let list_type = ptr::addr_of_mut!(PyList_Type);
    if unsafe { is_exact_type(object, list_type) }? {
        if !seen.insert(object as usize) {
            return Ok(None);
        }
        let length = unsafe { PyList_Size(object) };
        if length < 0 {
            return Err(());
        }
        let mut values = Vec::with_capacity(length as usize);
        for index in 0..length {
            let item = unsafe { PyList_GetItem(object, index) };
            if item.is_null() {
                return Err(());
            }
            let Some(value) = (unsafe { encode_value(item, depth + 1, seen, budget) })? else {
                return Ok(None);
            };
            values.push(value);
        }
        return Ok(Some(PickleValue::List(values)));
    }

    let dict_type = ptr::addr_of_mut!(PyDict_Type);
    if unsafe { is_exact_type(object, dict_type) }? {
        if !seen.insert(object as usize) {
            return Ok(None);
        }
        let mut position = 0;
        let mut entries = Vec::new();
        loop {
            let mut key = ptr::null_mut();
            let mut value = ptr::null_mut();
            if unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } == 0 {
                break;
            }
            let Some(key) = (unsafe { encode_value(key, depth + 1, seen, budget) })? else {
                return Ok(None);
            };
            if !matches!(
                key,
                PickleValue::None
                    | PickleValue::Bool(_)
                    | PickleValue::Int(_)
                    | PickleValue::Bytes(_)
                    | PickleValue::String(_)
            ) {
                return Ok(None);
            }
            let Some(value) = (unsafe { encode_value(value, depth + 1, seen, budget) })? else {
                return Ok(None);
            };
            entries.push((key, value));
        }
        return Ok(Some(PickleValue::Dict(entries)));
    }

    Ok(None)
}

fn stream_string(input: &[u8], cursor: &mut usize, length: usize) -> bool {
    match cursor.checked_add(length) {
        Some(end) if end <= input.len() => {
            *cursor = end;
            true
        }
        _ => false,
    }
}

fn stream_u32(input: &[u8], cursor: &mut usize) -> Option<usize> {
    let end = cursor.checked_add(4)?;
    let bytes: [u8; 4] = input.get(*cursor..end)?.try_into().ok()?;
    *cursor = end;
    Some(u32::from_le_bytes(bytes) as usize)
}

/// Recognize only non-memoized protocol 3+ opcodes emitted for the supported
/// value tree. Rejecting memo operations avoids changing shared-object or
/// recursive-graph identity when CPython can handle the full pickle stream.
fn supported_pickle_length(input: &[u8]) -> Option<usize> {
    if input.len() > MAX_PICKLE_BYTES
        || input.len() < 3
        || input[0] != 0x80
        || !matches!(input[1], 3..=5)
    {
        return None;
    }
    let mut cursor = 2;
    let mut depth = 0usize;
    while cursor < input.len() {
        let opcode = input[cursor];
        cursor += 1;
        match opcode {
            b'N' | 0x88 | 0x89 | b'(' => {}
            b'J' => {
                if !stream_string(input, &mut cursor, 4) {
                    return None;
                }
            }
            b'K' | b'C' => {
                let length = *input.get(cursor)? as usize;
                cursor += 1;
                if opcode == b'C' && !stream_string(input, &mut cursor, length) {
                    return None;
                }
            }
            b'M' => {
                if !stream_string(input, &mut cursor, 2) {
                    return None;
                }
            }
            b'G' => {
                if !stream_string(input, &mut cursor, 8) {
                    return None;
                }
            }
            b'X' | b'B' => {
                let length = stream_u32(input, &mut cursor)?;
                if !stream_string(input, &mut cursor, length) {
                    return None;
                }
            }
            0x8a => {
                let length = *input.get(cursor)? as usize;
                cursor += 1;
                if !stream_string(input, &mut cursor, length) {
                    return None;
                }
            }
            0x8b => {
                let length = stream_u32(input, &mut cursor)?;
                if !stream_string(input, &mut cursor, length) {
                    return None;
                }
            }
            b']' | b'}' => {
                if input.get(cursor) == Some(&b'(') {
                    depth += 1;
                    if depth > MAX_DEPTH {
                        return None;
                    }
                }
            }
            b'e' | b'u' => {
                if depth == 0 {
                    return None;
                }
                if input.get(cursor) != Some(&b'(') {
                    depth -= 1;
                }
            }
            b'.' if depth == 0 => return Some(cursor),
            _ => return None,
        }
    }
    None
}

fn supported_decoded_value(value: &Value, depth: usize) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    match value {
        Value::None | Value::Bool(_) | Value::I64(_) | Value::F64(_)
        | Value::Bytes(_) | Value::String(_) => true,
        Value::List(values) => values.iter().all(|value| supported_decoded_value(value, depth + 1)),
        Value::Dict(values) => values.iter().all(|(key, value)| {
            matches!(
                key,
                serde_pickle::HashableValue::None
                    | serde_pickle::HashableValue::Bool(_)
                    | serde_pickle::HashableValue::I64(_)
                    | serde_pickle::HashableValue::Bytes(_)
                    | serde_pickle::HashableValue::String(_)
            ) && supported_decoded_value(value, depth + 1)
        }),
        Value::Int(_) | Value::Tuple(_) | Value::Set(_) | Value::FrozenSet(_) => false,
    }
}

unsafe fn new_none() -> *mut PyObject {
    let object = ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>();
    unsafe { Py_IncRef(object) };
    object
}

unsafe fn new_unicode(text: &str) -> *mut PyObject {
    if text.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
}

unsafe fn decode_value(value: PickleValue, depth: usize) -> Result<*mut PyObject, ()> {
    if depth > MAX_DEPTH {
        return Err(());
    }
    match value {
        PickleValue::None => Ok(unsafe { new_none() }),
        PickleValue::Bool(value) => {
            let object = unsafe { PyBool_FromLong(if value { 1 } else { 0 }) };
            if object.is_null() { Err(()) } else { Ok(object) }
        }
        PickleValue::Int(value) => {
            let object = unsafe { PyLong_FromLongLong(value) };
            if object.is_null() { Err(()) } else { Ok(object) }
        }
        PickleValue::Float(value) => {
            let object = unsafe { PyFloat_FromDouble(value) };
            if object.is_null() { Err(()) } else { Ok(object) }
        }
        PickleValue::Bytes(value) => {
            if value.len() > Py_ssize_t::MAX as usize {
                unsafe { PyErr_NoMemory() };
                return Err(());
            }
            let object = unsafe {
                PyBytes_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t)
            };
            if object.is_null() { Err(()) } else { Ok(object) }
        }
        PickleValue::String(value) => {
            let object = unsafe { new_unicode(&value) };
            if object.is_null() { Err(()) } else { Ok(object) }
        }
        PickleValue::List(values) => {
            let list = unsafe { PyList_New(0) };
            if list.is_null() {
                return Err(());
            }
            for value in values {
                let item = match unsafe { decode_value(value, depth + 1) } {
                    Ok(item) => item,
                    Err(()) => {
                        unsafe { Py_DecRef(list) };
                        return Err(());
                    }
                };
                let status = unsafe { PyList_Append(list, item) };
                unsafe { Py_DecRef(item) };
                if status != 0 {
                    unsafe { Py_DecRef(list) };
                    return Err(());
                }
            }
            Ok(list)
        }
        PickleValue::Dict(entries) => {
            let dict = unsafe { PyDict_New() };
            if dict.is_null() {
                return Err(());
            }
            for (key, value) in entries {
                let key = match unsafe { decode_value(key, depth + 1) } {
                    Ok(key) => key,
                    Err(()) => {
                        unsafe { Py_DecRef(dict) };
                        return Err(());
                    }
                };
                let value = match unsafe { decode_value(value, depth + 1) } {
                    Ok(value) => value,
                    Err(()) => {
                        unsafe {
                            Py_DecRef(key);
                            Py_DecRef(dict);
                        }
                        return Err(());
                    }
                };
                let status = unsafe { PyDict_SetItem(dict, key, value) };
                unsafe {
                    Py_DecRef(key);
                    Py_DecRef(value);
                }
                if status != 0 {
                    unsafe { Py_DecRef(dict) };
                    return Err(());
                }
            }
            Ok(dict)
        }
    }
}

unsafe fn return_status(ok: bool, value: *mut PyObject, consumed: usize) -> *mut PyObject {
    if value.is_null() {
        return ptr::null_mut();
    }
    let tuple = unsafe { PyTuple_New(3) };
    if tuple.is_null() {
        unsafe { Py_DecRef(value) };
        return ptr::null_mut();
    }
    let flag = unsafe { PyBool_FromLong(if ok { 1 } else { 0 }) };
    let length = unsafe { PyLong_FromLongLong(consumed as i64) };
    if flag.is_null() || length.is_null() {
        unsafe {
            if !flag.is_null() { Py_DecRef(flag); }
            if !length.is_null() { Py_DecRef(length); }
            Py_DecRef(value);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, flag) } != 0 {
        unsafe {
            Py_DecRef(value);
            Py_DecRef(length);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 1, value) } != 0 {
        unsafe {
            Py_DecRef(length);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 2, length) } != 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

fn unsupported_status() -> *mut PyObject {
    unsafe { return_status(false, new_none(), 0) }
}

fn unsupported_dumps() -> *mut PyObject {
    unsafe { new_none() }
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"dumps() takes exactly two arguments".as_ptr()) };
        return ptr::null_mut();
    }
    let mut seen = HashSet::new();
    let mut budget = EncodeBudget::default();
    let value = match unsafe { encode_value(*args, 0, &mut seen, &mut budget) } {
        Ok(Some(value)) => value,
        Ok(None) => return unsupported_dumps(),
        Err(()) => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            return unsupported_dumps();
        }
    };
    let protocol_object = unsafe { *args.add(1) };
    let protocol = if protocol_object == ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>() {
        5
    } else {
        let is_integer = match unsafe { is_exact_type(protocol_object, ptr::addr_of_mut!(PyLong_Type)) } {
            Ok(is_integer) => is_integer,
            Err(()) => return ptr::null_mut(),
        };
        if !is_integer {
            return unsupported_dumps();
        }
        let value = unsafe { PyLong_AsLong(protocol_object) };
        if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            unsafe { PyErr_Clear() };
            return unsupported_dumps();
        }
        match value {
            -1 => 5,
            3..=5 => value as u8,
            _ => return unsupported_dumps(),
        }
    };
    let mut encoded = match serde_pickle::to_vec(&value, SerOptions::new()) {
        Ok(encoded) => encoded,
        Err(_) => return unsupported_dumps(),
    };
    if encoded.get(0) != Some(&0x80) || encoded.len() < 3 {
        return unsupported_dumps();
    }
    if encoded.len() > MAX_PICKLE_BYTES {
        return unsupported_dumps();
    }
    encoded[1] = protocol;
    if encoded.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(encoded.as_ptr().cast::<c_char>(), encoded.len() as Py_ssize_t)
    }
}

unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"loads() takes exactly one argument".as_ptr()) };
        return ptr::null_mut();
    }
    let input_object = unsafe { *args };
    match unsafe { is_exact_type(input_object, ptr::addr_of_mut!(PyBytes_Type)) } {
        Ok(true) => {}
        Ok(false) => return unsupported_status(),
        Err(()) => return ptr::null_mut(),
    }
    let mut data = ptr::null_mut();
    let mut length = 0;
    if unsafe { PyBytes_AsStringAndSize(input_object, &mut data, &mut length) } != 0 || length < 0 {
        unsafe { PyErr_Clear() };
        return unsupported_status();
    }
    let input = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let Some(consumed) = supported_pickle_length(input) else {
        return unsupported_status();
    };
    let input = &input[..consumed];
    let parsed = match serde_pickle::value_from_slice(input, DeOptions::new()) {
        Ok(parsed) if supported_decoded_value(&parsed, 0) => parsed,
        _ => return unsupported_status(),
    };
    drop(parsed);
    let value = match serde_pickle::from_slice::<PickleValue>(input, DeOptions::new()) {
        Ok(value) => value,
        Err(_) => return unsupported_status(),
    };
    match unsafe { decode_value(value, 0) } {
        Ok(value) => unsafe { return_status(true, value, consumed) },
        Err(()) => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                ptr::null_mut()
            } else {
                unsafe { PyErr_Clear() };
                unsupported_status()
            }
        }
    }
}

pub extern "C" fn _pickle_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _pickle_rs_free(_object: *mut c_void) {}

// CPython copies these immutable slots into each interpreter's module. The
// codec retains no Python objects or mutable state between calls.
struct ModuleSlots([PySlot; 8]);
unsafe impl Sync for ModuleSlots {}

// The non-stable ABI requires the locked CPython 3.16 GIL build. The loader
// checks the major/minor version and GIL compatibility; the source lock pins
// the full interpreter revision independently of the release-level bits.
static ABI_INFO: PyABIInfo = PyABIInfo {
    abiinfo_major_version: 1, abiinfo_minor_version: 0, flags: 2,
    build_version: 0x031000a0, abi_version: 0x031000a0,
};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("pickle slot export requires the supported 64-bit CPython ABI");

const _: () = {
    assert!(std::mem::size_of::<PySlot>() == 16);
    assert!(std::mem::align_of::<PySlot>() == 8);
    assert!(std::mem::offset_of!(PySlot, sl_id) == 0);
    assert!(std::mem::offset_of!(PySlot, sl_flags) == 2);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_1) == 4);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_2) == 8);
    assert!(std::mem::size_of::<PyABIInfo>() == 12);
    assert!(std::mem::align_of::<PyABIInfo>() == 4);
};

const fn data_slot(id: u32, value: *mut c_void) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: PySlot_INTPTR as u16,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: value } }
}

// Method definitions outlive each module: CPython retains their pointer after
// copying the slots, so the immutable table declares process-lifetime storage.
const fn static_data_slot(id: u32, value: *mut c_void) -> PySlot {
    let mut slot = data_slot(id, value);
    slot.sl_flags |= PySlot_STATIC as u16;
    slot
}

const fn function_slot(id: u32, value: unsafe extern "C" fn()) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_func: Some(value) } }
}

// The non-limited compatibility macro is omitted by the binding generator.
// The native header oracle verifies the interpreter's corresponding slot ID.
const MODULE_MULTIPLE_INTERPRETERS_SLOT: u16 = 86;

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"dumps".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dumps },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a supported builtin pickle graph".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: loads },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Deserialize a supported builtin pickle graph".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

// Omitted state-size, execution and traversal slots retain zero state and no
// execution/traversal hooks; the clear/free callbacks keep their original ABI.
static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    data_slot(Py_mod_abi, &ABI_INFO as *const PyABIInfo as *mut c_void),
    data_slot(Py_mod_name, c"_pickle_rs".as_ptr() as *mut c_void),
    data_slot(Py_mod_doc, c"Rust pickle codec for common builtin object graphs".as_ptr() as *mut c_void),
    static_data_slot(Py_mod_methods, METHODS.as_ptr() as *mut c_void),
    PySlot { sl_id: MODULE_MULTIPLE_INTERPRETERS_SLOT, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_uint64: 2 } },
    function_slot(Py_mod_state_clear, unsafe { std::mem::transmute::<
        extern "C" fn(*mut PyObject) -> c_int, unsafe extern "C" fn()>(_pickle_rs_clear) }),
    function_slot(Py_mod_state_free, unsafe { std::mem::transmute::<
        extern "C" fn(*mut c_void), unsafe extern "C" fn()>(_pickle_rs_free) }),
    PySlot { sl_id: 0, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: ptr::null_mut() } },
]);

#[unsafe(no_mangle)]
pub extern "C" fn PyModExport__pickle_rs() -> *mut PySlot {
    MODULE_SLOTS.0.as_ptr() as *mut PySlot
}
