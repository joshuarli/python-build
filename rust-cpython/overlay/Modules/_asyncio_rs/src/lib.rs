use std::cell::UnsafeCell;
use std::ffi::{c_char, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, Py_DecRef, PyErr_SetString, PyExc_TypeError,
    PyList_GetItemRef, PyList_Size, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot, PyObject,
    PyObject_CallNoArgs, PyObject_CallOneArg, PyObject_GetAttrString, PyObject_IsTrue,
    PyObject_RichCompareBool, PyObject_SetAttrString, Py_NewRef, Py_ssize_t,
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

unsafe extern "C" fn promote_due_timers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 4 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"promote_due_timers requires four arguments".as_ptr());
        }
        return ptr::null_mut();
    }

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
        let Some(when) = Owned::new(unsafe {
            PyObject_GetAttrString(head.as_ptr(), c"_when".as_ptr())
        }) else {
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
        let Some(false_object) = Owned::new(unsafe { PyBool_FromLong(0) }) else {
            return ptr::null_mut();
        };
        if unsafe {
            PyObject_SetAttrString(handle.as_ptr(), c"_scheduled".as_ptr(), false_object.as_ptr())
        } < 0 {
            return ptr::null_mut();
        }
        let Some(append) = Owned::new(unsafe { PyObject_GetAttrString(ready, c"append".as_ptr()) })
        else {
            return ptr::null_mut();
        };
        if Owned::new(unsafe { PyObject_CallOneArg(append.as_ptr(), handle.as_ptr()) }).is_none() {
            return ptr::null_mut();
        }
    }

    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn pop_ready_handle(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"pop_ready_handle requires one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let Some(pop) = Owned::new(unsafe { PyObject_GetAttrString(*args, c"popleft".as_ptr()) })
    else {
        return ptr::null_mut();
    };
    unsafe { PyObject_CallNoArgs(pop.as_ptr()) }
}

unsafe extern "C" fn dispatch_ready_handle(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"dispatch_ready_handle requires one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let Some(handle) = Owned::new(unsafe { pop_ready_handle(_module, args, nargs) }) else {
        return ptr::null_mut();
    };
    let Some(cancelled) = Owned::new(unsafe {
        PyObject_GetAttrString(handle.as_ptr(), c"_cancelled".as_ptr())
    }) else {
        return ptr::null_mut();
    };
    let is_cancelled = unsafe { PyObject_IsTrue(cancelled.as_ptr()) };
    if is_cancelled < 0 {
        return ptr::null_mut();
    }
    if is_cancelled == 0 {
        let Some(run) = Owned::new(unsafe { PyObject_GetAttrString(handle.as_ptr(), c"_run".as_ptr()) })
        else {
            return ptr::null_mut();
        };
        if Owned::new(unsafe { PyObject_CallNoArgs(run.as_ptr()) }).is_none() {
            return ptr::null_mut();
        }
    }
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 2]);

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
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__asyncio_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
