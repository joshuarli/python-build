use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyDict_New, PyDict_SetItem, PyErr_Clear,
    PyErr_ExceptionMatches, PyErr_SetString, PyFloat_FromString, PyImport_ImportModule,
    PyList_New, PyList_SetItem, PyLong_FromLongLong, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyObject_CallOneArg, PyObject_GetAttrString,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_DecRef, Py_ssize_t,
};
use toml_edit::{ArrayOfTables, DocumentMut, Formatted, Item, Table, Value};

/// Deepest nesting converted directly; deeper documents fall back to Python.
const MAX_DEPTH: usize = 128;

enum Fail {
    /// The Python parser must handle the document (or raise its error).
    Fallback,
    /// A Python exception is set and must propagate.
    Error,
}

type Built = Result<*mut PyObject, Fail>;

struct Ctx {
    /// Null when the default `float` is in use.
    parse_float: *mut PyObject,
    datetime: *mut PyObject,
    /// `fromisoformat` of `date`, `time`, and `datetime`, loaded on first use.
    constructors: [*mut PyObject; 3],
}

impl Drop for Ctx {
    fn drop(&mut self) {
        unsafe {
            for constructor in self.constructors {
                if !constructor.is_null() {
                    Py_DecRef(constructor);
                }
            }
            if !self.datetime.is_null() {
                Py_DecRef(self.datetime);
            }
        }
    }
}

fn check(object: *mut PyObject) -> Built {
    if object.is_null() { Err(Fail::Error) } else { Ok(object) }
}

unsafe fn new_str(text: &str) -> Built {
    check(unsafe {
        PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t)
    })
}

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

unsafe fn make_float(ctx: &Ctx, raw: &str) -> Built {
    let text = unsafe { new_str(raw)? };
    let result = if ctx.parse_float.is_null() {
        unsafe { PyFloat_FromString(text) }
    } else {
        unsafe { PyObject_CallOneArg(ctx.parse_float, text) }
    };
    unsafe { Py_DecRef(text) };
    check(result)
}

unsafe fn make_datetime(ctx: &mut Ctx, kind: usize, raw: &str) -> Built {
    if ctx.constructors[kind].is_null() {
        if ctx.datetime.is_null() {
            ctx.datetime = check(unsafe { PyImport_ImportModule(c"datetime".as_ptr()) })?;
        }
        let name = [c"date", c"time", c"datetime"][kind];
        let class = check(unsafe { PyObject_GetAttrString(ctx.datetime, name.as_ptr()) })?;
        let method = unsafe { PyObject_GetAttrString(class, c"fromisoformat".as_ptr()) };
        unsafe { Py_DecRef(class) };
        ctx.constructors[kind] = check(method)?;
    }
    let mut text = raw.to_owned();
    if kind == 2 {
        if let Some(index) = text.find('t') {
            text.replace_range(index..=index, "T");
        }
        if text.ends_with(['z', 'Z']) {
            text.truncate(text.len() - 1);
            text.push_str("+00:00");
        }
    }
    let text = unsafe { new_str(&text)? };
    let result = unsafe { PyObject_CallOneArg(ctx.constructors[kind], text) };
    unsafe { Py_DecRef(text) };
    if result.is_null() {
        if unsafe { PyErr_ExceptionMatches(cpython_sys::PyExc_ValueError) } != 0 {
            unsafe { PyErr_Clear() };
            return Err(Fail::Fallback);
        }
        return Err(Fail::Error);
    }
    Ok(result)
}

/// Insert `value` under `key`, consuming the value; on failure the dict is freed.
unsafe fn store(dict: *mut PyObject, key: &str, value: Built) -> Result<(), Fail> {
    let value = match value {
        Ok(value) => value,
        Err(fail) => {
            unsafe { Py_DecRef(dict) };
            return Err(fail);
        }
    };
    let key = match unsafe { new_str(key) } {
        Ok(key) => key,
        Err(fail) => {
            unsafe {
                Py_DecRef(value);
                Py_DecRef(dict);
            }
            return Err(fail);
        }
    };
    let status = unsafe { PyDict_SetItem(dict, key, value) };
    unsafe {
        Py_DecRef(key);
        Py_DecRef(value);
    }
    if status != 0 {
        unsafe { Py_DecRef(dict) };
        return Err(Fail::Error);
    }
    Ok(())
}

unsafe fn build_list<I>(len: usize, items: I) -> Built
where
    I: Iterator<Item = Built>,
{
    let list = check(unsafe { PyList_New(len as Py_ssize_t) })?;
    for (index, item) in items.enumerate() {
        let item = match item {
            Ok(item) => item,
            Err(fail) => {
                unsafe { Py_DecRef(list) };
                return Err(fail);
            }
        };
        if unsafe { PyList_SetItem(list, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(list) };
            return Err(Fail::Error);
        }
    }
    Ok(list)
}

unsafe fn build_table(ctx: &mut Ctx, table: &Table, depth: usize) -> Built {
    if depth > MAX_DEPTH {
        return Err(Fail::Fallback);
    }
    let dict = check(unsafe { PyDict_New() })?;
    for (key, item) in table.iter() {
        let value = match item {
            Item::None => continue,
            Item::Value(value) => unsafe { build_value(ctx, value, depth + 1) },
            Item::Table(table) => unsafe { build_table(ctx, table, depth + 1) },
            Item::ArrayOfTables(tables) => unsafe { build_tables(ctx, tables, depth + 1) },
        };
        unsafe { store(dict, key, value)? };
    }
    Ok(dict)
}

unsafe fn build_tables(ctx: &mut Ctx, tables: &ArrayOfTables, depth: usize) -> Built {
    unsafe {
        build_list(
            tables.len(),
            tables.iter().map(|table| build_table(ctx, table, depth + 1)),
        )
    }
}

unsafe fn build_value(ctx: &mut Ctx, value: &Value, depth: usize) -> Built {
    if depth > MAX_DEPTH {
        return Err(Fail::Fallback);
    }
    match value {
        Value::String(value) => unsafe { new_str(value.value()) },
        Value::Integer(value) => check(unsafe { PyLong_FromLongLong(*value.value()) }),
        Value::Float(value) => unsafe { make_float(ctx, &raw_float(value)) },
        Value::Boolean(value) => check(unsafe { PyBool_FromLong(*value.value() as _) }),
        Value::Datetime(value) => {
            let datetime = value.value();
            let kind = if datetime.date.is_some() && datetime.time.is_some() {
                2
            } else if datetime.date.is_some() {
                0
            } else {
                1
            };
            unsafe { make_datetime(ctx, kind, &raw_datetime(value)) }
        }
        Value::Array(array) => unsafe {
            build_list(
                array.len(),
                array.iter().map(|item| build_value(ctx, item, depth + 1)),
            )
        },
        Value::InlineTable(table) => {
            let dict = check(unsafe { PyDict_New() })?;
            for (key, item) in table.iter() {
                let item = unsafe { build_value(ctx, item, depth + 1) };
                unsafe { store(dict, key, item)? };
            }
            Ok(dict)
        }
    }
}

unsafe fn py_none() -> *mut PyObject {
    let none = ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct);
    unsafe { cpython_sys::Py_IncRef(none) };
    none
}

unsafe fn parse_document(source: *mut PyObject, parse_float: *mut PyObject) -> *mut PyObject {
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

    let float_type = ptr::addr_of_mut!(cpython_sys::PyFloat_Type).cast::<PyObject>();
    let mut ctx = Ctx {
        parse_float: if parse_float == float_type { ptr::null_mut() } else { parse_float },
        datetime: ptr::null_mut(),
        constructors: [ptr::null_mut(); 3],
    };
    match unsafe { build_table(&mut ctx, document.as_table(), 0) } {
        Ok(result) => result,
        Err(Fail::Fallback) => unsafe { py_none() },
        Err(Fail::Error) => ptr::null_mut(),
    }
}

/// Parse one complete TOML document into Python objects, or return None when
/// the Python parser must handle it. Floats go through `parse_float`.
pub unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                cpython_sys::PyExc_TypeError,
                c"_tomllib_rs.loads() takes exactly two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    unsafe { parse_document(*args, *args.add(1)) }
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
