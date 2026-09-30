#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;

mod ffi;
use ffi::*;
mod buffer;
use buffer::MatchBuffer;

fn set_type_error(message: &'static core::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

fn set_value_error(message: &'static core::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
}

unsafe fn read_integer_list(arg: *mut PyObject) -> Option<MatchBuffer<i64>> {
    let length = unsafe { PyList_Size(arg) };
    if length < 0 {
        return None;
    }
    let mut values = MatchBuffer::new();
    if values.try_reserve_exact(length as usize).is_err() {
        unsafe { PyErr_NoMemory() };
        return None;
    }
    for index in 0..length {
        let item = unsafe { PyList_GetItem(arg, index) };
        if item.is_null() {
            return None;
        }
        let value = unsafe { PyLong_AsLongLong(item) };
        if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            return None;
        }
        values.push(value);
    }
    Some(values)
}

unsafe fn read_bound(arg: *mut PyObject) -> Option<usize> {
    let value = unsafe { PyLong_AsLongLong(arg) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    if value < 0 {
        set_value_error(c"sequence bounds must be non-negative");
        return None;
    }
    usize::try_from(value).ok()
}

unsafe extern "C" fn compare_tokens(left: *const c_void, right: *const c_void) -> c_int {
    let left = unsafe { *left.cast::<i64>() };
    let right = unsafe { *right.cast::<i64>() };
    (left > right) as c_int - (left < right) as c_int
}

unsafe extern "C" fn compare_positions(left: *const c_void, right: *const c_void) -> c_int {
    let left = unsafe { *left.cast::<(i64, usize)>() };
    let right = unsafe { *right.cast::<(i64, usize)>() };
    (left > right) as c_int - (left < right) as c_int
}

fn longest_match(
    a: &[i64],
    b: &[i64],
    popular: &mut [i64],
    alo: usize,
    ahi: usize,
    blo: usize,
    bhi: usize,
) -> Option<(usize, usize, usize)> {
    if popular.len() > 1 {
        unsafe { qsort(popular.as_mut_ptr().cast(), popular.len(), core::mem::size_of::<i64>(), compare_tokens) };
    }
    let mut positions = MatchBuffer::new();
    if positions.try_reserve_exact(bhi - blo).is_err() {
        unsafe { PyErr_NoMemory() };
        return None;
    }
    for index in blo..bhi {
        if popular.binary_search(&b[index]).is_err() {
            positions.push((b[index], index));
        }
    }
    // Ordering by token then position preserves the earliest-position tie rule
    // while keeping all occurrences in one buffer instead of separate heaps.
    if positions.len() > 1 {
        unsafe { qsort(positions.as_mut_ptr().cast(), positions.len(), core::mem::size_of::<(i64, usize)>(), compare_positions) };
    }
    let mut best_i = alo;
    let mut best_j = blo;
    let mut best_size = 0;
    let mut previous = MatchBuffer::<(usize, usize)>::new();
    let mut current = MatchBuffer::<(usize, usize)>::new();
    for i in alo..ahi {
        current.clear();
        let start = positions.partition_point(|&(token, _)| token < a[i]);
        let end = positions.partition_point(|&(token, _)| token <= a[i]);
        if current.try_reserve(end - start).is_err() {
            unsafe { PyErr_NoMemory() };
            return None;
        }
        let mut predecessor = 0;
        for &(_, j) in &positions[start..end] {
            let mut size = 1;
            if j > blo {
                // Both rows are in ascending position order. A forward join
                // finds the preceding match length without hashing or clearing
                // a dense row for positions that did not match.
                while predecessor < previous.len() && previous[predecessor].0 < j - 1 {
                    predecessor += 1;
                }
                if predecessor < previous.len() && previous[predecessor].0 == j - 1 {
                    size += previous[predecessor].1;
                }
            }
            current.push((j, size));
            if size > best_size {
                best_i = i + 1 - size;
                best_j = j + 1 - size;
                best_size = size;
            }
        }
        core::mem::swap(&mut previous, &mut current);
    }

    // Popular elements are excluded only as match starting points. Python
    // still extends an adjacent match through them after finding its core.
    while best_i > alo && best_j > blo && a[best_i - 1] == b[best_j - 1] {
        best_i -= 1;
        best_j -= 1;
        best_size += 1;
    }
    while best_i + best_size < ahi
        && best_j + best_size < bhi
        && a[best_i + best_size] == b[best_j + best_size]
    {
        best_size += 1;
    }

    Some((best_i, best_j, best_size))
}

unsafe fn new_result(values: (usize, usize, usize)) -> *mut PyObject {
    let Ok(a) = i64::try_from(values.0) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    let Ok(b) = i64::try_from(values.1) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    let Ok(size) = i64::try_from(values.2) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };

    let tuple = unsafe { PyTuple_New(3) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    for (index, value) in [a, b, size].into_iter().enumerate() {
        let item = unsafe { PyLong_FromLongLong(value) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
    }
    tuple
}

unsafe extern "C" fn find_longest_match(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 7 {
        set_type_error(c"find_longest_match() takes exactly seven arguments");
        return ptr::null_mut();
    }
    let Some(a) = (unsafe { read_integer_list(*args) }) else {
        return ptr::null_mut();
    };
    let Some(b) = (unsafe { read_integer_list(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    let Some(mut popular) = (unsafe { read_integer_list(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    let Some(alo) = (unsafe { read_bound(*args.add(3)) }) else {
        return ptr::null_mut();
    };
    let Some(ahi) = (unsafe { read_bound(*args.add(4)) }) else {
        return ptr::null_mut();
    };
    let Some(blo) = (unsafe { read_bound(*args.add(5)) }) else {
        return ptr::null_mut();
    };
    let Some(bhi) = (unsafe { read_bound(*args.add(6)) }) else {
        return ptr::null_mut();
    };
    if alo > ahi || ahi > a.len() || blo > bhi || bhi > b.len() {
        set_value_error(c"sequence bounds are outside the input sequences");
        return ptr::null_mut();
    }

    let Some(result) = longest_match(&a, &b, &mut popular, alo, ahi, blo, bhi) else {
        return ptr::null_mut();
    };
    unsafe { new_result(result) }
}

pub extern "C" fn _difflib_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _difflib_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _DIFFLIB_RS_MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"find_longest_match".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: find_longest_match,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Find a longest matching block in integer token sequences.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _DIFFLIB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_difflib_rs".as_ptr() as *mut _,
        m_doc: c"Rust sequence matching helpers for difflib.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_DIFFLIB_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_difflib_rs_clear),
        m_free: Some(_difflib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__difflib_rs() -> *mut PyObject {
    _DIFFLIB_RS_MODULE.init_multi_phase()
}
