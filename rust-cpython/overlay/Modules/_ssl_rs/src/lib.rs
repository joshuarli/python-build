use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot,
    PyObject,
};

mod cert;
mod config;
mod crl;
mod error;
mod policy;
mod session;
mod trust;
mod verify;

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);
unsafe impl Sync for ModuleSlots {}

// These are the generated slot IDs in the pinned CPython 3.16 fork.
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot { slot: PY_MOD_EXEC, value: module_exec as *const () as *mut c_void },
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

struct ModuleDef(UnsafeCell<PyModuleDef>);
unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_ssl_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust TLS engine (rustls) with a C ABI for the rtls bridge".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: ptr::null_mut(),
    m_slots: SLOTS.0.as_ptr() as *mut _,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__ssl_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
