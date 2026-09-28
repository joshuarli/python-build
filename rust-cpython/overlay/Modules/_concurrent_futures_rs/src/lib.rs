use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_TypeError, Py_GetConstant,
    PyIter_Next, PyLong_FromLong, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot, PyObject,
    PyObject_CallOneArg, PyObject_GetAttrString, PyObject_GetIter,
    PyObject_IsTrue, PyObject_SetAttrString, Py_ssize_t,
};

unsafe extern "C" {
    fn PyObject_RichCompare(left: *mut PyObject, right: *mut PyObject, op: c_int)
        -> *mut PyObject;
}

const PY_EQ: c_int = 2;
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

struct Owned(*mut PyObject);

impl Owned {
    unsafe fn from_owned(object: *mut PyObject) -> Option<Self> {
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

unsafe fn get_attr(object: *mut PyObject, name: &'static std::ffi::CStr) -> Option<Owned> {
    unsafe { Owned::from_owned(PyObject_GetAttrString(object, name.as_ptr())) }
}

unsafe fn set_attr(
    object: *mut PyObject,
    name: &'static std::ffi::CStr,
    value: *mut PyObject,
) -> bool {
    unsafe { PyObject_SetAttrString(object, name.as_ptr(), value) == 0 }
}

unsafe fn equal(left: *mut PyObject, right: *mut PyObject) -> Option<bool> {
    let comparison = unsafe { Owned::from_owned(PyObject_RichCompare(left, right, PY_EQ)) }?;
    match unsafe { PyObject_IsTrue(comparison.as_ptr()) } {
        -1 => None,
        result => Some(result != 0),
    }
}

unsafe fn notify_waiters(future: *mut PyObject, method_name: &'static std::ffi::CStr) -> bool {
    let Some(waiters) = (unsafe { get_attr(future, c"_waiters") }) else {
        return false;
    };
    let Some(iterator) = (unsafe { Owned::from_owned(PyObject_GetIter(waiters.as_ptr())) }) else {
        return false;
    };

    loop {
        let waiter = unsafe { PyIter_Next(iterator.as_ptr()) };
        let Some(waiter) = (unsafe { Owned::from_owned(waiter) }) else {
            return unsafe { PyErr_Occurred() }.is_null();
        };
        let Some(method) = (unsafe { get_attr(waiter.as_ptr(), method_name) }) else {
            return false;
        };
        let notified = unsafe { PyObject_CallOneArg(method.as_ptr(), future) };
        if notified.is_null() {
            return false;
        }
        unsafe { Py_DecRef(notified) };
    }
}

unsafe fn arity_error(expected: Py_ssize_t) -> *mut PyObject {
    let message = match expected {
        3 => c"future completion requires three arguments",
        _ => c"future scheduling transition requires five arguments",
    };
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

unsafe extern "C" fn set_running_or_notify_cancel(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 5 {
        return unsafe { arity_error(5) };
    }
    let future = unsafe { *args };
    let Some(state) = (unsafe { get_attr(future, c"_state") }) else {
        return ptr::null_mut();
    };
    let cancelled = match unsafe { equal(state.as_ptr(), *args.add(3)) } {
        Some(value) => value,
        None => return ptr::null_mut(),
    };

    let status = if cancelled {
        if !unsafe { set_attr(future, c"_state", *args.add(4)) } {
            return ptr::null_mut();
        }
        if !unsafe { notify_waiters(future, c"add_cancelled") } {
            return ptr::null_mut();
        }
        0
    } else {
        let Some(current_state) = (unsafe { get_attr(future, c"_state") }) else {
            return ptr::null_mut();
        };
        let pending = match unsafe { equal(current_state.as_ptr(), *args.add(1)) } {
            Some(value) => value,
            None => return ptr::null_mut(),
        };
        if !pending {
            2
        } else {
            if !unsafe { set_attr(future, c"_state", *args.add(2)) } {
                return ptr::null_mut();
            }
            1
        }
    };
    unsafe { PyLong_FromLong(status as c_long) }
}

unsafe fn complete_future(
    future: *mut PyObject,
    value: *mut PyObject,
    finished: *mut PyObject,
    result_attribute: &'static std::ffi::CStr,
    waiter_method: &'static std::ffi::CStr,
) -> *mut PyObject {
    if !unsafe { set_attr(future, result_attribute, value) }
        || !unsafe { set_attr(future, c"_state", finished) }
        || !unsafe { notify_waiters(future, waiter_method) }
    {
        return ptr::null_mut();
    }
    unsafe { Py_GetConstant(0) }
}

unsafe extern "C" fn set_result(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { arity_error(3) };
    }
    unsafe { complete_future(*args, *args.add(1), *args.add(2), c"_result", c"add_result") }
}

unsafe extern "C" fn set_exception(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { arity_error(3) };
    }
    unsafe {
        complete_future(
            *args,
            *args.add(1),
            *args.add(2),
            c"_exception",
            c"add_exception",
        )
    }
}

static METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"set_running_or_notify_cancel".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: set_running_or_notify_cancel,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Apply an Executor's Future scheduling transition under its condition lock."
            .as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"set_result".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: set_result },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Store a Future result, finish it, and notify its waiters.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"set_exception".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: set_exception },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Store a Future exception, finish it, and notify its waiters.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

unsafe extern "C" fn exec_module(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_EXEC,
        value: exec_module as *const () as *mut c_void,
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
    m_name: c"_concurrent_futures_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust Future scheduling and result state transitions.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__concurrent_futures_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
