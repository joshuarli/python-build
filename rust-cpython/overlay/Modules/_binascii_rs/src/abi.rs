#![allow(non_camel_case_types, non_snake_case)]
// Typed declarations for the pinned 64-bit, GIL-enabled CPython ABI.
use core::ffi::{c_char, c_int, c_ulong, c_void};
pub type Py_ssize_t = isize;
#[repr(C)] pub struct PyObject { _opaque: [u8; 0] }
impl PyObject { pub fn as_raw(&self) -> *mut Self { self as *const Self as *mut Self } }
#[repr(C)] pub struct Py_buffer {
    pub buf: *mut c_void, pub obj: *mut PyObject, pub len: isize,
    pub itemsize: isize, pub readonly: c_int, pub ndim: c_int,
    pub format: *mut c_char, pub shape: *mut isize, pub strides: *mut isize,
    pub suboffsets: *mut isize, pub internal: *mut c_void,
}
pub type Fast = unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, isize) -> *mut PyObject;
pub type Keywords = unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, isize, *mut PyObject) -> *mut PyObject;
#[repr(C)] pub union PyMethodDefFuncPointer {
    pub PyCFunctionFast: Fast, pub PyCFunctionFastWithKeywords: Keywords,
    pub null: *mut c_void,
}
#[repr(C)] pub struct PyMethodDef {
    pub ml_name: *mut c_char, pub ml_meth: PyMethodDefFuncPointer,
    pub ml_flags: c_int, pub ml_doc: *mut c_char,
}
unsafe impl Sync for PyMethodDef {}
impl PyMethodDef { pub const fn zeroed() -> Self {
    Self { ml_name: core::ptr::null_mut(), ml_meth: PyMethodDefFuncPointer { null: core::ptr::null_mut() },
           ml_flags: 0, ml_doc: core::ptr::null_mut() }
}}
#[repr(C)] pub struct PyModuleDef_Base {
    pub ob_refcnt_full: u64, pub ob_type: *mut PyObject,
    pub m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    pub m_index: isize, pub m_copy: *mut PyObject,
}
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_refcnt_full: (3u64 << 30) | (5u64 << 48), ob_type: core::ptr::null_mut(),
    m_init: None, m_index: 0, m_copy: core::ptr::null_mut(),
};
#[repr(C)] pub struct PyModuleDef_Slot { pub slot: c_int, pub value: *mut c_void }
pub type Visit = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int;
#[repr(C)] pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base, pub m_name: *mut c_char, pub m_doc: *mut c_char,
    pub m_size: isize, pub m_methods: *mut PyMethodDef, pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, Visit, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}
pub const METH_FASTCALL: c_int = 0x80;
pub const METH_KEYWORDS: c_int = 2;
const _: () = {
    assert!(core::mem::size_of::<usize>() == 8);
    assert!(core::mem::size_of::<Py_buffer>() == 80);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::size_of::<PyModuleDef_Slot>() == 16);
};
unsafe extern "C" {
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub static mut PyExc_SystemError: *mut PyObject;
    pub static mut PyBytes_Type: PyObject;
    pub static mut PyUnicode_Type: PyObject;
    pub static mut _Py_NoneStruct: PyObject;
    pub fn Py_DecRef(obj: *mut PyObject);
    pub fn Py_NewRef(obj: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetBuffer(obj: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn PyObject_IsInstance(obj: *mut PyObject, cls: *mut PyObject) -> c_int;
    pub fn PyObject_IsTrue(obj: *mut PyObject) -> c_int;
    pub fn PyObject_Length(obj: *mut PyObject) -> isize;
    pub fn PyObject_GetAttrString(obj: *mut PyObject, name: *const c_char) -> *mut PyObject;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, len: isize) -> *mut PyObject;
    pub fn PyBytes_AsString(obj: *mut PyObject) -> *mut c_char;
    pub fn _PyBytes_Resize(obj: *mut *mut PyObject, len: isize) -> c_int;
    pub fn PyErr_SetString(exc: *mut PyObject, message: *const c_char);
    pub fn PyErr_Format(exc: *mut PyObject, format: *const c_char, ...) -> *mut PyObject;
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyImport_AddModule(name: *const c_char) -> *mut PyObject;
    pub fn PyTuple_Size(obj: *mut PyObject) -> isize;
    pub fn PyTuple_GetItem(obj: *mut PyObject, index: isize) -> *mut PyObject;
    pub fn PyUnicode_AsUTF8AndSize(obj: *mut PyObject, len: *mut isize) -> *const c_char;
    pub fn PyUnicode_GetLength(obj: *mut PyObject) -> isize;
    pub fn PyUnicode_ReadChar(obj: *mut PyObject, index: isize) -> u32;
    pub fn PyUnicode_FromStringAndSize(data: *const c_char, len: isize) -> *mut PyObject;
    pub fn PyUnicode_Replace(obj: *mut PyObject, old: *mut PyObject, new: *mut PyObject, count: isize) -> *mut PyObject;
    pub fn PyLong_AsSsize_t(obj: *mut PyObject) -> isize;
    pub fn PyLong_AsUnsignedLongMask(obj: *mut PyObject) -> c_ulong;
    pub fn PyLong_FromUnsignedLong(value: c_ulong) -> *mut PyObject;
    pub fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub fn PyMem_Free(ptr: *mut c_void);
    pub fn PyModuleDef_Init(def: *mut PyModuleDef) -> *mut PyObject;
}

// Core-only dylibs must explicitly link the platform runtime providing abort.
#[cfg_attr(target_os = "macos", link(name = "System"))]
#[cfg_attr(target_os = "linux", link(name = "c"))]
unsafe extern "C" {
    pub fn abort() -> !;
}
