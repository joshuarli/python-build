//! The address operations use the 64-bit, GIL-enabled Python C ABI.
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_long, c_void};
use core::ptr;

pub type Py_ssize_t = isize;

// Python may mutate the header while Rust borrows an argument.
#[repr(C)]
pub struct PyObject {
    pub ob_refcnt: UnsafeCell<Py_ssize_t>,
    pub ob_type: UnsafeCell<*mut PyTypeObject>,
}

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

impl PyObject {
    pub fn as_raw(&self) -> *mut Self {
        ptr::from_ref(self).cast_mut()
    }
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

pub type FastCall = unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject;
pub type Visit = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int;

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunctionFast: FastCall,
    pub void: *mut c_void,
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
        Self { ml_name: ptr::null_mut(), ml_meth: PyMethodDefFuncPointer { void: ptr::null_mut() },
               ml_flags: 0, ml_doc: ptr::null_mut() }
    }
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

#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, Visit, *mut c_void) -> c_int>,
    pub m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<extern "C" fn(*mut c_void)>,
}

pub const METH_FASTCALL: c_int = 0x0080;
// Static objects combine the immortal refcount with their static allocation flags.
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject { ob_refcnt: UnsafeCell::new((3_isize << 30) | (5_isize << 48)),
                        ob_type: UnsafeCell::new(ptr::null_mut()) },
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub fn PyLong_AsLong(object: *mut PyObject) -> c_long;
    pub fn PyObject_GetBuffer(object: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    pub fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn abort() -> !;
}

// These layouts are shared with the interpreter, including the buffer exporter.
const _: () = {
    assert!(core::mem::size_of::<PyObject>() == 16);
    assert!(core::mem::align_of::<PyObject>() == 8);
    assert!(core::mem::size_of::<Py_buffer>() == 80);
    assert!(core::mem::offset_of!(Py_buffer, readonly) == 32);
    assert!(core::mem::offset_of!(Py_buffer, format) == 40);
    assert!(core::mem::offset_of!(Py_buffer, internal) == 72);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::offset_of!(PyMethodDef, ml_flags) == 16);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::offset_of!(PyModuleDef, m_methods) == 64);
    assert!(core::mem::offset_of!(PyModuleDef, m_slots) == 72);
    assert!(core::mem::offset_of!(PyModuleDef, m_free) == 96);
};
