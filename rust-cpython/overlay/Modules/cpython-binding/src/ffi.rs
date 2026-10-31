#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_long, c_void};

pub type Py_ssize_t = isize;

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
pub struct PyObject {
    pub ob_refcnt: Py_ssize_t,
    pub ob_type: *mut PyTypeObject,
}

pub type PyCFunction = unsafe extern "C" fn(*mut PyObject, *mut PyObject) -> *mut PyObject;
pub type PyCFunctionFast =
    unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject;
pub type visitproc = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int;

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunction: PyCFunction,
    pub PyCFunctionFast: PyCFunctionFast,
    pub void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    pub ml_name: *const c_char,
    pub ml_meth: PyMethodDefFuncPointer,
    pub ml_flags: c_int,
    pub ml_doc: *const c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
pub struct PyModuleDef_Base {
    pub ob_base: PyObject,
    pub m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    pub m_index: Py_ssize_t,
    pub m_copy: *mut PyObject,
}

#[repr(C)]
pub struct PyModuleDef_Slot {
    pub slot: c_int,
    pub value: *mut c_void,
}

unsafe impl Sync for PyModuleDef_Slot {}

#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, visitproc, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

#[repr(C)]
pub struct Py_buffer {
    pub buf: *mut c_void,
    pub obj: *mut PyObject,
    pub len: Py_ssize_t,
    pub itemsize: Py_ssize_t,
    pub readonly: c_int,
    pub ndim: c_int,
    pub format: *mut c_char,
    pub shape: *mut Py_ssize_t,
    pub strides: *mut Py_ssize_t,
    pub suboffsets: *mut Py_ssize_t,
    pub internal: *mut c_void,
}

#[repr(C)]
pub struct PyBytesWriter {
    _opaque: [u8; 0],
}

pub const METH_O: c_int = 0x0008;
pub const METH_NOARGS: c_int = 0x0004;
pub const METH_FASTCALL: c_int = 0x0080;

pub const PyBUF_SIMPLE: c_int = 0;

pub const Py_mod_multiple_interpreters: c_int = 86;
pub const Py_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2usize as *mut c_void;

/// `_Py_STATIC_IMMORTAL_INITIAL_REFCNT` of the 64-bit GIL-enabled build:
/// `(3 << 30) | ((_Py_STATICALLY_ALLOCATED_FLAG | _Py_IMMORTAL_FLAGS) << 48)`.
pub const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);

unsafe extern "C" {
    pub static mut _Py_NoneStruct: PyObject;
    pub static mut PyExc_IndexError: *mut PyObject;
    pub static mut PyExc_OverflowError: *mut PyObject;
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub static mut PyList_Type: PyTypeObject;
    pub static mut PyLong_Type: PyTypeObject;
    pub static mut PyTuple_Type: PyTypeObject;

    pub fn Py_DecRef(object: *mut PyObject);
    pub fn Py_GetConstant(constant_id: u32) -> *mut PyObject;
    pub fn Py_IncRef(object: *mut PyObject);
    pub fn Py_NewRef(object: *mut PyObject) -> *mut PyObject;

    pub fn PyBool_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn PyBytesWriter_Create(size: Py_ssize_t) -> *mut PyBytesWriter;
    pub fn PyBytesWriter_Discard(writer: *mut PyBytesWriter);
    pub fn PyBytesWriter_FinishWithSize(
        writer: *mut PyBytesWriter,
        size: Py_ssize_t,
    ) -> *mut PyObject;
    pub fn PyBytesWriter_GetData(writer: *mut PyBytesWriter) -> *mut c_void;
    pub fn PyBytesWriter_GetSize(writer: *mut PyBytesWriter) -> Py_ssize_t;
    pub fn PyBytesWriter_Grow(writer: *mut PyBytesWriter, size: Py_ssize_t) -> c_int;
    pub fn PyBytesWriter_WriteBytes(
        writer: *mut PyBytesWriter,
        bytes: *const c_void,
        size: Py_ssize_t,
    ) -> c_int;
    pub fn PyBytes_AsString(object: *mut PyObject) -> *mut c_char;
    pub fn PyBytes_AsStringAndSize(
        object: *mut PyObject,
        data: *mut *mut c_char,
        length: *mut Py_ssize_t,
    ) -> c_int;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyBytes_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyErr_Clear();
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub fn PyIter_Next(iterator: *mut PyObject) -> *mut PyObject;
    pub fn PyList_Append(list: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PyList_GetItem(list: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_SetItem(list: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    pub fn PyList_Size(list: *mut PyObject) -> Py_ssize_t;
    pub fn PyLong_AsLongLong(object: *mut PyObject) -> i64;
    pub fn PyLong_AsUnsignedLongLong(object: *mut PyObject) -> u64;
    pub fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    pub fn PyLong_FromSsize_t(value: Py_ssize_t) -> *mut PyObject;
    pub fn PyLong_FromUnsignedLongLong(value: u64) -> *mut PyObject;
    pub fn PyMem_Free(pointer: *mut c_void);
    pub fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyNumber_Subtract(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_CallOneArg(callable: *mut PyObject, arg: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetBuffer(object: *mut PyObject, view: *mut Py_buffer, flags: c_int)
    -> c_int;
    pub fn PyObject_GetItem(object: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetIter(object: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_IsTrue(object: *mut PyObject) -> c_int;
    pub fn PyObject_SetItem(object: *mut PyObject, key: *mut PyObject, value: *mut PyObject)
    -> c_int;
    pub fn PyObject_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PySequence_Contains(sequence: *mut PyObject, value: *mut PyObject) -> c_int;
    pub fn PyTuple_GetItem(tuple: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject)
    -> c_int;
    pub fn PyTuple_Size(tuple: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_AsUCS4(
        object: *mut PyObject,
        target: *mut u32,
        targetsize: Py_ssize_t,
        copy_null: c_int,
    ) -> *mut u32;
    pub fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t)
    -> *const c_char;
    pub fn PyUnicode_DecodeUTF8(
        data: *const c_char,
        size: Py_ssize_t,
        errors: *const c_char,
    ) -> *mut PyObject;
    pub fn PyUnicode_FromKindAndData(
        kind: c_int,
        buffer: *const c_void,
        size: Py_ssize_t,
    ) -> *mut PyObject;
    pub fn PyUnicode_FromStringAndSize(text: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyUnicode_GetLength(object: *mut PyObject) -> Py_ssize_t;
}
