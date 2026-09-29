use std::cell::UnsafeCell;
use std::collections::HashSet;
use std::ffi::{c_char, c_int, c_void};
use std::io::Cursor;
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyBool_Type, PyByteArray_AsString, PyByteArray_Size,
    PyByteArray_Type, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize, PyBytes_Type,
    PyDict_New, PyDict_Next, PyDict_SetItem, PyDict_Size, PyDict_Type, PyErr_Clear, PyErr_Occurred,
    PyFloat_AsDouble, PyFloat_FromDouble, PyFloat_Type, PyList_GetItem, PyList_New,
    PyList_SetItem, PyList_Size, PyList_Type, PyLong_AsLongLong, PyLong_AsLongLongAndOverflow,
    PyLong_AsUnsignedLongLong, PyLong_FromLongLong, PyLong_FromUnsignedLongLong, PyLong_Type,
    PyMapping_Items, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyObject_CallOneArg, PyObject_GetAttrString,
    PyObject_IsInstance, PyObject_IsTrue, PyObject_RichCompareBool, PyTuple_GetItem, PyTuple_Size, PyTuple_Type,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, PyUnicode_Type, Py_DecRef, Py_NewRef,
    Py_EQ, Py_ssize_t, _Py_NoneStruct, _Py_TrueStruct,
};
use plist::{Date, Dictionary, Integer, Uid, Value};

const XML_FORMAT: i64 = 0;
const BINARY_FORMAT: i64 = 1;

unsafe fn python_bytes<'a>(object: *mut PyObject) -> Option<&'a [u8]> {
    let mut data = ptr::null_mut();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
        return None;
    }
    Some(unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) })
}

unsafe fn python_result_str(value: &str) -> *mut PyObject {
    unsafe { PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t) }
}

unsafe fn python_result_bytes(value: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t) }
}

unsafe fn none_result() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

const MAX_BUILD_DEPTH: usize = 256;

struct Builder {
    uid_class: *mut PyObject,
    date_parser: *mut PyObject,
}

impl Builder {
    /// Build the Python object for `value`. A null result with no exception
    /// set means the value is unsupported and the caller falls back to Python.
    unsafe fn build(&self, value: &Value, depth: usize) -> *mut PyObject {
        if depth > MAX_BUILD_DEPTH {
            return ptr::null_mut();
        }
        match value {
            Value::Array(values) => {
                let list = unsafe { PyList_New(values.len() as Py_ssize_t) };
                if list.is_null() {
                    return list;
                }
                for (index, item) in values.iter().enumerate() {
                    let object = unsafe { self.build(item, depth + 1) };
                    if object.is_null() {
                        unsafe { Py_DecRef(list) };
                        return ptr::null_mut();
                    }
                    unsafe { PyList_SetItem(list, index as Py_ssize_t, object) };
                }
                list
            }
            Value::Dictionary(values) => {
                let dict = unsafe { PyDict_New() };
                if dict.is_null() {
                    return dict;
                }
                for (key, item) in values.iter() {
                    let key = unsafe {
                        PyUnicode_FromStringAndSize(
                            key.as_ptr().cast::<c_char>(),
                            key.len() as Py_ssize_t,
                        )
                    };
                    if key.is_null() {
                        unsafe { Py_DecRef(dict) };
                        return ptr::null_mut();
                    }
                    let object = unsafe { self.build(item, depth + 1) };
                    if object.is_null() {
                        unsafe {
                            Py_DecRef(key);
                            Py_DecRef(dict);
                        }
                        return ptr::null_mut();
                    }
                    let status = unsafe { PyDict_SetItem(dict, key, object) };
                    unsafe {
                        Py_DecRef(key);
                        Py_DecRef(object);
                    }
                    if status != 0 {
                        unsafe { Py_DecRef(dict) };
                        return ptr::null_mut();
                    }
                }
                dict
            }
            Value::Boolean(value) => unsafe { PyBool_FromLong(*value as _) },
            Value::Data(value) => unsafe { python_result_bytes(value) },
            Value::Date(value) => {
                let text = value.to_xml_format();
                let text = text.strip_suffix('Z').unwrap_or(&text);
                let text = unsafe { python_result_str(text) };
                if text.is_null() {
                    return text;
                }
                let result = unsafe { PyObject_CallOneArg(self.date_parser, text) };
                unsafe { Py_DecRef(text) };
                result
            }
            Value::Real(value) => unsafe { PyFloat_FromDouble(*value) },
            Value::Integer(value) => {
                if let Some(signed) = value.as_signed() {
                    unsafe { PyLong_FromLongLong(signed) }
                } else if let Some(unsigned) = value.as_unsigned() {
                    unsafe { PyLong_FromUnsignedLongLong(unsigned) }
                } else {
                    ptr::null_mut()
                }
            }
            Value::String(value) => unsafe { python_result_str(value) },
            Value::Uid(value) => {
                let number = unsafe { PyLong_FromUnsignedLongLong(value.get()) };
                if number.is_null() {
                    return number;
                }
                let result = unsafe { PyObject_CallOneArg(self.uid_class, number) };
                unsafe { Py_DecRef(number) };
                result
            }
            _ => ptr::null_mut(),
        }
    }
}

const MAX_WALK_DEPTH: usize = 64;

struct Walker {
    binary: bool,
    sort_keys: bool,
    skipkeys: bool,
    uid_class: *mut PyObject,
    frozendict_class: *mut PyObject,
    datetime_class: *mut PyObject,
    date_string: *mut PyObject,
    active: HashSet<usize>,
    seen: HashSet<usize>,
}

/// `Ok(None)` means the value is unsupported (the caller falls back to
/// Python); `Err` means a Python exception is set and must propagate.
type Walked = Result<Option<Value>, ()>;

unsafe fn utf8_of<'a>(object: *mut PyObject) -> Option<&'a str> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    std::str::from_utf8(bytes).ok()
}

unsafe fn type_of(object: *mut PyObject) -> *mut PyObject {
    unsafe { (*object.cast::<cpython_sys::_object>()).ob_type }.cast::<PyObject>()
}

impl Walker {
    unsafe fn convert(&mut self, object: *mut PyObject, depth: usize) -> Walked {
        if depth > MAX_WALK_DEPTH {
            return Ok(None);
        }
        let kind = unsafe { type_of(object) };
        if kind == ptr::addr_of_mut!(PyBool_Type).cast::<PyObject>() {
            let truth = object == ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>();
            return Ok(Some(Value::Boolean(truth)));
        }
        if kind == ptr::addr_of_mut!(PyLong_Type).cast::<PyObject>() {
            let mut overflow: c_int = 0;
            let signed = unsafe { PyLong_AsLongLongAndOverflow(object, &mut overflow) };
            if overflow == 0 {
                if signed == -1 && !unsafe { PyErr_Occurred() }.is_null() {
                    unsafe { PyErr_Clear() };
                    return Ok(None);
                }
                return Ok(Some(Value::Integer(Integer::from(signed))));
            }
            if overflow < 0 {
                return Ok(None);
            }
            let unsigned = unsafe { PyLong_AsUnsignedLongLong(object) };
            if unsigned == u64::MAX && !unsafe { PyErr_Occurred() }.is_null() {
                unsafe { PyErr_Clear() };
                return Ok(None);
            }
            return Ok(Some(Value::Integer(Integer::from(unsigned))));
        }
        if kind == ptr::addr_of_mut!(PyFloat_Type).cast::<PyObject>() {
            let value = unsafe { PyFloat_AsDouble(object) };
            if !value.is_finite() {
                return Ok(None);
            }
            return Ok(Some(Value::Real(value)));
        }
        if kind == ptr::addr_of_mut!(PyUnicode_Type).cast::<PyObject>() {
            return Ok(unsafe { utf8_of(object) }.map(|text| Value::String(text.to_owned())));
        }
        if kind == ptr::addr_of_mut!(PyBytes_Type).cast::<PyObject>() {
            return Ok(unsafe { python_bytes(object) }.map(|bytes| Value::Data(bytes.to_vec())));
        }
        if kind == ptr::addr_of_mut!(PyByteArray_Type).cast::<PyObject>() {
            let length = unsafe { PyByteArray_Size(object) };
            let data = unsafe { PyByteArray_AsString(object) };
            if length < 0 || data.is_null() {
                unsafe { PyErr_Clear() };
                return Ok(None);
            }
            let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
            return Ok(Some(Value::Data(bytes.to_vec())));
        }
        if kind == self.datetime_class {
            let text = unsafe { PyObject_CallOneArg(self.date_string, object) };
            if text.is_null() {
                return Err(());
            }
            let date = unsafe { utf8_of(text) }.and_then(|text| Date::from_xml_format(text).ok());
            unsafe { Py_DecRef(text) };
            return Ok(date.map(Value::Date));
        }
        if kind == self.uid_class {
            if !self.binary {
                return Ok(None);
            }
            let data = unsafe { PyObject_GetAttrString(object, c"data".as_ptr()) };
            if data.is_null() {
                return Err(());
            }
            let mut number = None;
            if unsafe { type_of(data) } == ptr::addr_of_mut!(PyLong_Type).cast::<PyObject>() {
                let value = unsafe { PyLong_AsUnsignedLongLong(data) };
                if value == u64::MAX && !unsafe { PyErr_Occurred() }.is_null() {
                    unsafe { PyErr_Clear() };
                } else {
                    number = Some(value);
                }
            }
            unsafe { Py_DecRef(data) };
            return Ok(number.map(|value| Value::Uid(Uid::new(value))));
        }
        let is_dict = kind == ptr::addr_of_mut!(PyDict_Type).cast::<PyObject>();
        let is_frozen = kind == self.frozendict_class;
        let is_list = kind == ptr::addr_of_mut!(PyList_Type).cast::<PyObject>();
        let is_tuple = kind == ptr::addr_of_mut!(PyTuple_Type).cast::<PyObject>();
        if !(is_dict || is_frozen || is_list || is_tuple) {
            return Ok(None);
        }
        let identity = object as usize;
        if self.active.contains(&identity) || (self.binary && self.seen.contains(&identity)) {
            return Ok(None);
        }
        self.active.insert(identity);
        if self.binary {
            self.seen.insert(identity);
        }
        let result = if is_dict || is_frozen {
            unsafe { self.convert_mapping(object, is_frozen, depth) }
        } else {
            unsafe { self.convert_sequence(object, is_list, depth) }
        };
        self.active.remove(&identity);
        result
    }

    unsafe fn convert_sequence(&mut self, object: *mut PyObject, is_list: bool, depth: usize) -> Walked {
        let length = unsafe {
            if is_list { PyList_Size(object) } else { PyTuple_Size(object) }
        };
        if length < 0 {
            unsafe { PyErr_Clear() };
            return Ok(None);
        }
        let mut values = Vec::with_capacity(length as usize);
        for index in 0..length {
            let item = unsafe {
                if is_list { PyList_GetItem(object, index) } else { PyTuple_GetItem(object, index) }
            };
            if item.is_null() {
                unsafe { PyErr_Clear() };
                return Ok(None);
            }
            match unsafe { self.convert(item, depth + 1) }? {
                Some(value) => values.push(value),
                None => return Ok(None),
            }
        }
        Ok(Some(Value::Array(values)))
    }

    unsafe fn convert_mapping(&mut self, object: *mut PyObject, is_frozen: bool, depth: usize) -> Walked {
        let mut entries: Vec<(*mut PyObject, *mut PyObject)> = Vec::new();
        // Owner of the borrowed entry pointers for the frozendict snapshot.
        let mut owner: *mut PyObject = ptr::null_mut();
        if is_frozen {
            owner = unsafe { PyMapping_Items(object) };
            if owner.is_null() {
                return Err(());
            }
            let length = unsafe { PyList_Size(owner) };
            for index in 0..length.max(0) {
                let pair = unsafe { PyList_GetItem(owner, index) };
                let key = unsafe { PyTuple_GetItem(pair, 0) };
                let value = unsafe { PyTuple_GetItem(pair, 1) };
                if key.is_null() || value.is_null() {
                    unsafe {
                        PyErr_Clear();
                        Py_DecRef(owner);
                    }
                    return Ok(None);
                }
                entries.push((key, value));
            }
        } else {
            let mut position: Py_ssize_t = 0;
            let mut key = ptr::null_mut();
            let mut value = ptr::null_mut();
            while unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } != 0 {
                entries.push((key, value));
            }
        }
        let result = unsafe { self.convert_entries(&entries, depth) };
        if !owner.is_null() {
            unsafe { Py_DecRef(owner) };
        }
        result
    }

    unsafe fn convert_entries(&mut self, entries: &[(*mut PyObject, *mut PyObject)], depth: usize) -> Walked {
        let string_type = ptr::addr_of_mut!(PyUnicode_Type).cast::<PyObject>();
        let mut keyed: Vec<(&str, *mut PyObject)> = Vec::with_capacity(entries.len());
        for &(key, value) in entries {
            if unsafe { type_of(key) } != string_type {
                let instance = unsafe { PyObject_IsInstance(key, string_type) };
                if instance != 0 {
                    if instance < 0 {
                        unsafe { PyErr_Clear() };
                    }
                    return Ok(None);
                }
                if self.skipkeys {
                    continue;
                }
                return Ok(None);
            }
            let Some(text) = (unsafe { utf8_of(key) }) else {
                return Ok(None);
            };
            keyed.push((text, value));
        }
        if self.sort_keys {
            keyed.sort_by(|left, right| left.0.cmp(right.0));
        }
        let mut dictionary = Dictionary::new();
        for (key, value) in keyed {
            match unsafe { self.convert(value, depth + 1) }? {
                Some(item) => {
                    dictionary.insert(key.to_owned(), item);
                }
                None => return Ok(None),
            }
        }
        Ok(Some(Value::Dictionary(dictionary)))
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
    if nargs != 4 {
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
    let Some(value) = parse_plist(data, format) else {
        return unsafe { none_result() };
    };
    let builder = Builder {
        uid_class: unsafe { *args.add(2) },
        date_parser: unsafe { *args.add(3) },
    };
    let object = unsafe { builder.build(&value, 0) };
    if object.is_null() && unsafe { PyErr_Occurred() }.is_null() {
        return unsafe { none_result() };
    }
    object
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 8 {
        unsafe { return none_result() };
    }
    let format = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if format == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let sort_keys = unsafe { PyObject_IsTrue(*args.add(2)) };
    let skipkeys = unsafe { PyObject_IsTrue(*args.add(3)) };
    if sort_keys < 0 || skipkeys < 0 {
        return ptr::null_mut();
    }
    if format != XML_FORMAT && format != BINARY_FORMAT {
        return unsafe { none_result() };
    }
    let mut walker = Walker {
        binary: format == BINARY_FORMAT,
        sort_keys: sort_keys != 0,
        skipkeys: skipkeys != 0,
        uid_class: unsafe { *args.add(4) },
        frozendict_class: unsafe { *args.add(5) },
        datetime_class: unsafe { *args.add(6) },
        date_string: unsafe { *args.add(7) },
        active: HashSet::new(),
        seen: HashSet::new(),
    };
    let value = match unsafe { walker.convert(*args, 0) } {
        Ok(Some(value)) => value,
        Ok(None) => return unsafe { none_result() },
        Err(()) => return ptr::null_mut(),
    };
    let mut output = Vec::new();
    let result = if format == XML_FORMAT {
        value.to_writer_xml(&mut output)
    } else {
        value.to_writer_binary(&mut output)
    };
    if result.is_err() {
        return unsafe { none_result() };
    }
    if format == XML_FORMAT && !output.ends_with(b"\n") {
        output.push(b'\n');
    }
    unsafe { python_result_bytes(&output) }
}

const MAX_GRAPH_DEPTH: usize = 512;

/// Compares two object graphs for the same shape and sharing. `candidate` is
/// built fresh by `loads`, so its containers and most leaves are unshared; any
/// container reached twice in `original`, or leaf identity that maps
/// inconsistently, means the graphs differ. Leaves referenced exactly once are
/// necessarily unshared, so only shared or immortal leaves are recorded.
struct GraphCheck {
    containers: HashSet<usize>,
    shared: Vec<(usize, usize)>,
}

unsafe fn reference_count(object: *mut PyObject) -> i64 {
    unsafe { (*object.cast::<cpython_sys::_object>()).__bindgen_anon_1.ob_refcnt_full }
}

impl GraphCheck {
    unsafe fn leaf(&mut self, left: *mut PyObject, right: *mut PyObject) {
        if unsafe { reference_count(left) != 1 || reference_count(right) != 1 } {
            self.shared.push((left as usize, right as usize));
        }
    }

    unsafe fn same(&mut self, left: *mut PyObject, right: *mut PyObject, depth: usize) -> bool {
        if depth > MAX_GRAPH_DEPTH {
            return false;
        }
        let kind = unsafe { type_of(left) };
        if kind != unsafe { type_of(right) } {
            return false;
        }
        let is_dict = kind == ptr::addr_of_mut!(PyDict_Type).cast::<PyObject>();
        let is_list = kind == ptr::addr_of_mut!(PyList_Type).cast::<PyObject>();
        if !is_dict && !is_list {
            unsafe { self.leaf(left, right) };
            return true;
        }
        if !self.containers.insert(left as usize) {
            return false;
        }
        if is_list {
            let length = unsafe { PyList_Size(left) };
            if length < 0 || length != unsafe { PyList_Size(right) } {
                unsafe { PyErr_Clear() };
                return false;
            }
            for index in 0..length {
                let (a, b) = unsafe { (PyList_GetItem(left, index), PyList_GetItem(right, index)) };
                if a.is_null() || b.is_null() {
                    unsafe { PyErr_Clear() };
                    return false;
                }
                if !unsafe { self.same(a, b, depth + 1) } {
                    return false;
                }
            }
            return true;
        }
        if unsafe { PyDict_Size(left) != PyDict_Size(right) } {
            return false;
        }
        let (mut left_position, mut right_position): (Py_ssize_t, Py_ssize_t) = (0, 0);
        loop {
            let (mut left_key, mut left_value) = (ptr::null_mut(), ptr::null_mut());
            let (mut right_key, mut right_value) = (ptr::null_mut(), ptr::null_mut());
            let more = unsafe {
                PyDict_Next(left, &mut left_position, &mut left_key, &mut left_value)
            };
            let other = unsafe {
                PyDict_Next(right, &mut right_position, &mut right_key, &mut right_value)
            };
            if more == 0 || other == 0 {
                return more == other;
            }
            let equal = unsafe { PyObject_RichCompareBool(left_key, right_key, Py_EQ as c_int) };
            if equal != 1 || unsafe { type_of(left_key) != type_of(right_key) } {
                unsafe { PyErr_Clear() };
                return false;
            }
            unsafe { self.leaf(left_key, right_key) };
            if !unsafe { self.same(left_value, right_value, depth + 1) } {
                return false;
            }
        }
    }

    /// True when every object that occurs more than once maps to exactly one
    /// counterpart, in both directions.
    fn consistent(&mut self) -> bool {
        self.shared.sort_unstable();
        self.shared.dedup();
        if self.shared.windows(2).any(|pair| pair[0].0 == pair[1].0) {
            return false;
        }
        self.shared.sort_unstable_by_key(|pair| pair.1);
        !self.shared.windows(2).any(|pair| pair[0].1 == pair[1].1)
    }
}

unsafe extern "C" fn same_graph(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { return none_result() };
    }
    let mut check = GraphCheck { containers: HashSet::new(), shared: Vec::new() };
    let same = unsafe { check.same(*args, *args.add(1), 0) } && check.consistent();
    unsafe { PyBool_FromLong(same as _) }
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

pub static _PLISTLIB_RS_MODULE_METHODS: [PyMethodDef; 4] = [
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
    PyMethodDef {
        ml_name: c"same_graph".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: same_graph },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compare two property-list object graphs for shape and sharing".as_ptr()
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
