use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_longlong, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyLong_FromLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::Py_ssize_t;

const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: c_int = 86;
const BARRIER_RESETTING: c_longlong = -1;
const BARRIER_FILLING: c_longlong = 0;
const BARRIER_DRAINING: c_longlong = 1;
const BARRIER_BROKEN: c_longlong = -2;

// The Python Condition owns synchronization; this stateless module computes
// Barrier transitions without sharing per-barrier state between interpreters.

unsafe extern "C" fn barrier_transition(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"barrier transition requires an operation, state, and count".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let operation_object = unsafe { *args };
    let mut operation_length = 0;
    let operation_bytes = unsafe {
        PyUnicode_AsUTF8AndSize(operation_object, &mut operation_length)
    };
    if operation_bytes.is_null() {
        return ptr::null_mut();
    }
    if operation_length < 0 {
        unsafe {
            PyErr_SetString(PyExc_ValueError, c"barrier operation has a negative length".as_ptr());
        }
        return ptr::null_mut();
    }
    let operation = unsafe {
        slice::from_raw_parts(operation_bytes.cast::<u8>(), operation_length as usize)
    };

    let state = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if state == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let count = unsafe { PyLong_AsLongLong(*args.add(2)) };
    if count == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }

    let result = match operation {
        b"enter_status" => {
            if state == BARRIER_RESETTING || state == BARRIER_DRAINING {
                0
            } else if state < 0 {
                -1
            } else {
                1
            }
        }
        b"release_state" => BARRIER_DRAINING,
        b"wait_condition" => (state != BARRIER_FILLING) as c_longlong,
        b"wait_status" => {
            if state < 0 {
                -1
            } else if state == BARRIER_DRAINING {
                1
            } else {
                0
            }
        }
        b"exit_state" => {
            if count == 0 && (state == BARRIER_RESETTING || state == BARRIER_DRAINING) {
                BARRIER_FILLING
            } else {
                state
            }
        }
        b"reset_state" => {
            if count > 0 {
                if state == BARRIER_FILLING || state == BARRIER_BROKEN {
                    BARRIER_RESETTING
                } else {
                    state
                }
            } else {
                0
            }
        }
        b"broken_state" => BARRIER_BROKEN,
        b"waiting_count" => {
            if state == BARRIER_FILLING {
                count
            } else {
                0
            }
        }
        b"is_broken" => (state == BARRIER_BROKEN) as c_longlong,
        _ => {
            unsafe {
                PyErr_SetString(PyExc_ValueError, c"unknown barrier transition".as_ptr());
            }
            return ptr::null_mut();
        }
    };

    if operation == b"wait_condition" || operation == b"is_broken" {
        unsafe { PyBool_FromLong(result) }
    } else {
        unsafe { PyLong_FromLongLong(result) }
    }
}

pub extern "C" fn _threading_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _threading_rs_free(_module: *mut c_void) {}

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

static METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"_barrier_transition".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: barrier_transition,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Apply a threading barrier state transition in Rust.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE_SLOTS: [ModuleSlot; 2] = [
    ModuleSlot {
        slot: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
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
        m_name: c"_threading_rs".as_ptr() as *mut _,
        m_doc: c"Rust barrier state transitions used by threading.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: MODULE_SLOTS.as_ptr() as *mut _,
        m_traverse: None,
        m_clear: Some(_threading_rs_clear),
        m_free: Some(_threading_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__threading_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
