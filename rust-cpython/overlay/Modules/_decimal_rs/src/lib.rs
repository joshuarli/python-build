use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, PyErr_SetString, PyExc_TypeError, PyExc_ValueError, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_Slot, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize,
    Py_ssize_t,
};
use num_bigint::BigUint;

unsafe fn parse_integer(object: *mut PyObject) -> Result<BigUint, ()> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    match BigUint::parse_bytes(bytes, 10) {
        Some(value) => Ok(value),
        None => {
            unsafe { PyErr_SetString(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
            Err(())
        }
    }
}

unsafe extern "C" fn add_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }
    let left = match unsafe { parse_integer(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let right = match unsafe { parse_integer(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let result = (left + right).to_str_radix(10);
    unsafe {
        PyUnicode_FromStringAndSize(result.as_ptr().cast::<c_char>(), result.len() as Py_ssize_t)
    }
}

unsafe extern "C" fn multiply_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }
    let left = match unsafe { parse_integer(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let right = match unsafe { parse_integer(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let result = (left * right).to_str_radix(10);
    unsafe {
        PyUnicode_FromStringAndSize(result.as_ptr().cast::<c_char>(), result.len() as Py_ssize_t)
    }
}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"multiply_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: multiply_exact_integers },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Multiply two nonnegative decimal integer coefficients exactly.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"add_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: add_exact_integers },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Add two nonnegative decimal integer coefficients exactly.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

struct ModuleSlots([PyModuleDef_Slot; 2]);

unsafe impl Sync for ModuleSlots {}

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: 2usize as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_decimal_rs".as_ptr() as *mut _,
    m_doc: c"Exact integer coefficient arithmetic for decimal.Decimal.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: SLOTS.0.as_ptr() as *mut _,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__decimal_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
