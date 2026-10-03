use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, Py_DecRef, PyErr_Occurred, PyErr_SetNone, PyErr_SetString,
    PyExc_StopIteration, PyExc_TypeError, PyLong_AsSsize_t, PyLong_FromLong,
    PyLong_FromSsize_t, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot, Py_NewRef, PyObject, PyObject_Call,
    PyObject_CallOneArg, PyObject_GetIter, PyObject_IsTrue, PyIter_Next, PySequence_Tuple,
    PyTuple_New, PyTuple_SetItem, Py_ssize_t, _Py_NoneStruct,
};

unsafe fn none() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct).cast()) }
}

unsafe fn iteration_done() -> *mut PyObject {
    if unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_SetNone(PyExc_StopIteration) };
    }
    ptr::null_mut()
}

unsafe fn tuple2(first: *mut PyObject, second: *mut PyObject) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        unsafe {
            Py_DecRef(first);
            Py_DecRef(second);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, first) } != 0 {
        unsafe {
            Py_DecRef(second);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 1, second) } != 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

unsafe fn tuple3(
    first: *mut PyObject,
    second: *mut PyObject,
    third: *mut PyObject,
) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(3) };
    if tuple.is_null() {
        unsafe {
            Py_DecRef(first);
            Py_DecRef(second);
            Py_DecRef(third);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, first) } != 0 {
        unsafe {
            Py_DecRef(second);
            Py_DecRef(third);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 1, second) } != 0 {
        unsafe {
            Py_DecRef(third);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 2, third) } != 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

unsafe fn chain_state(status: c_long, value: *mut PyObject) -> *mut PyObject {
    let status = unsafe { PyLong_FromLong(status) };
    if status.is_null() {
        unsafe { Py_DecRef(value) };
        return ptr::null_mut();
    }
    unsafe { tuple2(status, value) }
}

unsafe fn require_args(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    expected: Py_ssize_t,
    function: *const c_char,
) -> Result<*mut *mut PyObject, ()> {
    if nargs != expected {
        unsafe { PyErr_SetString(PyExc_TypeError, function) };
        return Err(());
    }
    if args.is_null() {
        unsafe { PyErr_SetString(PyExc_TypeError, function) };
        return Err(());
    }
    Ok(args)
}

unsafe fn is_none(object: *mut PyObject) -> bool {
    object == ptr::addr_of_mut!(_Py_NoneStruct).cast()
}

unsafe extern "C" fn chain_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 2, c"_chain_next expects two arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let source = unsafe { *args };
    let active_arg = unsafe { *args.add(1) };
    if unsafe { is_none(active_arg) } {
        let iterable = unsafe { PyIter_Next(source) };
        if iterable.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                return unsafe { chain_state(3, none()) };
            }
            return ptr::null_mut();
        }
        let active = unsafe { PyObject_GetIter(iterable) };
        unsafe { Py_DecRef(iterable) };
        if active.is_null() {
            return ptr::null_mut();
        }
        return unsafe { chain_state(1, active) };
    }

    let item = unsafe { PyIter_Next(active_arg) };
    if item.is_null() {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { chain_state(2, none()) };
    }
    unsafe { chain_state(0, item) }
}

unsafe extern "C" fn compress_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 2, c"_compress_next expects two arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let data = unsafe { *args };
    let selectors = unsafe { *args.add(1) };
    loop {
        let datum = unsafe { PyIter_Next(data) };
        if datum.is_null() {
            return unsafe { iteration_done() };
        }
        let selector = unsafe { PyIter_Next(selectors) };
        if selector.is_null() {
            unsafe { Py_DecRef(datum) };
            return unsafe { iteration_done() };
        }
        let selected = unsafe { PyObject_IsTrue(selector) };
        unsafe { Py_DecRef(selector) };
        if selected > 0 {
            return datum;
        }
        unsafe { Py_DecRef(datum) };
        if selected < 0 {
            return ptr::null_mut();
        }
    }
}

unsafe extern "C" fn dropwhile_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 3, c"_dropwhile_next expects three arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let function = unsafe { *args };
    let iterable = unsafe { *args.add(1) };
    let mut started = unsafe { PyObject_IsTrue(*args.add(2)) };
    if started < 0 {
        return ptr::null_mut();
    }

    loop {
        let item = unsafe { PyIter_Next(iterable) };
        if item.is_null() {
            return unsafe { iteration_done() };
        }
        if started != 0 {
            let flag = unsafe { PyBool_FromLong(1) };
            if flag.is_null() {
                unsafe { Py_DecRef(item) };
                return ptr::null_mut();
            }
            return unsafe { tuple2(flag, item) };
        }
        let predicate = unsafe { PyObject_CallOneArg(function, item) };
        if predicate.is_null() {
            unsafe { Py_DecRef(item) };
            return ptr::null_mut();
        }
        let passed = unsafe { PyObject_IsTrue(predicate) };
        unsafe { Py_DecRef(predicate) };
        if passed < 0 {
            unsafe { Py_DecRef(item) };
            return ptr::null_mut();
        }
        if passed == 0 {
            started = 1;
            let flag = unsafe { PyBool_FromLong(1) };
            if flag.is_null() {
                unsafe { Py_DecRef(item) };
                return ptr::null_mut();
            }
            return unsafe { tuple2(flag, item) };
        }
        unsafe { Py_DecRef(item) };
    }
}

unsafe extern "C" fn filterfalse_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 2, c"_filterfalse_next expects two arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let function = unsafe { *args };
    let iterable = unsafe { *args.add(1) };
    loop {
        let item = unsafe { PyIter_Next(iterable) };
        if item.is_null() {
            return unsafe { iteration_done() };
        }
        let predicate = if unsafe { is_none(function) } {
            unsafe { Py_NewRef(item) }
        } else {
            unsafe { PyObject_CallOneArg(function, item) }
        };
        if predicate.is_null() {
            unsafe { Py_DecRef(item) };
            return ptr::null_mut();
        }
        let passed = unsafe { PyObject_IsTrue(predicate) };
        unsafe { Py_DecRef(predicate) };
        if passed == 0 {
            return item;
        }
        unsafe { Py_DecRef(item) };
        if passed < 0 {
            return ptr::null_mut();
        }
    }
}

unsafe fn parse_ssize(object: *mut PyObject) -> Result<Py_ssize_t, ()> {
    let value = unsafe { PyLong_AsSsize_t(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        Err(())
    } else {
        Ok(value)
    }
}

unsafe extern "C" fn islice_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 5, c"_islice_next expects five arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let iterable = unsafe { *args };
    let mut next = match unsafe { parse_ssize(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let stop = match unsafe { parse_ssize(*args.add(2)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let step = match unsafe { parse_ssize(*args.add(3)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let mut count = match unsafe { parse_ssize(*args.add(4)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };

    while count < next {
        let skipped = unsafe { PyIter_Next(iterable) };
        if skipped.is_null() {
            return unsafe { iteration_done() };
        }
        unsafe { Py_DecRef(skipped) };
        count = count.wrapping_add(1);
    }
    if stop != -1 && count >= stop {
        return unsafe { iteration_done() };
    }
    let item = unsafe { PyIter_Next(iterable) };
    if item.is_null() {
        return unsafe { iteration_done() };
    }
    count = count.wrapping_add(1);
    let old_next = next;
    next = next.wrapping_add(step);
    if next < old_next || (stop != -1 && next > stop) {
        next = stop;
    }
    let next_object = unsafe { PyLong_FromSsize_t(next) };
    if next_object.is_null() {
        unsafe { Py_DecRef(item) };
        return ptr::null_mut();
    }
    let count_object = unsafe { PyLong_FromSsize_t(count) };
    if count_object.is_null() {
        unsafe {
            Py_DecRef(item);
            Py_DecRef(next_object);
        }
        return ptr::null_mut();
    }
    unsafe { tuple3(item, next_object, count_object) }
}

unsafe extern "C" fn starmap_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 2, c"_starmap_next expects two arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let function = unsafe { *args };
    let iterable = unsafe { *args.add(1) };
    let item = unsafe { PyIter_Next(iterable) };
    if item.is_null() {
        return unsafe { iteration_done() };
    }
    let call_args = unsafe { PySequence_Tuple(item) };
    unsafe { Py_DecRef(item) };
    if call_args.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_Call(function, call_args, ptr::null_mut()) };
    unsafe { Py_DecRef(call_args) };
    result
}

unsafe extern "C" fn takewhile_next(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let args = match unsafe { require_args(args, nargs, 3, c"_takewhile_next expects three arguments".as_ptr()) } {
        Ok(args) => args,
        Err(()) => return ptr::null_mut(),
    };
    let function = unsafe { *args };
    let iterable = unsafe { *args.add(1) };
    let stopped = unsafe { PyObject_IsTrue(*args.add(2)) };
    if stopped < 0 {
        return ptr::null_mut();
    }
    if stopped != 0 {
        return unsafe { iteration_done() };
    }
    let item = unsafe { PyIter_Next(iterable) };
    if item.is_null() {
        return unsafe { iteration_done() };
    }
    let predicate = unsafe { PyObject_CallOneArg(function, item) };
    if predicate.is_null() {
        unsafe { Py_DecRef(item) };
        return ptr::null_mut();
    }
    let passed = unsafe { PyObject_IsTrue(predicate) };
    unsafe { Py_DecRef(predicate) };
    if passed < 0 {
        unsafe { Py_DecRef(item) };
        return ptr::null_mut();
    }
    if passed > 0 {
        let flag = unsafe { PyBool_FromLong(1) };
        if flag.is_null() {
            unsafe { Py_DecRef(item) };
            return ptr::null_mut();
        }
        return unsafe { tuple2(flag, item) };
    }
    unsafe { Py_DecRef(item) };
    let flag = unsafe { PyBool_FromLong(0) };
    if flag.is_null() {
        return ptr::null_mut();
    }
    unsafe { tuple2(flag, none()) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

// These slot IDs and marker values are defined by the pinned CPython 3.16 fork.
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
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

static METHODS: [PyMethodDef; 8] = [
    PyMethodDef {
        ml_name: c"_chain_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: chain_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a chain iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_compress_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compress_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a compress iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_dropwhile_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dropwhile_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a dropwhile iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_filterfalse_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: filterfalse_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a filterfalse iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_islice_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: islice_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance an islice iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_starmap_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: starmap_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a starmap iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_takewhile_next".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: takewhile_next },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a takewhile iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_itertools_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust iterator transformation steps.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__itertools_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
