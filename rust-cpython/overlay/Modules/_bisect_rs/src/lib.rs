use std::cell::UnsafeCell;
use std::ffi::c_char;
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_TypeError,
    PyLong_AsSsize_t, PyLong_FromSsize_t, PyMethodDef, PyMethodDefFuncPointer,
    PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject,
    PyObject_CallOneArg, PyObject_IsTrue, Py_ssize_t,
};

unsafe fn search(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    move_right_when_true: bool,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"search requires lo, hi, and a comparison callback".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let (lo_obj, hi_obj, probe) = unsafe { (*args, *args.add(1), *args.add(2)) };
    let mut lo = unsafe { PyLong_AsSsize_t(lo_obj) };
    if lo == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let mut hi = unsafe { PyLong_AsSsize_t(hi_obj) };
    if hi == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }

    while lo < hi {
        // Unsigned arithmetic avoids overflow for ranges near PY_SSIZE_T_MAX.
        let mid = ((lo as usize + hi as usize) / 2) as Py_ssize_t;
        let mid_obj = unsafe { PyLong_FromSsize_t(mid) };
        if mid_obj.is_null() {
            return ptr::null_mut();
        }
        let comparison = unsafe { PyObject_CallOneArg(probe, mid_obj) };
        unsafe { Py_DecRef(mid_obj) };
        if comparison.is_null() {
            return ptr::null_mut();
        }
        let is_less = unsafe { PyObject_IsTrue(comparison) };
        unsafe { Py_DecRef(comparison) };
        if is_less < 0 {
            return ptr::null_mut();
        }
        if (is_less != 0) == move_right_when_true {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    unsafe { PyLong_FromSsize_t(lo) }
}

unsafe extern "C" fn search_left(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { search(args, nargs, true) }
}

unsafe extern "C" fn search_right(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { search(args, nargs, false) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"search_left".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: search_left,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the left insertion index using a comparison callback.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"search_right".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: search_right,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the right insertion index using a comparison callback.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_bisect_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust search loop for bisect.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__bisect_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
