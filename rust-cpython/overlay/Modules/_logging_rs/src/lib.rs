use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_SetString, PyExc_TypeError, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_Init, PyModuleDef_Slot,
    PyModuleDef_HEAD_INIT, PyNumber_Remainder, PyObject, PyObject_IsTrue, PyObject_Str,
    Py_ssize_t,
};

unsafe fn format_message(message: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    let message = unsafe { PyObject_Str(message) };
    if message.is_null() {
        return ptr::null_mut();
    }

    let has_args = unsafe { PyObject_IsTrue(args) };
    if has_args < 0 {
        unsafe { Py_DecRef(message) };
        return ptr::null_mut();
    }
    if has_args == 0 {
        return message;
    }

    let formatted = unsafe { PyNumber_Remainder(message, args) };
    unsafe { Py_DecRef(message) };
    formatted
}

unsafe extern "C" fn get_message(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"get_message requires a message and its arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    unsafe { format_message(*args, *args.add(1)) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

static METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"get_message".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: get_message,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Format a logging record's message and arguments.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_EXEC,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_logging_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust message formatting for logging records.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__logging_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
