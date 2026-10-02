#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;

use cpython_sys::{
    METH_FASTCALL, PyErr_SetString, PyExc_TypeError, PyList_GetItemRef, PyList_Size,
    PyMethodDef, PyMethodDefFuncPointer, PyModule_GetState, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyModuleDef_Slot, PyObject, PyObject_CallOneArg, PyObject_GetAttr,
    PyObject_IsTrue, PyObject_RichCompareBool, PyObject_SetAttr, PyObject_VectorcallMethod,
    PyUnicode_InternFromString, Py_DecRef, Py_NewRef, Py_ssize_t, _Py_FalseStruct,
    _Py_NoneStruct,
};

struct Owned(*mut PyObject);

impl Owned {
    fn new(object: *mut PyObject) -> Option<Self> {
        (!object.is_null()).then_some(Self(object))
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }
}

impl Drop for Owned {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) };
    }
}

/// Interned attribute and method names, one set per module object, so the
/// event-loop hot path never builds a temporary `str` or misses the type
/// attribute cache.
struct State {
    popleft: *mut PyObject,
    append: *mut PyObject,
    cancelled: *mut PyObject,
    run: *mut PyObject,
    when: *mut PyObject,
    scheduled: *mut PyObject,
}

unsafe fn state<'a>(module: *mut PyObject) -> &'a State {
    unsafe { &*(PyModule_GetState(module) as *const State) }
}

unsafe fn call_method0(object: *mut PyObject, name: *mut PyObject) -> *mut PyObject {
    let args = [object];
    unsafe { PyObject_VectorcallMethod(name, args.as_ptr(), 1, ptr::null_mut()) }
}

unsafe fn call_method1(
    object: *mut PyObject,
    name: *mut PyObject,
    arg: *mut PyObject,
) -> *mut PyObject {
    let args = [object, arg];
    unsafe { PyObject_VectorcallMethod(name, args.as_ptr(), 2, ptr::null_mut()) }
}

unsafe extern "C" fn promote_due_timers(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 4 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"promote_due_timers requires four arguments".as_ptr());
        }
        return ptr::null_mut();
    }
    let names = unsafe { state(module) };

    let scheduled = unsafe { *args };
    let ready = unsafe { *args.add(1) };
    let end_time = unsafe { *args.add(2) };
    let heappop = unsafe { *args.add(3) };

    loop {
        let count = unsafe { PyList_Size(scheduled) };
        if count < 0 {
            return ptr::null_mut();
        }
        if count == 0 {
            break;
        }

        let Some(head) = Owned::new(unsafe { PyList_GetItemRef(scheduled, 0) }) else {
            return ptr::null_mut();
        };
        let Some(when) = Owned::new(unsafe { PyObject_GetAttr(head.as_ptr(), names.when) }) else {
            return ptr::null_mut();
        };
        // Match the event loop's >= comparison so equal deadlines stay queued.
        let not_due = unsafe { PyObject_RichCompareBool(when.as_ptr(), end_time, 5) };
        if not_due < 0 {
            return ptr::null_mut();
        }
        if not_due != 0 {
            break;
        }

        let Some(handle) = Owned::new(unsafe { PyObject_CallOneArg(heappop, scheduled) }) else {
            return ptr::null_mut();
        };
        let false_object = ptr::addr_of_mut!(_Py_FalseStruct) as *mut PyObject;
        if unsafe { PyObject_SetAttr(handle.as_ptr(), names.scheduled, false_object) } < 0 {
            return ptr::null_mut();
        }
        if Owned::new(unsafe { call_method1(ready, names.append, handle.as_ptr()) }).is_none() {
            return ptr::null_mut();
        }
    }

    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn pop_ready_handle(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"pop_ready_handle requires one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let names = unsafe { state(module) };
    unsafe { call_method0(*args, names.popleft) }
}

unsafe extern "C" fn dispatch_ready_handle(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"dispatch_ready_handle requires one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let names = unsafe { state(module) };
    let Some(handle) = Owned::new(unsafe { call_method0(*args, names.popleft) }) else {
        return ptr::null_mut();
    };
    let Some(cancelled) =
        Owned::new(unsafe { PyObject_GetAttr(handle.as_ptr(), names.cancelled) })
    else {
        return ptr::null_mut();
    };
    let is_cancelled = unsafe { PyObject_IsTrue(cancelled.as_ptr()) };
    if is_cancelled < 0 {
        return ptr::null_mut();
    }
    if is_cancelled == 0
        && Owned::new(unsafe { call_method0(handle.as_ptr(), names.run) }).is_none()
    {
        return ptr::null_mut();
    }
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn module_clear(module: *mut PyObject) -> c_int {
    let names = unsafe { PyModule_GetState(module) as *mut State };
    if !names.is_null() {
        unsafe {
            for slot in [
                &mut (*names).popleft,
                &mut (*names).append,
                &mut (*names).cancelled,
                &mut (*names).run,
                &mut (*names).when,
                &mut (*names).scheduled,
            ] {
                let object = core::mem::replace(slot, ptr::null_mut());
                if !object.is_null() {
                    Py_DecRef(object);
                }
            }
        }
    }
    0
}

unsafe extern "C" fn module_free(module: *mut c_void) {
    unsafe { module_clear(module as *mut PyObject) };
}

unsafe extern "C" fn module_exec(module: *mut PyObject) -> c_int {
    let names = unsafe { PyModule_GetState(module) as *mut State };
    if names.is_null() {
        return -1;
    }
    unsafe {
        for (slot, name) in [
            (&mut (*names).popleft, c"popleft"),
            (&mut (*names).append, c"append"),
            (&mut (*names).cancelled, c"_cancelled"),
            (&mut (*names).run, c"_run"),
            (&mut (*names).when, c"_when"),
            (&mut (*names).scheduled, c"_scheduled"),
        ] {
            *slot = PyUnicode_InternFromString(name.as_ptr());
            if (*slot).is_null() {
                return -1;
            }
        }
    }
    0
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

static METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"promote_due_timers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: promote_due_timers,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Move expired loop timers to the ready callback queue.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"pop_ready_handle".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: pop_ready_handle,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Take the next callback scheduled for this loop turn.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"dispatch_ready_handle".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: dispatch_ready_handle,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Run the next non-debug event-loop callback unless cancelled.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: 85,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 86,
        value: 2usize as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_asyncio_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust scheduling operations for asyncio event loops.".as_ptr() as *mut c_char,
    m_size: core::mem::size_of::<State>() as Py_ssize_t,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: Some(module_clear),
    m_free: Some(module_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__asyncio_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}

// A standalone extension has no standard runtime to own the panic handler.
// Static integration supplies the handler once through its owning runtime.
#[cfg(not(feature = "static-module"))]
unsafe extern "C" {
    fn abort() -> !;
}

#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    unsafe { abort() }
}
