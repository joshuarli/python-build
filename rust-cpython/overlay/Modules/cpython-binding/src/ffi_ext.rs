#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_long, c_ulong, c_void};

pub use crate::ffi::{Py_ssize_t, PyObject, PyTypeObject};

#[repr(C)]
pub struct PyThreadState {
    _opaque: [u8; 0],
}

pub type PyCapsule_Destructor = Option<unsafe extern "C" fn(*mut PyObject)>;

pub const Py_TPFLAGS_UNICODE_SUBCLASS: c_ulong = 1 << 28;

unsafe extern "C" {
    pub static mut PyExc_MemoryError: *mut PyObject;
    pub static mut PyExc_OSError: *mut PyObject;
    pub static mut PyExc_RuntimeError: *mut PyObject;
    pub static mut PyUnicode_Type: PyTypeObject;

    pub fn PyCapsule_GetPointer(capsule: *mut PyObject, name: *const c_char) -> *mut c_void;
    pub fn PyCapsule_New(
        pointer: *mut c_void,
        name: *const c_char,
        destructor: PyCapsule_Destructor,
    ) -> *mut PyObject;
    pub fn PyDict_Contains(dict: *mut PyObject, key: *mut PyObject) -> c_int;
    pub fn PyDict_GetItemWithError(dict: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_New() -> *mut PyObject;
    pub fn PyDict_SetItem(dict: *mut PyObject, key: *mut PyObject, value: *mut PyObject)
    -> c_int;
    pub fn PyErr_CheckSignals() -> c_int;
    pub fn PyErr_SetFromErrno(exception: *mut PyObject) -> *mut PyObject;
    pub fn PyEval_RestoreThread(state: *mut PyThreadState);
    pub fn PyEval_SaveThread() -> *mut PyThreadState;
    pub fn PyLong_AsLong(object: *mut PyObject) -> c_long;
    pub fn PyLong_AsSsize_t(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyLong_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyObject_CallNoArgs(callable: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetAttr(object: *mut PyObject, name: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetAttrString(object: *mut PyObject, name: *const c_char) -> *mut PyObject;
    pub fn PyObject_Vectorcall(
        callable: *mut PyObject,
        args: *const *mut PyObject,
        nargsf: usize,
        kwnames: *mut PyObject,
    ) -> *mut PyObject;
    pub fn PyType_GetFlags(class: *mut PyTypeObject) -> c_ulong;
    pub fn PyUnicode_InternFromString(text: *const c_char) -> *mut PyObject;
    pub fn _PyBytes_Resize(object: *mut *mut PyObject, size: Py_ssize_t) -> c_int;
}
