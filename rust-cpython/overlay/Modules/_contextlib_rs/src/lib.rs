use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::METH_VARARGS;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyCFunction_NewEx;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_CallNoArgs;
use cpython_sys::PyObject_CallOneArg;
use cpython_sys::PyObject_CallObject;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::Py_ssize_t;

// CPython 3.16 assigns slot 86 to multiple-interpreter support.
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

unsafe extern "C" fn push_callback(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"internal contextlib callback push requires two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let callbacks = unsafe { *args };
    let callback = unsafe { *args.add(1) };
    let append = unsafe { PyObject_GetAttrString(callbacks, c"append".as_ptr()) };
    if append.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_CallOneArg(append, callback) };
    unsafe { Py_DecRef(append) };
    result
}

unsafe extern "C" fn pop_callback(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"internal contextlib callback pop requires one argument".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let callbacks = unsafe { *args };
    let pop = unsafe { PyObject_GetAttrString(callbacks, c"pop".as_ptr()) };
    if pop.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_CallNoArgs(pop) };
    unsafe { Py_DecRef(pop) };
    result
}

unsafe extern "C" fn call_callback(
    callback: *mut PyObject,
    args: *mut PyObject,
) -> *mut PyObject {
    unsafe { PyObject_CallObject(callback, args) }
}

unsafe extern "C" fn call_suppressing_callback(
    callback: *mut PyObject,
    args: *mut PyObject,
) -> *mut PyObject {
    let result = unsafe { PyObject_CallObject(callback, args) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let truth = unsafe { PyObject_IsTrue(result) };
    unsafe { Py_DecRef(result) };
    if truth < 0 {
        return ptr::null_mut();
    }
    unsafe { PyBool_FromLong(truth as c_long) }
}

unsafe extern "C" fn wrap_callback(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"internal contextlib callback wrapping requires two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let truth_test_result = unsafe { PyObject_IsTrue(*args.add(1)) };
    if truth_test_result < 0 {
        return ptr::null_mut();
    }
    let method = if truth_test_result != 0 {
        &SUPPRESSING_CALLBACK_METHOD
    } else {
        &CALLBACK_METHOD
    };
    unsafe {
        PyCFunction_NewEx(
            method as *const PyMethodDef as *mut PyMethodDef,
            *args,
            ptr::null_mut(),
        )
    }
}

pub extern "C" fn _contextlib_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _contextlib_rs_free(_module: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

#[repr(C)]
struct ModuleSlot {
    slot: c_int,
    value: *mut c_void,
}

unsafe impl Sync for ModuleSlot {}

static CALLBACK_METHOD: PyMethodDef = PyMethodDef {
    ml_name: c"contextlib_callback".as_ptr() as *mut c_char,
    ml_meth: PyMethodDefFuncPointer {
        PyCFunction: call_callback,
    },
    ml_flags: METH_VARARGS,
    ml_doc: c"Call an exit callback from Rust.".as_ptr() as *mut c_char,
};

static SUPPRESSING_CALLBACK_METHOD: PyMethodDef = PyMethodDef {
    ml_name: c"contextlib_exit_callback".as_ptr() as *mut c_char,
    ml_meth: PyMethodDefFuncPointer {
        PyCFunction: call_suppressing_callback,
    },
    ml_flags: METH_VARARGS,
    ml_doc: c"Call an exit callback and test its suppression result.".as_ptr() as *mut c_char,
};

static MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"push_callback".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: push_callback,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Register a callback in an exit stack.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"pop_callback".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: pop_callback,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Retrieve the newest callback in an exit stack.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"wrap_callback".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: wrap_callback,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a Rust callback dispatcher.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE_SLOTS: [ModuleSlot; 2] = [
    ModuleSlot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        // The extension has no mutable state shared between interpreters.
        value: 2usize as *mut c_void,
    },
    ModuleSlot {
        slot: 0,
        value: ptr::null_mut(),
    },
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_contextlib_rs".as_ptr() as *mut _,
        m_doc: c"Rust operations used by contextlib exit stacks.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut _,
        m_slots: MODULE_SLOTS.as_ptr() as *mut _,
        m_traverse: None,
        m_clear: Some(_contextlib_rs_clear),
        m_free: Some(_contextlib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__contextlib_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
