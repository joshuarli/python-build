use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, Py_IS_TYPE, PyErr_Occurred, PyErr_SetString, PyExc_TypeError, Py_GetConstant,
    PyIter_Next, PyList_GetItemRef, PyList_Size, PyList_Type, PyLong_FromLong, PyMethodDef,
    PyMethodDefFuncPointer, PyModule_GetState, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyModuleDef_Slot, PyObject, PyObject_GetAttr, PyObject_GetIter,
    PyObject_IsTrue, PyObject_SetAttr, PyObject_VectorcallMethod, PyUnicode_InternFromString,
    Py_ssize_t,
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

/// Interned attribute and method names, one set per module object, so a
/// transition never builds a temporary `str` for an attribute lookup.
struct State {
    state: *mut PyObject,
    waiters: *mut PyObject,
    result: *mut PyObject,
    exception: *mut PyObject,
    add_result: *mut PyObject,
    add_exception: *mut PyObject,
    add_cancelled: *mut PyObject,
}

unsafe fn names<'a>(module: *mut PyObject) -> &'a State {
    unsafe { &*(PyModule_GetState(module) as *const State) }
}

unsafe fn get_attr(object: *mut PyObject, name: *mut PyObject) -> Option<Owned> {
    unsafe { Owned::from_owned(PyObject_GetAttr(object, name)) }
}

unsafe fn set_attr(object: *mut PyObject, name: *mut PyObject, value: *mut PyObject) -> bool {
    unsafe { PyObject_SetAttr(object, name, value) == 0 }
}

unsafe fn equal(left: *mut PyObject, right: *mut PyObject) -> Option<bool> {
    if left == right {
        return Some(true);
    }
    let comparison = unsafe { Owned::from_owned(PyObject_RichCompare(left, right, PY_EQ)) }?;
    match unsafe { PyObject_IsTrue(comparison.as_ptr()) } {
        -1 => None,
        result => Some(result != 0),
    }
}

unsafe fn notify_one(waiter: *mut PyObject, method: *mut PyObject, future: *mut PyObject) -> bool {
    let args = [waiter, future];
    let notified = unsafe { PyObject_VectorcallMethod(method, args.as_ptr(), 2, ptr::null_mut()) };
    if notified.is_null() {
        return false;
    }
    unsafe { Py_DecRef(notified) };
    true
}

unsafe fn notify_waiters(future: *mut PyObject, names: &State, method: *mut PyObject) -> bool {
    let Some(waiters) = (unsafe { get_attr(future, names.waiters) }) else {
        return false;
    };
    if unsafe { Py_IS_TYPE(waiters.as_ptr(), ptr::addr_of_mut!(PyList_Type)) } != 0 {
        // The stdlib keeps waiters in a plain list; index it so no iterator
        // object is built for the common empty or short list.
        let mut index: Py_ssize_t = 0;
        loop {
            if index >= unsafe { PyList_Size(waiters.as_ptr()) } {
                return true;
            }
            let Some(waiter) =
                (unsafe { Owned::from_owned(PyList_GetItemRef(waiters.as_ptr(), index)) })
            else {
                return false;
            };
            if !unsafe { notify_one(waiter.as_ptr(), method, future) } {
                return false;
            }
            index += 1;
        }
    }
    let Some(iterator) = (unsafe { Owned::from_owned(PyObject_GetIter(waiters.as_ptr())) }) else {
        return false;
    };
    loop {
        let waiter = unsafe { PyIter_Next(iterator.as_ptr()) };
        let Some(waiter) = (unsafe { Owned::from_owned(waiter) }) else {
            return unsafe { PyErr_Occurred() }.is_null();
        };
        if !unsafe { notify_one(waiter.as_ptr(), method, future) } {
            return false;
        }
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
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 5 {
        return unsafe { arity_error(5) };
    }
    let names = unsafe { names(module) };
    let future = unsafe { *args };
    let Some(state) = (unsafe { get_attr(future, names.state) }) else {
        return ptr::null_mut();
    };
    let cancelled = match unsafe { equal(state.as_ptr(), *args.add(3)) } {
        Some(value) => value,
        None => return ptr::null_mut(),
    };

    let status = if cancelled {
        if !unsafe { set_attr(future, names.state, *args.add(4)) } {
            return ptr::null_mut();
        }
        if !unsafe { notify_waiters(future, names, names.add_cancelled) } {
            return ptr::null_mut();
        }
        0
    } else {
        // The state was read once under the future's condition lock and
        // nothing has run since, so it is still current.
        let pending = match unsafe { equal(state.as_ptr(), *args.add(1)) } {
            Some(value) => value,
            None => return ptr::null_mut(),
        };
        if !pending {
            2
        } else {
            if !unsafe { set_attr(future, names.state, *args.add(2)) } {
                return ptr::null_mut();
            }
            1
        }
    };
    unsafe { PyLong_FromLong(status as c_long) }
}

unsafe fn complete_future(
    names: &State,
    future: *mut PyObject,
    value: *mut PyObject,
    finished: *mut PyObject,
    result_attribute: *mut PyObject,
    waiter_method: *mut PyObject,
) -> *mut PyObject {
    if !unsafe { set_attr(future, result_attribute, value) }
        || !unsafe { set_attr(future, names.state, finished) }
        || !unsafe { notify_waiters(future, names, waiter_method) }
    {
        return ptr::null_mut();
    }
    unsafe { Py_GetConstant(0) }
}

unsafe extern "C" fn set_result(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { arity_error(3) };
    }
    let names = unsafe { names(module) };
    unsafe {
        complete_future(
            names,
            *args,
            *args.add(1),
            *args.add(2),
            names.result,
            names.add_result,
        )
    }
}

unsafe extern "C" fn set_exception(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { arity_error(3) };
    }
    let names = unsafe { names(module) };
    unsafe {
        complete_future(
            names,
            *args,
            *args.add(1),
            *args.add(2),
            names.exception,
            names.add_exception,
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

unsafe extern "C" fn module_clear(module: *mut PyObject) -> c_int {
    let names = unsafe { PyModule_GetState(module) as *mut State };
    if !names.is_null() {
        unsafe {
            for slot in [
                &mut (*names).state,
                &mut (*names).waiters,
                &mut (*names).result,
                &mut (*names).exception,
                &mut (*names).add_result,
                &mut (*names).add_exception,
                &mut (*names).add_cancelled,
            ] {
                let object = std::mem::replace(slot, ptr::null_mut());
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

unsafe extern "C" fn exec_module(module: *mut PyObject) -> c_int {
    let names = unsafe { PyModule_GetState(module) as *mut State };
    if names.is_null() {
        return -1;
    }
    unsafe {
        for (slot, name) in [
            (&mut (*names).state, c"_state"),
            (&mut (*names).waiters, c"_waiters"),
            (&mut (*names).result, c"_result"),
            (&mut (*names).exception, c"_exception"),
            (&mut (*names).add_result, c"add_result"),
            (&mut (*names).add_exception, c"add_exception"),
            (&mut (*names).add_cancelled, c"add_cancelled"),
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
    m_size: std::mem::size_of::<State>() as Py_ssize_t,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: Some(module_clear),
    m_free: Some(module_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__concurrent_futures_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
