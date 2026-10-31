//! Sequence choice and sampling through Python generator callbacks.
//!
//! Direct CPython declarations avoid adding a separate standard runtime
//! to the extension. The builtin route uses the interpreter's existing
//! Rust archive and panic runtime. Python owns all sampling allocations.
#![cfg_attr(feature = "freestanding", no_std)]

use core::ptr;

use cpython_binding::ffi::{
    PyErr_Occurred, PyErr_SetString, PyExc_IndexError, PyExc_TypeError, PyIter_Next,
    PyLong_FromSsize_t, PyMethodDef, PyNumber_Subtract, PyObject, PyObject_CallOneArg,
    PyObject_GetItem, PyObject_GetIter, PyObject_SetItem, PyObject_Size, PySequence_Contains,
    Py_DecRef, Py_IncRef, Py_ssize_t,
};
use cpython_binding::{Module, fastcall, method_table_end};
use cpython_binding::module::PER_INTERPRETER_GIL;

unsafe fn check_arity(actual: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if actual == expected {
        true
    } else {
        unsafe { PyErr_SetString(PyExc_TypeError, c"invalid number of arguments".as_ptr()) };
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

static MODULE_METHODS: [PyMethodDef; 4] = [
    fastcall(
        c"choice",
        choice,
        c"Choose an element using a Python generator callback",
    ),
    fastcall(
        c"sample_pool",
        sample_pool_method,
        c"Sample a sequence using a Python generator callback",
    ),
    fastcall(
        c"sample_selected",
        sample_selected_method,
        c"Sample a sequence using a Python generator callback",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_random_rs",
    c"Rust sequence sampling primitives for random.Random",
    &MODULE_METHODS,
).with_slots(&PER_INTERPRETER_GIL);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__random_rs() -> *mut PyObject {
    MODULE.init()
}
