#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_ulong, c_void};

use crate::ffi::{PyCFunction, PyObject, PyTypeObject, Py_ssize_t};

unsafe extern "C" {
    pub static mut PyExc_MemoryError: *mut PyObject;
    pub static mut PyExc_OSError: *mut PyObject;
    pub static mut PyExc_RuntimeError: *mut PyObject;
    pub static mut PyExc_ZeroDivisionError: *mut PyObject;
    pub static mut PyCFunction_Type: PyTypeObject;

    pub fn PyCFunction_GetFunction(object: *mut PyObject) -> Option<PyCFunction>;
    pub fn PyCFunction_GetSelf(object: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_Contains(dict: *mut PyObject, key: *mut PyObject) -> c_int;
    pub fn PyDict_GetItemString(dict: *mut PyObject, key: *const c_char) -> *mut PyObject;
    pub fn PyErr_CheckSignals() -> c_int;
    pub fn PyLong_AsInt(object: *mut PyObject) -> c_int;
    pub fn PyLong_AsNativeBytes(
        object: *mut PyObject,
        buffer: *mut c_void,
        size: Py_ssize_t,
        flags: c_int,
    ) -> Py_ssize_t;
    pub fn PyLong_AsUnsignedLongMask(object: *mut PyObject) -> c_ulong;
    pub fn PyLong_FromNativeBytes(buffer: *const c_void, size: usize, flags: c_int)
    -> *mut PyObject;
    pub fn PyLong_FromUnsignedLong(value: c_ulong) -> *mut PyObject;
    pub fn PyModule_GetDict(module: *mut PyObject) -> *mut PyObject;
    pub fn PyNumber_Index(object: *mut PyObject) -> *mut PyObject;
    pub fn PyUnicode_Concat(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    pub fn PyUnicode_New(size: Py_ssize_t, maxchar: u32) -> *mut PyObject;
    pub fn PyUnicode_ReadChar(object: *mut PyObject, index: Py_ssize_t) -> u32;
    pub fn PyUnicode_WriteChar(object: *mut PyObject, index: Py_ssize_t, character: u32) -> c_int;
}
