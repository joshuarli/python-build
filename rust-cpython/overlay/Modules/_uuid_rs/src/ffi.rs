#![allow(non_camel_case_types, non_snake_case)]
// This object head is only initialized inside static module definitions.
// Runtime Python objects remain opaque and are accessed through typed C APIs.
#[cfg(not(all(target_pointer_width = "64", target_endian = "little")))]
compile_error!("the module ABI requires a 64-bit little-endian GIL-enabled CPython build");
use core::ffi::{c_char, c_int, c_void};
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
#[repr(C)] pub union PyMethodDefFuncPointer {
    pub PyCFunctionFast: Fast,
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
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, Option<Visit>, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}
pub const METH_FASTCALL: c_int = 0x80;
const _: () = {
    assert!(core::mem::size_of::<usize>() == 8);
    assert!(core::mem::size_of::<Py_buffer>() == 80);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::size_of::<PyModuleDef_Slot>() == 16);
    assert!(core::mem::align_of::<PyModuleDef>() == 8);
    assert!(core::mem::offset_of!(PyModuleDef, m_methods) == 64);
    assert!(core::mem::offset_of!(PyModuleDef, m_slots) == 72);
    assert!(core::mem::offset_of!(PyMethodDef, ml_flags) == 16);
    assert!(core::mem::offset_of!(Py_buffer, internal) == 72);
};
unsafe extern "C" {
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub fn PyObject_GetBuffer(obj: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn PyBytes_FromStringAndSize(data: *const c_char, len: isize) -> *mut PyObject;
    pub fn PyErr_SetString(exc: *mut PyObject, message: *const c_char);
    pub fn PyModuleDef_Init(def: *mut PyModuleDef) -> *mut PyObject;
}

