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

// Legacy integer-token boundary for callers with pre-encoded sequences.
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

// Exact built-in values cannot invoke Python equality callbacks. Validate the
// whole pair before comparing anything: a changed list may contain a custom
// value whose comparison or finalizer must remain on the original tuple path.
// The live tuple factory must also be the built-in type; replacing it is an
// observable facade hook. GIL ownership and strong arguments keep both input
// containers and their immutable members alive without a copied list snapshot.
unsafe extern "C" fn snapshot_matches(
    _module: *mut PyObject, args: *mut *mut PyObject, nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"snapshot_matches() takes exactly three arguments");
        return ptr::null_mut();
    }
    let list = unsafe { *args };
    let snapshot = unsafe { *args.add(1) };
    let factory = unsafe { *args.add(2) };
    if unsafe { (*list).ob_type } != ptr::addr_of!(PyList_Type).cast_mut().cast()
        || unsafe { (*snapshot).ob_type } != ptr::addr_of!(PyTuple_Type).cast_mut().cast()
        || factory != ptr::addr_of!(PyTuple_Type).cast_mut().cast()
    {
        return unsafe { PyLong_FromLongLong(-1) };
    }
    let length = unsafe { PyList_Size(list) };
    let stored_length = unsafe { PyTuple_Size(snapshot) };
    for (container, count, is_list) in [(list, length, true), (snapshot, stored_length, false)] {
        for index in 0..count {
            let value = if is_list {
                unsafe { PyList_GetItem(container, index) }
            } else {
                unsafe { PyTuple_GetItem(container, index) }
            };
            let kind = unsafe { (*value).ob_type };
            if kind != ptr::addr_of!(PyLong_Type).cast_mut().cast()
                && kind != ptr::addr_of!(PyUnicode_Type).cast_mut().cast()
            {
                return unsafe { PyLong_FromLongLong(-1) };
            }
        }
    }
    if length != stored_length {
        return unsafe { PyLong_FromLongLong(0) };
    }
    for index in 0..length {
        let left = unsafe { PyList_GetItem(list, index) };
        let right = unsafe { PyTuple_GetItem(snapshot, index) };
        let equal = unsafe { PyObject_RichCompareBool(left, right, 2) };
        if equal < 0 {
            return ptr::null_mut();
        }
        if equal == 0 {
            return unsafe { PyLong_FromLongLong(0) };
        }
    }
    unsafe { PyLong_FromLongLong(1) }
}

unsafe fn read_builtin_tuple(arg: *mut PyObject) -> Option<usize> {
    if unsafe { (*arg).ob_type } != ptr::addr_of!(PyTuple_Type).cast_mut().cast() {
        set_type_error(c"matching values must be exact tuples");
        return None;
    }
    let length = unsafe { PyTuple_Size(arg) };
    for index in 0..length {
        let item = unsafe { PyTuple_GetItem(arg, index) };
        if item.is_null() {
            return None;
        }
        let kind = unsafe { (*item).ob_type };
        if kind != ptr::addr_of!(PyLong_Type).cast_mut().cast()
            && kind != ptr::addr_of!(PyUnicode_Type).cast_mut().cast()
        {
            set_type_error(c"matching values must be exact integers or strings");
            return None;
        }
    }
    Some(length as usize)
}

unsafe fn builtin_equal(a: *mut PyObject, ai: usize, b: *mut PyObject, bi: usize) -> bool {
    let left = unsafe { PyTuple_GetItem(a, ai as Py_ssize_t) };
    let right = unsafe { PyTuple_GetItem(b, bi as Py_ssize_t) };
    // Validated tuples retain their exact immutable values for the whole call.
    unsafe { PyObject_RichCompareBool(left, right, 2) == 1 }
}

unsafe fn indexed_match(
    a: *mut PyObject, b: *mut PyObject, index: *mut PyObject,
    alo: usize, ahi: usize, blo: usize, bhi: usize,
) -> Option<(usize, usize, usize)> {
    let (mut best_i, mut best_j, mut best_size) = (alo, blo, 0);
    let mut previous = MatchBuffer::<(usize, usize)>::new();
    let mut current = MatchBuffer::<(usize, usize)>::new();
    for i in alo..ahi {
        current.clear();
        let value = unsafe { PyTuple_GetItem(a, i as Py_ssize_t) };
        // Tuples retain the immutable values throughout this call. Position
        // lists are borrowed only until the next lookup, and exact integer
        // conversions cannot invoke a callback while a list is being scanned.
        let indices = unsafe { PyDict_GetItemWithError(index, value) };
        if indices.is_null() {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return None;
            }
        } else {
            let count = unsafe { PyList_Size(indices) };
            if count < 0 {
                return None;
            }
            if current.try_reserve(count as usize).is_err() {
                unsafe { PyErr_NoMemory() };
                return None;
            }
            let mut predecessor = 0;
            let mut last_j = None;
            for position in 0..count {
                let item = unsafe { PyList_GetItem(indices, position) };
                if item.is_null() {
                    return None;
                }
                if unsafe { (*item).ob_type } != ptr::addr_of!(PyLong_Type).cast_mut().cast() {
                    set_type_error(c"matching positions must be exact integers");
                    return None;
                }
                let j = unsafe { PyLong_AsLongLong(item) };
                if j == -1 && !unsafe { PyErr_Occurred() }.is_null() {
                    return None;
                }
                if let Some(last) = last_j {
                    if j <= last {
                        set_value_error(c"matching positions must be in ascending order");
                        return None;
                    }
                }
                last_j = Some(j);
                if j < 0 || (j as usize) < blo {
                    continue;
                }
                let j = j as usize;
                if j >= bhi {
                    break;
                }
                let mut size = 1;
                if j > blo {
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
        }
        core::mem::swap(&mut previous, &mut current);
    }
    // The supplied index excludes popular values only as starting points.
    while best_i > alo && best_j > blo
        && unsafe { builtin_equal(a, best_i - 1, b, best_j - 1) }
    {
        best_i -= 1;
        best_j -= 1;
        best_size += 1;
    }
    while best_i + best_size < ahi && best_j + best_size < bhi
        && unsafe { builtin_equal(a, best_i + best_size, b, best_j + best_size) }
    {
        best_size += 1;
    }
    Some((best_i, best_j, best_size))
}

unsafe extern "C" fn find_longest_match_index(
    _module: *mut PyObject, args: *mut *mut PyObject, nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 7 {
        set_type_error(c"find_longest_match_index() takes exactly seven arguments");
        return ptr::null_mut();
    }
    let a = unsafe { *args };
    let b = unsafe { *args.add(1) };
    let index = unsafe { *args.add(2) };
    let Some(a_length) = (unsafe { read_builtin_tuple(a) }) else { return ptr::null_mut(); };
    let Some(b_length) = (unsafe { read_builtin_tuple(b) }) else { return ptr::null_mut(); };
    if unsafe { (*index).ob_type } != ptr::addr_of!(PyDict_Type).cast_mut().cast() {
        set_type_error(c"matching positions must be an exact dictionary");
        return ptr::null_mut();
    }
    let Some(alo) = (unsafe { read_bound(*args.add(3)) }) else { return ptr::null_mut(); };
    let Some(ahi) = (unsafe { read_bound(*args.add(4)) }) else { return ptr::null_mut(); };
    let Some(blo) = (unsafe { read_bound(*args.add(5)) }) else { return ptr::null_mut(); };
    let Some(bhi) = (unsafe { read_bound(*args.add(6)) }) else { return ptr::null_mut(); };
    if alo > ahi || ahi > a_length || blo > bhi || bhi > b_length {
        set_value_error(c"sequence bounds are outside the input sequences");
        return ptr::null_mut();
    }
    let Some(result) = (unsafe { indexed_match(a, b, index, alo, ahi, blo, bhi) }) else {
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

pub static _DIFFLIB_RS_MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"find_longest_match".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: find_longest_match,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Find a longest matching block in integer token sequences.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"find_longest_match_index".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: find_longest_match_index },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Find a longest block of builtin values through ascending position lists.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"snapshot_matches".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: snapshot_matches },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compare an exact builtin list and tuple without callbacks; -1 declines.".as_ptr() as *mut c_char,
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
