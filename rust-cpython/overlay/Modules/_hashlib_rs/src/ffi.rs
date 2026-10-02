#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

#[cfg(not(target_pointer_width = "64"))]
compile_error!("hash contexts require the 64-bit GIL-enabled CPython object ABI");

use core::ffi::{c_char, c_int, c_long, c_uint, c_void};
use core::ptr;

pub type Py_ssize_t = isize;

// These declarations describe the 64-bit GIL-enabled CPython object ABI.
#[repr(C)]
pub struct PyObject {
    pub ob_refcnt: Py_ssize_t,
    pub ob_type: *mut PyTypeObject,
}

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunction: unsafe extern "C" fn(*mut PyObject, *mut PyObject) -> *mut PyObject,
    pub Void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    pub ml_name: *mut c_char,
    pub ml_meth: PyMethodDefFuncPointer,
    pub ml_flags: c_int,
    pub ml_doc: *mut c_char,
}

impl PyMethodDef {
    pub const fn zeroed() -> Self {
        Self {
            ml_name: ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer { Void: ptr::null_mut() },
            ml_flags: 0,
            ml_doc: ptr::null_mut(),
        }
    }
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
pub struct PyGetSetDef {
    pub name: *const c_char,
    pub get: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void) -> *mut PyObject>,
    pub set: Option<unsafe extern "C" fn(*mut PyObject, *mut PyObject, *mut c_void) -> c_int>,
    pub doc: *const c_char,
    pub closure: *mut c_void,
}

#[repr(C)]
pub struct PyType_Slot {
    pub slot: c_int,
    pub pfunc: *mut c_void,
}

#[repr(C)]
pub struct PyType_Spec {
    pub name: *const c_char,
    pub basicsize: c_int,
    pub itemsize: c_int,
    pub flags: c_uint,
    pub slots: *mut PyType_Slot,
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

#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(
        *mut PyObject,
        Option<unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int>,
        *mut c_void,
    ) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

pub const METH_VARARGS: c_int = 0x0001;
pub const METH_NOARGS: c_int = 0x0004;
pub const METH_O: c_int = 0x0008;
pub const Py_tp_dealloc: c_int = 52;
pub const Py_tp_hash: c_int = 59;
pub const Py_tp_methods: c_int = 64;
pub const Py_tp_repr: c_int = 66;
pub const Py_tp_getset: c_int = 73;
pub const Py_TPFLAGS_DEFAULT: c_uint = 0;
pub const Py_TPFLAGS_DISALLOW_INSTANTIATION: c_uint = 1 << 7;
pub const Py_TPFLAGS_IMMUTABLETYPE: c_uint = 1 << 8;

// Static objects combine the immortal count with the static and immortal flags.
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject {
        ob_refcnt: (3_isize << 30) | (5_isize << 48),
        ob_type: ptr::null_mut(),
    },
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    pub static mut _Py_NoneStruct: PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub static mut PyExc_TypeError: *mut PyObject;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub fn PyLong_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyModule_AddObject(module: *mut PyObject, name: *const c_char, value: *mut PyObject) -> c_int;
    pub fn PyModuleDef_Init(definition: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyObject_Free(object: *mut c_void);
    pub fn PyObject_GetAttrString(object: *mut PyObject, name: *const c_char) -> *mut PyObject;
    pub fn PyObject_GetBuffer(object: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    pub fn PyObject_HashNotImplemented(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyObject_Type(object: *mut PyObject) -> *mut PyObject;
    pub fn PyType_FromSpec(specification: *mut PyType_Spec) -> *mut PyObject;
    pub fn PyType_GenericAlloc(type_object: *mut PyTypeObject, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    pub fn PyUnicode_FromFormat(format: *const c_char, ...) -> *mut PyObject;
    pub fn PyUnicode_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyTuple_GetItem(object: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn Py_NewRef(object: *mut PyObject) -> *mut PyObject;
    pub fn Py_DecRef(object: *mut PyObject);
    pub fn malloc(size: usize) -> *mut c_void;
    pub fn free(pointer: *mut c_void);
    pub fn abort() -> !;
}

const _: () = {
    assert!(core::mem::size_of::<PyObject>() == 16);
    assert!(core::mem::size_of::<Py_buffer>() == 80);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::size_of::<PyGetSetDef>() == 40);
    assert!(core::mem::size_of::<PyType_Spec>() == 32);
};
