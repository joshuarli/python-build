use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyErr_Clear, PyErr_NoMemory, PyErr_Occurred,
    PyList_GetItem, PyList_Size, PyLong_AsLongLong, PyLong_FromLongLong, PyLong_FromSsize_t,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyObject_Type, PyTuple_GetItem, PyTuple_New, PyTuple_SetItem,
    PyTuple_Size, PyTypeObject, Py_DecRef, PyList_Type, PyLong_Type, PyTuple_Type,
    Py_ssize_t,
};

unsafe fn is_exact_type(object: *mut PyObject, expected: *mut PyTypeObject) -> Result<bool, ()> {
    let actual = unsafe { PyObject_Type(object) };
    if actual.is_null() {
        return Err(());
    }
    let matches = actual == expected.cast::<PyObject>();
    unsafe { Py_DecRef(actual) };
    Ok(matches)
}

unsafe fn sequence_info(object: *mut PyObject) -> Result<Option<(bool, usize)>, ()> {
    let list_type = unsafe { ptr::addr_of_mut!(PyList_Type) };
    if unsafe { is_exact_type(object, list_type) }? {
        let length = unsafe { PyList_Size(object) };
        if length < 0 {
            return Err(());
        }
        return Ok(Some((true, length as usize)));
    }

    let tuple_type = unsafe { ptr::addr_of_mut!(PyTuple_Type) };
    if unsafe { is_exact_type(object, tuple_type) }? {
        let length = unsafe { PyTuple_Size(object) };
        if length < 0 {
            return Err(());
        }
        return Ok(Some((false, length as usize)));
    }

    Ok(None)
}

unsafe fn sequence_item(object: *mut PyObject, is_list: bool, index: usize) -> Result<*mut PyObject, ()> {
    let item = if is_list {
        unsafe { PyList_GetItem(object, index as Py_ssize_t) }
    } else {
        unsafe { PyTuple_GetItem(object, index as Py_ssize_t) }
    };
    if item.is_null() {
        Err(())
    } else {
        Ok(item)
    }
}

unsafe fn exact_i64(object: *mut PyObject) -> Result<Option<i64>, ()> {
    let integer_type = unsafe { ptr::addr_of_mut!(PyLong_Type) };
    if !unsafe { is_exact_type(object, integer_type) }? {
        return Ok(None);
    }
    let value = unsafe { PyLong_AsLongLong(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return Ok(None);
    }
    Ok(Some(value))
}

fn no_fast_path() -> *mut PyObject {
    unsafe { PyBool_FromLong(0) }
}

unsafe fn return_integer_tuple(values: &[i64]) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if tuple.is_null() {
        return tuple;
    }
    for (index, value) in values.iter().enumerate() {
        let item = unsafe { PyLong_FromLongLong(*value) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return ptr::null_mut();
        }
    }
    tuple
}

unsafe fn integer_moments(data: *mut PyObject) -> Result<Option<(i64, i64, i64)>, ()> {
    let Some((is_list, length)) = (unsafe { sequence_info(data) })? else {
        return Ok(None);
    };
    if length == 0 {
        return Ok(None);
    }

    let mut total = 0_i64;
    let mut squares = 0_i64;
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(None);
        };
        let Some(square) = value.checked_mul(value) else {
            return Ok(None);
        };
        let Some(next_total) = total.checked_add(value) else {
            return Ok(None);
        };
        let Some(next_squares) = squares.checked_add(square) else {
            return Ok(None);
        };
        total = next_total;
        squares = next_squares;
    }

    Ok(Some((total, squares, length as i64)))
}

unsafe extern "C" fn integer_moments_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return no_fast_path();
    }
    match unsafe { integer_moments(*args) } {
        Ok(Some((total, squares, count))) => unsafe {
            return_integer_tuple(&[total, squares, count])
        },
        Ok(None) => no_fast_path(),
        Err(()) => ptr::null_mut(),
    }
}

unsafe fn median_indices(data: *mut PyObject) -> Result<Option<(usize, usize)>, ()> {
    let Some((is_list, length)) = (unsafe { sequence_info(data) })? else {
        return Ok(None);
    };
    if length == 0 {
        return Ok(None);
    }

    let mut ordered = Vec::new();
    if ordered.try_reserve_exact(length).is_err() {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(None);
        };
        ordered.push((value, index));
    }

    ordered.sort_by_key(|(value, _)| *value);
    Ok(Some((
        ordered[(length - 1) / 2].1,
        ordered[length / 2].1,
    )))
}

unsafe extern "C" fn median_indices_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return no_fast_path();
    }
    let (low, high) = match unsafe { median_indices(*args) } {
        Ok(Some(indices)) => indices,
        Ok(None) => return no_fast_path(),
        Err(()) => return ptr::null_mut(),
    };

    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        return tuple;
    }
    for (slot, index) in [low, high].into_iter().enumerate() {
        let item = unsafe { PyLong_FromSsize_t(index as Py_ssize_t) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, slot as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return ptr::null_mut();
        }
    }
    tuple
}

pub extern "C" fn _statistics_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _statistics_rs_free(_object: *mut c_void) {}

struct ModuleDef(UnsafeCell<PyModuleDef>);

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"integer_moments".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: integer_moments_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return sum, sum of squares, and count for exact int sequences."
            .as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"median_indices".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: median_indices_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return stable median indices for exact int sequences."
            .as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_statistics_rs".as_ptr() as *mut _,
    m_doc: c"Rust summary operations for exact integer sequences.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: Some(_statistics_rs_clear),
    m_free: Some(_statistics_rs_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__statistics_rs() -> *mut PyObject {
    MODULE.init()
}
