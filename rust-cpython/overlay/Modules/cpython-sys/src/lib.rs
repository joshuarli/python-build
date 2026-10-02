#![no_std]
#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(unsafe_op_in_unsafe_fn)]
#![allow(unnecessary_transmutes)]
#![allow(clippy::approx_constant)]

use core::ffi::{c_char, c_int, c_void};

include!(concat!(env!("OUT_DIR"), "/c_api.rs"));

// Parser bindings are not currently included.
//include!(concat!(env!("OUT_DIR"), "/parser.rs"));
/* Flag passed to newmethodobject */
/* #define METH_OLDARGS  0x0000   -- unsupported now */
pub const METH_VARARGS: c_int = 0x0001;
pub const METH_KEYWORDS: c_int = 0x0002;
/* METH_NOARGS and METH_O must not be combined with the flags above. */
pub const METH_NOARGS: c_int = 0x0004;
pub const METH_O: c_int = 0x0008;

/* METH_CLASS and METH_STATIC are a little different; these control
the construction of methods for a class.  These cannot be used for
functions in modules. */
pub const METH_CLASS: c_int = 0x0010;
pub const METH_STATIC: c_int = 0x0020;

/* METH_COEXIST allows a method to be entered even though a slot has
already filled the entry.  When defined, the flag allows a separate
method, "__contains__" for example, to coexist with a defined
slot like sq_contains. */

pub const METH_COEXIST: c_int = 0x0040;

pub const METH_FASTCALL: c_int = 0x0080;

/* This bit is preserved for Stackless Python
pub const METH_STACKLESS: c_int = 0x0100;
pub const METH_STACKLESS: c_int = 0x0000;
*/

/* METH_METHOD means the function stores an
 * additional reference to the class that defines it;
 * both self and class are passed to it.
 * It uses PyCMethodObject instead of PyCFunctionObject.
 * May not be combined with METH_NOARGS, METH_O, METH_CLASS or METH_STATIC.
 */

pub const METH_METHOD: c_int = 0x0200;

#[cfg(target_pointer_width = "64")]
pub const _Py_STATIC_FLAG_BITS: Py_ssize_t =
    (_Py_STATICALLY_ALLOCATED_FLAG | _Py_IMMORTAL_FLAGS) as Py_ssize_t;
#[cfg(target_pointer_width = "64")]
pub const _Py_STATIC_IMMORTAL_INITIAL_REFCNT: Py_ssize_t =
    (_Py_IMMORTAL_INITIAL_REFCNT as Py_ssize_t) | (_Py_STATIC_FLAG_BITS << 48);
#[cfg(not(target_pointer_width = "64"))]
pub const _Py_STATIC_IMMORTAL_INITIAL_REFCNT: Py_ssize_t = (7u32 << 28) as Py_ssize_t;

#[repr(transparent)]
pub struct PyObject(core::cell::UnsafeCell<_object>);

impl PyObject {
    #[inline]
    pub fn as_raw(&self) -> *mut Self {
        self.0.get() as *mut Self
    }
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunction: unsafe extern "C" fn(slf: *mut PyObject, args: *mut PyObject) -> *mut PyObject,
    pub PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    pub PyCFunctionWithKeywords: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut PyObject,
        kwargs: *mut PyObject,
    ) -> *mut PyObject,
    pub PyCFunctionFastWithKeywords: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
        kwargs: *mut PyObject,
    ) -> *mut PyObject,
    pub PyCMethod: unsafe extern "C" fn(
        slf: *mut PyObject,
        typ: *mut PyTypeObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
        kwargs: *mut PyObject,
    ) -> *mut PyObject,
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
            ml_name: core::ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer {
                Void: core::ptr::null_mut(),
            },
            ml_flags: 0,
            ml_doc: core::ptr::null_mut(),
        }
    }
}

// TODO: this is pretty unsafe, we should probably wrap this in a nicer
// abstraction
unsafe impl Sync for PyMethodDef {}
unsafe impl Send for PyMethodDef {}

#[cfg(py_gil_disabled)]
pub const PyObject_HEAD_INIT: PyObject = {
    let mut obj: _object = unsafe { core::mem::MaybeUninit::zeroed().assume_init() };
    obj.ob_flags = _Py_STATICALLY_ALLOCATED_FLAG as _;
    PyObject(core::cell::UnsafeCell::new(obj))
};

#[cfg(all(not(py_gil_disabled), target_pointer_width = "64"))]
pub const PyObject_HEAD_INIT: PyObject = PyObject(core::cell::UnsafeCell::new(_object {
    __bindgen_anon_1: _object__bindgen_ty_1 {
        ob_refcnt_full: _Py_STATIC_IMMORTAL_INITIAL_REFCNT as i64,
    },
    ob_type: core::ptr::null_mut(),
}));

// On 32-bit platforms, the refcount union only has ob_refcnt (no ob_refcnt_split).
#[cfg(all(not(py_gil_disabled), not(target_pointer_width = "64")))]
pub const PyObject_HEAD_INIT: PyObject = PyObject(core::cell::UnsafeCell::new(_object {
    __bindgen_anon_1: _object__bindgen_ty_1 {
        ob_refcnt: _Py_STATIC_IMMORTAL_INITIAL_REFCNT,
    },
    ob_type: core::ptr::null_mut(),
}));

pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject_HEAD_INIT,
    m_init: None,
    m_index: 0,
    m_copy: core::ptr::null_mut(),
};

#[cfg(test)]
mod tests {
    use super::*;

    const _: unsafe extern "C" fn(*mut PyModuleDef) -> *mut PyObject = PyModuleDef_Init;

    #[test]
    fn generated_object_wrapper_preserves_layout() {
        assert_eq!(core::mem::size_of::<PyObject>(), core::mem::size_of::<_object>());
        assert_eq!(core::mem::align_of::<PyObject>(), core::mem::align_of::<_object>());
    }

    #[test]
    fn static_module_initializer_preserves_configured_object_header() {
        let base = PyModuleDef_HEAD_INIT;
        let object = base.ob_base.as_raw().cast::<_object>();
        assert!(base.m_init.is_none());
        assert_eq!(base.m_index, 0);
        assert!(base.m_copy.is_null());
        unsafe {
            assert!((*object).ob_type.is_null());
            #[cfg(py_gil_disabled)]
            assert_eq!((*object).ob_flags, _Py_STATICALLY_ALLOCATED_FLAG as _);
            #[cfg(all(not(py_gil_disabled), target_pointer_width = "64"))]
            assert_eq!(
                (*object).__bindgen_anon_1.ob_refcnt_full,
                _Py_STATIC_IMMORTAL_INITIAL_REFCNT as i64,
            );
            #[cfg(all(not(py_gil_disabled), not(target_pointer_width = "64")))]
            assert_eq!(
                (*object).__bindgen_anon_1.ob_refcnt,
                _Py_STATIC_IMMORTAL_INITIAL_REFCNT,
            );
        }
    }

    #[test]
    fn method_sentinel_has_no_callable_or_metadata() {
        let method = PyMethodDef::zeroed();
        assert!(method.ml_name.is_null());
        assert!(unsafe { method.ml_meth.Void }.is_null());
        assert_eq!(method.ml_flags, 0);
        assert!(method.ml_doc.is_null());
    }
}
