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

enum Integer {
    Small(u128),
    Large(BigUint),
}

impl Integer {
    fn into_big(self) -> BigUint {
        match self {
            Self::Small(value) => BigUint::from(value),
            Self::Large(value) => value,
        }
    }
}

// Decimal coefficients usually fit a machine integer. Keep their parsing,
// arithmetic, and formatting on the stack; overflow retains exact precision.
fn parse_small(bytes: &[u8]) -> Option<u128> {
    if bytes.is_empty() {
        return None;
    }
    let mut value = 0u128;
    for &byte in bytes {
        if !byte.is_ascii_digit() {
            return None;
        }
        value = value.checked_mul(10)?.checked_add(u128::from(byte - b'0'))?;
    }
    Some(value)
}

unsafe fn small_result(mut value: u128) -> *mut PyObject {
    let mut digits = [0u8; 39];
    let mut start = digits.len();
    loop {
        start -= 1;
        digits[start] = b'0' + (value % 10) as u8;
        value /= 10;
        if value == 0 {
            break;
        }
    }
    unsafe {
        PyUnicode_FromStringAndSize(
            digits[start..].as_ptr().cast::<c_char>(),
            (digits.len() - start) as Py_ssize_t,
        )
    }
}

unsafe fn parse_integer(object: *mut PyObject) -> Result<Integer, ()> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    if let Some(value) = parse_small(bytes) {
        return Ok(Integer::Small(value));
    }
    match BigUint::parse_bytes(bytes, 10) {
        Some(value) => Ok(Integer::Large(value)),
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
    let result = match (left, right) {
        (Integer::Small(left), Integer::Small(right)) => {
            if let Some(result) = left.checked_add(right) {
                return unsafe { small_result(result) };
            }
            (BigUint::from(left) + BigUint::from(right)).to_str_radix(10)
        }
        (left, right) => (left.into_big() + right.into_big()).to_str_radix(10),
    };
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
    let result = match (left, right) {
        (Integer::Small(left), Integer::Small(right)) => {
            if let Some(result) = left.checked_mul(right) {
                return unsafe { small_result(result) };
            }
            (BigUint::from(left) * BigUint::from(right)).to_str_radix(10)
        }
        (left, right) => (left.into_big() * right.into_big()).to_str_radix(10),
    };
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
