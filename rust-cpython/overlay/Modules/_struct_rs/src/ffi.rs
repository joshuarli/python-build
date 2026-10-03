#![allow(non_camel_case_types, non_snake_case)]
// Only the 64-bit GIL-enabled CPython layouts used by this helper are declared.
use core::ffi::{c_char, c_double, c_int, c_long, c_longlong, c_ulonglong, c_void};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("the struct helper requires the 64-bit CPython ABI");

pub type Py_ssize_t = isize;
#[repr(C)] pub struct PyObject { _opaque: [u8; 0] }
#[repr(C)] pub struct PyTypeObject { _opaque: [u8; 0] }
#[repr(C)] pub struct Py_buffer {
    pub buf: *mut c_void, pub obj: *mut PyObject, pub len: isize,
    pub itemsize: isize, pub readonly: c_int, pub ndim: c_int,
    pub format: *mut c_char, pub shape: *mut isize, pub strides: *mut isize,
    pub suboffsets: *mut isize, pub internal: *mut c_void,
}
pub type Fast = unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, isize) -> *mut PyObject;
#[repr(C)] pub union PyMethodDefFuncPointer { pub PyCFunctionFast: Fast, pub null: *mut c_void }
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
    pub ob_refcnt_full: u64, pub ob_type: *mut PyTypeObject,
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
const _: () = {
    assert!(core::mem::size_of::<usize>() == 8);
    assert!(core::mem::size_of::<c_long>() == 8);
    assert!(core::mem::size_of::<c_longlong>() == 8);
    assert!(core::mem::size_of::<c_double>() == 8);
    assert!(core::mem::size_of::<Py_buffer>() == 80);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::size_of::<PyModuleDef_Slot>() == 16);
    assert!(core::mem::offset_of!(Py_buffer, len) == 16);
    assert!(core::mem::offset_of!(Py_buffer, internal) == 72);
    assert!(core::mem::offset_of!(PyModuleDef, m_methods) == 64);
    assert!(core::mem::offset_of!(PyModuleDef, m_slots) == 72);
    assert!(core::mem::offset_of!(PyModuleDef, m_free) == 96);
};
unsafe extern "C" {
    pub static mut PyBool_Type: PyTypeObject;
    pub static mut PyByteArray_Type: PyTypeObject;
    pub static mut PyBytes_Type: PyTypeObject;
    pub static mut PyFloat_Type: PyTypeObject;
    pub static mut PyLong_Type: PyTypeObject;
    pub static mut PyTuple_Type: PyTypeObject;
    pub static mut PyUnicode_Type: PyTypeObject;
    pub fn PyBool_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyBytes_AsString(obj: *mut PyObject) -> *mut c_char;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, len: isize) -> *mut PyObject;
    pub fn PyErr_Clear();
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyFloat_AsDouble(obj: *mut PyObject) -> c_double;
    pub fn PyFloat_FromDouble(value: c_double) -> *mut PyObject;
    pub fn PyLong_AsLongLong(obj: *mut PyObject) -> c_longlong;
    pub fn PyLong_AsSsize_t(obj: *mut PyObject) -> isize;
    pub fn PyLong_AsUnsignedLongLong(obj: *mut PyObject) -> c_ulonglong;
    pub fn PyLong_FromLongLong(value: c_longlong) -> *mut PyObject;
    pub fn PyLong_FromUnsignedLongLong(value: c_ulonglong) -> *mut PyObject;
    pub fn PyObject_GetBuffer(obj: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    pub fn PyObject_IsTrue(obj: *mut PyObject) -> c_int;
    pub fn PyObject_Type(obj: *mut PyObject) -> *mut PyObject;
    pub fn PyTuple_GetItem(obj: *mut PyObject, index: isize) -> *mut PyObject;
    pub fn PyTuple_New(len: isize) -> *mut PyObject;
    pub fn PyTuple_SetItem(obj: *mut PyObject, index: isize, value: *mut PyObject) -> c_int;
    pub fn PyTuple_Size(obj: *mut PyObject) -> isize;
    pub fn PyUnicode_AsUTF8AndSize(obj: *mut PyObject, len: *mut isize) -> *const c_char;
    pub fn Py_DecRef(obj: *mut PyObject);
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn PyMem_Free(ptr: *mut c_void);
    pub fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub fn Py_NewRef(obj: *mut PyObject) -> *mut PyObject;
    pub fn PyModuleDef_Init(def: *mut PyModuleDef) -> *mut PyObject;
}

// A core-only standalone image still needs the existing platform runtime.
#[cfg_attr(target_os = "macos", link(name = "System"))]
#[cfg_attr(target_os = "linux", link(name = "c"))]
unsafe extern "C" { pub fn Py_FatalError(message: *const c_char) -> !; }
