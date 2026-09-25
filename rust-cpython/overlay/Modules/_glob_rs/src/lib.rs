use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_O;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;

fn set_value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
    ptr::null_mut()
}

unsafe fn expand_impl(pattern_object: *mut PyObject) -> *mut PyObject {
    let mut size: Py_ssize_t = 0;
    let pattern_ptr = unsafe { PyUnicode_AsUTF8AndSize(pattern_object, &mut size) };
    if pattern_ptr.is_null() {
        return ptr::null_mut();
    }
    if size < 0 {
        return set_value_error(c"glob pattern has a negative encoded length");
    }
    let pattern_bytes = unsafe { slice::from_raw_parts(pattern_ptr.cast::<u8>(), size as usize) };
    let pattern = unsafe { std::str::from_utf8_unchecked(pattern_bytes) };

    let options = glob::MatchOptions {
        case_sensitive: true,
        require_literal_separator: true,
        // The Python boundary applies hidden-file rules per path component.
        require_literal_leading_dot: false,
    };
    let paths = match glob::glob_with(pattern, options) {
        Ok(paths) => paths,
        Err(_) => return set_value_error(c"glob pattern requires the Python fallback"),
    };
    let mut matches = Vec::new();
    for result in paths {
        let Ok(path) = result else {
            continue;
        };
        let Some(path) = path.to_str() else {
            return set_value_error(c"glob result requires the Python fallback");
        };
        matches.push(path.to_owned());
    }

    if matches.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let result = unsafe { PyList_New(matches.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, path) in matches.iter().enumerate() {
        if path.len() > Py_ssize_t::MAX as usize {
            unsafe { Py_DecRef(result) };
            unsafe { PyErr_NoMemory() };
            return ptr::null_mut();
        }
        let item = unsafe {
            PyUnicode_FromStringAndSize(path.as_ptr().cast::<c_char>(), path.len() as Py_ssize_t)
        };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyList_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

unsafe extern "C" fn expand(_module: *mut PyObject, pattern: *mut PyObject) -> *mut PyObject {
    unsafe { expand_impl(pattern) }
}

pub extern "C" fn _glob_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _glob_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _GLOB_RS_MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"expand".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: expand },
        ml_flags: METH_O,
        ml_doc: c"Expand a supported text pathname pattern.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _GLOB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_glob_rs".as_ptr() as *mut _,
        m_doc: c"Rust pathname expansion using the glob crate.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_GLOB_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_glob_rs_clear),
        m_free: Some(_glob_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__glob_rs() -> *mut PyObject {
    _GLOB_RS_MODULE.init_multi_phase()
}
