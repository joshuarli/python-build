//! The codec's used CPython API for the 64-bit, little-endian GIL build.
//! Object prefixes and module tables are C layouts; type and long objects stay
//! opaque because the codec only compares or casts their addresses. Unicode
//! storage is accessed through exported functions, not guessed bit fields.
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]
use core::ffi::{c_char, c_int, c_void};
#[cfg(not(all(target_pointer_width = "64", target_endian = "little")))]
compile_error!("JSON native declarations require 64-bit little-endian CPython");
pub type Py_ssize_t = isize;
#[repr(C)]
pub struct PyObject { pub ob_refcnt_full: i64, pub ob_type: *mut PyTypeObject }
pub type _object = PyObject;
#[repr(C)]
pub struct PyTypeObject { _opaque: [u8; 0] }
#[repr(C)]
pub struct PyLongObject { _opaque: [u8; 0] }
#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunctionFast: unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject,
    pub Void: *mut c_void,
}
#[repr(C)]
pub struct PyMethodDef { pub ml_name: *mut c_char, pub ml_meth: PyMethodDefFuncPointer, pub ml_flags: c_int, pub ml_doc: *mut c_char }
unsafe impl Sync for PyMethodDef {}
impl PyMethodDef {
    pub const fn zeroed() -> Self { Self { ml_name: core::ptr::null_mut(), ml_meth: PyMethodDefFuncPointer { Void: core::ptr::null_mut() }, ml_flags: 0, ml_doc: core::ptr::null_mut() } }
}
#[repr(C)]
pub struct PyModuleDef_Base {
    pub ob_base: PyObject,
    pub m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    pub m_index: Py_ssize_t,
    pub m_copy: *mut PyObject,
}
#[repr(C)]
pub struct PyModuleDef_Slot { pub slot: c_int, pub value: *mut c_void }
pub type visitproc = Option<unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int>;
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
pub const METH_FASTCALL: c_int = 0x0080;
// Static module definitions must carry both the immortal and static flags.
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject { ob_refcnt_full: (3_i64 << 30) | (5_i64 << 48), ob_type: core::ptr::null_mut() },
    m_init: None, m_index: 0, m_copy: core::ptr::null_mut(),
};
unsafe extern "C" {
    pub static mut PyBool_Type: PyTypeObject;
    pub static mut PyDict_Type: PyTypeObject;
    pub static mut PyFloat_Type: PyTypeObject;
    pub static mut PyList_Type: PyTypeObject;
    pub static mut PyLong_Type: PyTypeObject;
    pub static mut PyTuple_Type: PyTypeObject;
    pub static mut PyUnicode_Type: PyTypeObject;
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut _Py_NoneStruct: PyObject;
    pub static mut _Py_NotImplementedStruct: PyObject;
    pub static mut _Py_TrueStruct: PyLongObject;
    pub static mut _Py_FalseStruct: PyLongObject;
    pub fn PyDict_New() -> *mut PyObject;
    pub fn PyDict_Next(object: *mut PyObject, position: *mut Py_ssize_t, key: *mut *mut PyObject, value: *mut *mut PyObject) -> c_int;
    pub fn PyDict_SetItem(object: *mut PyObject, key: *mut PyObject, value: *mut PyObject) -> c_int;
    pub fn PyErr_Clear();
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyErr_SetString(kind: *mut PyObject, message: *const c_char);
    pub fn PyErr_GetRaisedException() -> *mut PyObject;
    pub fn PyErr_SetRaisedException(error: *mut PyObject);
    pub fn PyFloat_AsDouble(object: *mut PyObject) -> f64;
    pub fn PyFloat_FromDouble(value: f64) -> *mut PyObject;
    pub fn PyList_GetItem(object: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_New(length: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_SetItem(object: *mut PyObject, index: Py_ssize_t, value: *mut PyObject) -> c_int;
    pub fn PyList_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyLong_AsLongLongAndOverflow(object: *mut PyObject, overflow: *mut c_int) -> i64;
    pub fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    pub fn PyLong_FromString(text: *const c_char, end: *mut *mut c_char, base: c_int) -> *mut PyObject;
    pub fn PyMem_Free(data: *mut c_void);
    pub fn PyMem_Realloc(data: *mut c_void, bytes: usize) -> *mut c_void;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyOS_double_to_string(value: f64, format: c_char, precision: c_int, flags: c_int, kind: *mut c_int) -> *mut c_char;
    pub fn PyObject_IsTrue(object: *mut PyObject) -> c_int;
    pub fn PyObject_Str(object: *mut PyObject) -> *mut PyObject;
    pub fn PyTuple_GetItem(object: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, length: *mut Py_ssize_t) -> *const c_char;
    pub fn PyUnicode_DATA(object: *mut PyObject) -> *mut c_void;
    pub fn PyUnicode_KIND(object: *mut PyObject) -> c_int;
    pub fn PyUnicode_FromStringAndSize(data: *const c_char, length: Py_ssize_t) -> *mut PyObject;
    pub fn PyUnicode_GetLength(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_New(length: Py_ssize_t, maximum: u32) -> *mut PyObject;
    pub fn Py_DecRef(object: *mut PyObject);
    pub fn Py_IncRef(object: *mut PyObject);
}
// These are the only concrete C layouts read or constructed by the codec.
const _: () = {
    assert!(core::mem::size_of::<PyObject>() == 16);
    assert!(core::mem::offset_of!(PyObject, ob_type) == 8);
    assert!(core::mem::size_of::<PyMethodDef>() == 32);
    assert!(core::mem::offset_of!(PyMethodDef, ml_meth) == 8);
    assert!(core::mem::offset_of!(PyMethodDef, ml_flags) == 16);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::offset_of!(PyModuleDef, m_size) == 56);
    assert!(core::mem::offset_of!(PyModuleDef, m_methods) == 64);
    assert!(core::mem::offset_of!(PyModuleDef, m_slots) == 72);
    assert!(core::mem::offset_of!(PyModuleDef, m_traverse) == 80);
    assert!(core::mem::size_of::<PyModuleDef_Slot>() == 16);
};
