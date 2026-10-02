#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_long, c_void};
use core::ptr;

use cpython_sys::{
    PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot,
    PyModule_AddObject, PyObject, Py_DecRef,
};

// The static carrier owns its panic handler; a standalone extension terminates
// the process on panic rather than unwinding through a C callback boundary.
#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    unsafe extern "C" {
        fn abort() -> !;
    }
    unsafe { abort() }
}

const TLS_HANDSHAKE: c_int = 0;
const TLS_READ: c_int = 1;
const TLS_WRITE: c_int = 2;
const NO_WAIT: c_int = 0;
const WAIT_READ: c_int = 1;
const WAIT_WRITE: c_int = 2;

#[repr(C)]
struct TlsCallbacks {
    new_context: unsafe extern "C" fn(*const c_void) -> *mut c_void,
    set_options: unsafe extern "C" fn(*mut c_void, u64) -> u64,
    set_mode: unsafe extern "C" fn(*mut c_void, c_long) -> c_long,
    handshake: unsafe extern "C" fn(*mut c_void) -> c_int,
    read: unsafe extern "C" fn(*mut c_void, *mut c_void, usize, *mut usize) -> c_int,
    write: unsafe extern "C" fn(*mut c_void, *const c_void, usize, *mut usize) -> c_int,
    ssl_error: unsafe extern "C" fn(*const c_void, c_int) -> c_int,
    os_error: unsafe extern "C" fn() -> c_int,
    want_read: c_int,
    want_write: c_int,
}

#[repr(C)]
struct TlsStep {
    result: c_int,
    count: usize,
    ssl_error: c_int,
    os_error: c_int,
    wait_for: c_int,
}

#[repr(C)]
struct TlsApi {
    create_context: unsafe extern "C" fn(*const c_void, *const TlsCallbacks) -> *mut c_void,
    apply_context_options: unsafe extern "C" fn(*mut c_void, u64, *const TlsCallbacks),
    enable_context_mode: unsafe extern "C" fn(*mut c_void, c_long, *const TlsCallbacks),
    step: unsafe extern "C" fn(*mut c_void, c_int, *mut c_void, usize, *const TlsCallbacks) -> TlsStep,
}

// The callbacks keep OpenSSL's configured linkage, error queue, and socket
// ownership in CPython. Rust applies context policy and drives each TLS step.
unsafe extern "C" fn create_context(
    method: *const c_void,
    callbacks: *const TlsCallbacks,
) -> *mut c_void {
    let callbacks = unsafe { &*callbacks };
    unsafe { (callbacks.new_context)(method) }
}

unsafe extern "C" fn apply_context_options(
    context: *mut c_void,
    options: u64,
    callbacks: *const TlsCallbacks,
) {
    let callbacks = unsafe { &*callbacks };
    unsafe { (callbacks.set_options)(context, options) };
}

unsafe extern "C" fn enable_context_mode(
    context: *mut c_void,
    mode: c_long,
    callbacks: *const TlsCallbacks,
) {
    let callbacks = unsafe { &*callbacks };
    unsafe { (callbacks.set_mode)(context, mode) };
}

unsafe extern "C" fn step(
    ssl: *mut c_void,
    operation: c_int,
    data: *mut c_void,
    length: usize,
    callbacks: *const TlsCallbacks,
) -> TlsStep {
    let callbacks = unsafe { &*callbacks };
    let mut count = 0;
    let result = match operation {
        TLS_HANDSHAKE => unsafe { (callbacks.handshake)(ssl) },
        TLS_READ => unsafe { (callbacks.read)(ssl, data, length, &mut count) },
        TLS_WRITE => unsafe { (callbacks.write)(ssl, data.cast_const(), length, &mut count) },
        _ => return TlsStep { result: 0, count: 0, ssl_error: 1, os_error: 0, wait_for: NO_WAIT },
    };
    let failed = if operation == TLS_HANDSHAKE { result < 1 } else { result == 0 };
    if !failed {
        return TlsStep { result, count, ssl_error: 0, os_error: 0, wait_for: NO_WAIT };
    }

    // Save errno before SSL_get_error, just as CPython's native path does.
    let os_error = unsafe { (callbacks.os_error)() };
    let ssl_error = unsafe { (callbacks.ssl_error)(ssl, result) };
    let wait_for = if ssl_error == callbacks.want_read {
        WAIT_READ
    } else if ssl_error == callbacks.want_write {
        WAIT_WRITE
    } else {
        NO_WAIT
    };
    TlsStep { result, count, ssl_error, os_error, wait_for }
}

static API: TlsApi = TlsApi {
    create_context,
    apply_context_options,
    enable_context_mode,
    step,
};

unsafe extern "C" {
    fn PyCapsule_New(
        pointer: *mut c_void,
        name: *const c_char,
        destructor: Option<unsafe extern "C" fn(*mut PyObject)>,
    ) -> *mut PyObject;
}

unsafe extern "C" fn module_exec(module: *mut PyObject) -> c_int {
    let capsule = unsafe {
        PyCapsule_New(
            (&API as *const TlsApi).cast_mut().cast(),
            c"_ssl_rs._C_API".as_ptr(),
            None,
        )
    };
    if capsule.is_null() {
        return -1;
    }
    if unsafe { PyModule_AddObject(module, c"_C_API".as_ptr(), capsule) } < 0 {
        unsafe { Py_DecRef(capsule) };
        return -1;
    }
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);
unsafe impl Sync for ModuleSlots {}

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot { slot: 85, value: module_exec as *const () as *mut c_void },
    PyModuleDef_Slot { slot: 86, value: 2 as *mut c_void },
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

struct ModuleDef(UnsafeCell<PyModuleDef>);
unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_ssl_rs".as_ptr() as *mut _,
    m_doc: c"Rust TLS context and stream operation steps".as_ptr() as *mut _,
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
