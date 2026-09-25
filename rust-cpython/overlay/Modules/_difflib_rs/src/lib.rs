use std::cell::UnsafeCell;
use std::collections::{HashMap, HashSet};
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyList_GetItem;
use cpython_sys::PyList_Size;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyLong_FromLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;

fn set_type_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

fn set_value_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
}

unsafe fn read_integer_list(arg: *mut PyObject) -> Option<Vec<i64>> {
    let length = unsafe { PyList_Size(arg) };
    if length < 0 {
        return None;
    }
    let mut values = Vec::with_capacity(length as usize);
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

fn longest_match(
    a: &[i64],
    b: &[i64],
    popular: &[i64],
    alo: usize,
    ahi: usize,
    blo: usize,
    bhi: usize,
) -> (usize, usize, usize) {
    let popular = popular.iter().copied().collect::<HashSet<_>>();
    let mut b2j = HashMap::<i64, Vec<usize>>::new();
    for (index, &element) in b.iter().enumerate() {
        if !popular.contains(&element) {
            b2j.entry(element).or_default().push(index);
        }
    }

    let mut best_i = alo;
    let mut best_j = blo;
    let mut best_size = 0;
    let mut previous = HashMap::<usize, usize>::new();
    let mut current = HashMap::<usize, usize>::new();

    for i in alo..ahi {
        current.clear();
        if let Some(indices) = b2j.get(&a[i]) {
            for &j in indices {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let size = if j > blo {
                    previous.get(&(j - 1)).copied().unwrap_or(0) + 1
                } else {
                    1
                };
                current.insert(j, size);
                if size > best_size {
                    best_i = i + 1 - size;
                    best_j = j + 1 - size;
                    best_size = size;
                }
            }
        }
        std::mem::swap(&mut previous, &mut current);
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

    (best_i, best_j, best_size)
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
    let Some(popular) = (unsafe { read_integer_list(*args.add(2)) }) else {
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

    let result = longest_match(&a, &b, &popular, alo, ahi, blo, bhi);
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
