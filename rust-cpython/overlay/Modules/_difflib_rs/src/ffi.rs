#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_void};

// These C layouts describe the 64-bit, GIL-enabled CPython module boundary.
pub(super) type Py_ssize_t = isize;

#[repr(C)]
pub struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut c_void,
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub(super) PyCFunctionFast: unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject,
    pub(super) Void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    pub(super) ml_name: *mut c_char,
    pub(super) ml_meth: PyMethodDefFuncPointer,
    pub(super) ml_flags: c_int,
    pub(super) ml_doc: *mut c_char,
}

impl PyMethodDef {
    pub(super) const fn zeroed() -> Self {
        Self {
            ml_name: core::ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer { Void: core::ptr::null_mut() },
            ml_flags: 0,
            ml_doc: core::ptr::null_mut(),
        }
    }
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
pub(super) struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
pub(super) struct PyModuleDef {
    pub(super) m_base: PyModuleDef_Base,
    pub(super) m_name: *const c_char,
    pub(super) m_doc: *const c_char,
    pub(super) m_size: Py_ssize_t,
    pub(super) m_methods: *mut PyMethodDef,
    pub(super) m_slots: *mut c_void,
    pub(super) m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    pub(super) m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub(super) m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

pub(super) const METH_FASTCALL: c_int = 0x0080;
// Immortal reference count and static allocation flags in the 64-bit GIL ABI.
pub(super) const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject {
        ob_refcnt: (3_isize << 30) | (5_isize << 48),
        ob_type: core::ptr::null_mut(),
    },
    m_init: None,
    m_index: 0,
    m_copy: core::ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    pub(super) static mut PyExc_TypeError: *mut PyObject;
    pub(super) static mut PyExc_ValueError: *mut PyObject;
    pub(super) fn Py_DecRef(object: *mut PyObject);
    pub(super) fn PyErr_NoMemory() -> *mut PyObject;
    pub(super) fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub(super) fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub(super) fn PyErr_Occurred() -> *mut PyObject;
    pub(super) fn PyList_Size(object: *mut PyObject) -> Py_ssize_t;
    pub(super) fn PyList_GetItem(object: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub(super) fn PyLong_AsLongLong(object: *mut PyObject) -> i64;
    pub(super) fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    pub(super) fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    pub(super) fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    pub(super) fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub(super) fn PyMem_Realloc(pointer: *mut c_void, size: usize) -> *mut c_void;
    pub(super) fn PyMem_Free(pointer: *mut c_void);
    pub(super) fn qsort(
        base: *mut c_void, count: usize, size: usize,
        compare: unsafe extern "C" fn(*const c_void, *const c_void) -> c_int,
    );
    pub(super) fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

