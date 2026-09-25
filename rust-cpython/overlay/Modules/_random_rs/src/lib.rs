use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_IndexError,
    PyExc_TypeError, PyLong_FromSsize_t, PyMethodDef, PyMethodDefFuncPointer,
    PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot,
    PyNumber_Subtract, PyObject,
    PyObject_CallOneArg, PyObject_GetItem, PyObject_GetIter, PyObject_SetItem,
    PyObject_Size, PySequence_Contains, PyIter_Next, Py_IncRef, Py_ssize_t,
};

unsafe fn set_type_error(message: &str) {
    if let Ok(message) = std::ffi::CString::new(message) {
        unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    } else {
        unsafe { PyErr_SetString(PyExc_TypeError, c"invalid argument".as_ptr()) };
    }
}

unsafe fn check_arity(actual: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if actual == expected {
        true
    } else {
        unsafe { set_type_error("invalid number of arguments") };
        false
    }
}

unsafe fn call_randbelow(randbelow: *mut PyObject, upper: *mut PyObject) -> *mut PyObject {
    unsafe { PyObject_CallOneArg(randbelow, upper) }
}

unsafe fn set_item(
    container: *mut PyObject,
    index: *mut PyObject,
    item: *mut PyObject,
) -> bool {
    let status = unsafe { PyObject_SetItem(container, index, item) };
    unsafe { Py_DecRef(item) };
    status == 0
}

unsafe fn next_index(iterator: *mut PyObject) -> Result<Option<*mut PyObject>, ()> {
    let index = unsafe { PyIter_Next(iterator) };
    if !index.is_null() {
        return Ok(Some(index));
    }
    if unsafe { PyErr_Occurred() }.is_null() {
        Ok(None)
    } else {
        Err(())
    }
}

unsafe fn sample_pool(
    pool: *mut PyObject,
    result: *mut PyObject,
    indices: *mut PyObject,
    population_size: *mut PyObject,
    randbelow: *mut PyObject,
) -> bool {
    let iterator = unsafe { PyObject_GetIter(indices) };
    if iterator.is_null() {
        return false;
    }
    let one = unsafe { PyLong_FromSsize_t(1) };
    if one.is_null() {
        unsafe { Py_DecRef(iterator) };
        return false;
    }
    loop {
        let index = match unsafe { next_index(iterator) } {
            Ok(Some(index)) => index,
            Ok(None) => break,
            Err(()) => {
                unsafe {
                    Py_DecRef(one);
                    Py_DecRef(iterator);
                }
                return false;
            }
        };
        let upper = unsafe { PyNumber_Subtract(population_size, index) };
        if upper.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let selected_index = unsafe { call_randbelow(randbelow, upper) };
        unsafe { Py_DecRef(upper) };
        if selected_index.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let selected = unsafe { PyObject_GetItem(pool, selected_index) };
        if selected.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        if !unsafe { set_item(result, index, selected) } {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let end = unsafe { PyNumber_Subtract(population_size, index) };
        if end.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let last_index = unsafe { PyNumber_Subtract(end, one) };
        unsafe { Py_DecRef(end) };
        if last_index.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let replacement = unsafe { PyObject_GetItem(pool, last_index) };
        unsafe { Py_DecRef(last_index) };
        if replacement.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let updated = unsafe { PyObject_SetItem(pool, selected_index, replacement) };
        unsafe {
            Py_DecRef(replacement);
            Py_DecRef(selected_index);
            Py_DecRef(index);
        }
        if updated != 0 {
            unsafe {
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
    }
    unsafe {
        Py_DecRef(one);
        Py_DecRef(iterator);
    }
    true
}

unsafe fn sample_selected(
    population: *mut PyObject,
    selected: *mut PyObject,
    selected_add: *mut PyObject,
    result: *mut PyObject,
    indices: *mut PyObject,
    population_size: *mut PyObject,
    randbelow: *mut PyObject,
) -> bool {
    let iterator = unsafe { PyObject_GetIter(indices) };
    if iterator.is_null() {
        return false;
    }
    loop {
        let index = match unsafe { next_index(iterator) } {
            Ok(Some(index)) => index,
            Ok(None) => break,
            Err(()) => {
                unsafe { Py_DecRef(iterator) };
                return false;
            }
        };
        let mut selected_index = unsafe { call_randbelow(randbelow, population_size) };
        if selected_index.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        loop {
            let contains = unsafe { PySequence_Contains(selected, selected_index) };
            if contains < 0 {
                unsafe {
                    Py_DecRef(selected_index);
                    Py_DecRef(index);
                    Py_DecRef(iterator);
                }
                return false;
            }
            if contains == 0 {
                break;
            }
            unsafe { Py_DecRef(selected_index) };
            selected_index = unsafe { call_randbelow(randbelow, population_size) };
            if selected_index.is_null() {
                unsafe {
                    Py_DecRef(index);
                    Py_DecRef(iterator);
                }
                return false;
            }
        }
        let added = unsafe { PyObject_CallOneArg(selected_add, selected_index) };
        if added.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        unsafe { Py_DecRef(added) };
        let item = unsafe { PyObject_GetItem(population, selected_index) };
        unsafe { Py_DecRef(selected_index) };
        if item.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        if !unsafe { set_item(result, index, item) } {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        unsafe { Py_DecRef(index) };
    }
    unsafe { Py_DecRef(iterator) };
    true
}

unsafe extern "C" fn choice(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 2) } {
        return ptr::null_mut();
    }
    let sequence = unsafe { *args };
    let length = unsafe { PyObject_Size(sequence) };
    if length < 0 {
        return ptr::null_mut();
    }
    if length == 0 {
        unsafe { PyErr_SetString(PyExc_IndexError, c"Cannot choose from an empty sequence".as_ptr()) };
        return ptr::null_mut();
    }
    let upper = unsafe { PyLong_FromSsize_t(length) };
    if upper.is_null() {
        return ptr::null_mut();
    }
    let index = unsafe { call_randbelow(*args.add(1), upper) };
    unsafe { Py_DecRef(upper) };
    if index.is_null() {
        return ptr::null_mut();
    }
    let item = unsafe { PyObject_GetItem(sequence, index) };
    unsafe { Py_DecRef(index) };
    item
}

unsafe extern "C" fn sample_pool_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 5) } {
        return ptr::null_mut();
    }
    let pool = unsafe { *args };
    let result = unsafe { *args.add(1) };
    let indices = unsafe { *args.add(2) };
    let population_size = unsafe { *args.add(3) };
    let randbelow = unsafe { *args.add(4) };
    if !unsafe { sample_pool(pool, result, indices, population_size, randbelow) } {
        return ptr::null_mut();
    }
    unsafe { Py_IncRef(result) };
    result
}

unsafe extern "C" fn sample_selected_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 7) } {
        return ptr::null_mut();
    }
    let population = unsafe { *args };
    let selected = unsafe { *args.add(1) };
    let selected_add = unsafe { *args.add(2) };
    let result = unsafe { *args.add(3) };
    let indices = unsafe { *args.add(4) };
    let population_size = unsafe { *args.add(5) };
    let randbelow = unsafe { *args.add(6) };
    if !unsafe {
        sample_selected(
            population,
            selected,
            selected_add,
            result,
            indices,
            population_size,
            randbelow,
        )
    } {
        return ptr::null_mut();
    }
    unsafe { Py_IncRef(result) };
    result
}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

const PY_MOD_MULTIPLE_INTERPRETERS_SLOT: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: usize = 2;

struct ModuleSlots(UnsafeCell<[PyModuleDef_Slot; 2]>);

unsafe impl Sync for ModuleSlots {}

static MODULE_SLOTS: ModuleSlots = ModuleSlots(UnsafeCell::new([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS_SLOT,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]));

static MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"choice".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: choice },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Choose an element using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"sample_pool".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: sample_pool_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Sample a sequence using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"sample_selected".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: sample_selected_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Sample a sequence using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_random_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust sequence sampling primitives for random.Random".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: MODULE_SLOTS.0.get().cast(),
        m_traverse: None,
        m_clear: None,
        m_free: None,
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__random_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
