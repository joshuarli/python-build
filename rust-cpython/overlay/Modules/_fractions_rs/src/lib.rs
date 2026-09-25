use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void, CString};

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_NoMemory, PyErr_SetString, PyExc_TypeError, PyExc_ValueError,
    PyExc_ZeroDivisionError, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject, Py_ssize_t,
};
use num_bigint::BigInt;
use num_integer::Integer;
use num_rational::BigRational;

unsafe extern "C" {
    fn PyLong_AsNativeBytes(
        object: *mut PyObject,
        buffer: *mut c_void,
        size: Py_ssize_t,
        flags: c_int,
    ) -> Py_ssize_t;
    fn PyLong_FromNativeBytes(buffer: *const c_void, size: usize, flags: c_int) -> *mut PyObject;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
}

unsafe fn set_error(exception: *mut PyObject, message: &str) {
    if let Ok(message) = CString::new(message) {
        unsafe { PyErr_SetString(exception, message.as_ptr()) };
    } else {
        unsafe { PyErr_SetString(PyExc_ValueError, c"invalid integer text".as_ptr()) };
    }
}

unsafe fn integer_from_object(object: *mut PyObject) -> Result<BigInt, ()> {
    const LITTLE_ENDIAN: c_int = 1;
    let size = unsafe { PyLong_AsNativeBytes(object, std::ptr::null_mut(), 0, LITTLE_ENDIAN) };
    if size < 0 {
        return Err(());
    }
    let mut bytes = vec![0_u8; size as usize];
    let written = unsafe {
        PyLong_AsNativeBytes(
            object,
            bytes.as_mut_ptr().cast::<c_void>(),
            size,
            LITTLE_ENDIAN,
        )
    };
    if written < 0 {
        return Err(());
    }
    if written > size {
        bytes.resize(written as usize, 0);
        let retried = unsafe {
            PyLong_AsNativeBytes(
                object,
                bytes.as_mut_ptr().cast::<c_void>(),
                written,
                LITTLE_ENDIAN,
            )
        };
        if retried < 0 || retried > written {
            return Err(());
        }
        bytes.truncate(retried as usize);
    } else {
        bytes.truncate(written as usize);
    }
    Ok(BigInt::from_signed_bytes_le(&bytes))
}

unsafe fn result_integer(value: &BigInt) -> *mut PyObject {
    const LITTLE_ENDIAN: c_int = 1;
    let bytes = value.to_signed_bytes_le();
    unsafe { PyLong_FromNativeBytes(bytes.as_ptr().cast::<c_void>(), bytes.len(), LITTLE_ENDIAN) }
}

unsafe fn result_tuple(values: &[BigInt]) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if tuple.is_null() {
        return tuple;
    }
    for (index, value) in values.iter().enumerate() {
        let item = unsafe { result_integer(value) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return std::ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return std::ptr::null_mut();
        }
    }
    tuple
}

unsafe fn check_arity(actual: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if actual == expected {
        true
    } else {
        unsafe { PyErr_SetString(PyExc_TypeError, c"invalid number of arguments".as_ptr()) };
        false
    }
}

unsafe fn ratio_from_args(args: *mut *mut PyObject) -> Result<BigRational, ()> {
    let numerator = unsafe { integer_from_object(*args) }?;
    let denominator = unsafe { integer_from_object(*args.add(1)) }?;
    if denominator == BigInt::from(0) {
        unsafe { PyErr_SetString(PyExc_ZeroDivisionError, c"Fraction denominator is zero".as_ptr()) };
        return Err(());
    }
    Ok(BigRational::new(numerator, denominator))
}

unsafe fn ratio_pair(left: *mut *mut PyObject, right: *mut *mut PyObject) -> Result<(BigRational, BigRational), ()> {
    let first = unsafe { ratio_from_args(left) }?;
    let second = unsafe { ratio_from_args(right) }?;
    Ok((first, second))
}

unsafe extern "C" fn normalize(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 2) } {
        return std::ptr::null_mut();
    }
    let ratio = match unsafe { ratio_from_args(args) } {
        Ok(ratio) => ratio,
        Err(()) => return std::ptr::null_mut(),
    };
    unsafe { result_tuple(&[ratio.numer().clone(), ratio.denom().clone()]) }
}

unsafe extern "C" fn parse_parts(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 8) } {
        return std::ptr::null_mut();
    }
    let sign = match unsafe { integer_from_object(*args) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let mut numerator = match unsafe { integer_from_object(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let denominator = match unsafe { integer_from_object(*args.add(2)) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let decimal = match unsafe { integer_from_object(*args.add(3)) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let decimal_places = match unsafe { integer_from_object(*args.add(4)) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let exponent = match unsafe { integer_from_object(*args.add(5)) } {
        Ok(value) => value,
        Err(()) => return std::ptr::null_mut(),
    };
    let has_denominator = match unsafe { integer_from_object(*args.add(6)) } {
        Ok(value) => value != BigInt::from(0),
        Err(()) => return std::ptr::null_mut(),
    };
    let has_decimal = match unsafe { integer_from_object(*args.add(7)) } {
        Ok(value) => value != BigInt::from(0),
        Err(()) => return std::ptr::null_mut(),
    };

    let mut denominator = if has_denominator { denominator } else { BigInt::from(1) };

    if has_decimal {
        let places = match decimal_places.to_str_radix(10).parse::<u32>() {
            Ok(value) => value,
            Err(_) => {
                unsafe { PyErr_NoMemory() };
                return std::ptr::null_mut();
            }
        };
        let scale = BigInt::from(10).pow(places);
        numerator = numerator * &scale + decimal;
        denominator *= scale;
    }

    let exponent = match exponent.to_str_radix(10).parse::<i32>() {
        Ok(value) => value,
        Err(_) => {
            unsafe { PyErr_NoMemory() };
            return std::ptr::null_mut();
        }
    };
    if exponent >= 0 {
        numerator *= BigInt::from(10).pow(exponent as u32);
    } else {
        denominator *= BigInt::from(10).pow(exponent.unsigned_abs());
    }
    if sign < BigInt::from(0) {
        numerator = -numerator;
    }
    if denominator == BigInt::from(0) {
        let message = format!("Fraction({}, 0)", numerator);
        unsafe { set_error(PyExc_ZeroDivisionError, &message) };
        return std::ptr::null_mut();
    }
    let ratio = BigRational::new(numerator, denominator);
    unsafe { result_tuple(&[ratio.numer().clone(), ratio.denom().clone()]) }
}

unsafe fn binary_result(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    operation: &str,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 4) } {
        return std::ptr::null_mut();
    }
    let right_args = unsafe { args.add(2) };
    let (left, right) = match unsafe { ratio_pair(args, right_args) } {
        Ok(pair) => pair,
        Err(()) => return std::ptr::null_mut(),
    };
    match operation {
        "add" => {
            let result = left + right;
            unsafe { result_tuple(&[result.numer().clone(), result.denom().clone()]) }
        }
        "sub" => {
            let result = left - right;
            unsafe { result_tuple(&[result.numer().clone(), result.denom().clone()]) }
        }
        "mul" => {
            let result = left * right;
            unsafe { result_tuple(&[result.numer().clone(), result.denom().clone()]) }
        }
        "truediv" => {
            if right.numer() == &BigInt::from(0) {
                unsafe { PyErr_SetString(PyExc_ZeroDivisionError, c"Fraction division by zero".as_ptr()) };
                return std::ptr::null_mut();
            }
            let result = left / right;
            unsafe { result_tuple(&[result.numer().clone(), result.denom().clone()]) }
        }
        "floordiv" | "mod" | "divmod" => {
            if right.numer() == &BigInt::from(0) {
                unsafe { PyErr_SetString(PyExc_ZeroDivisionError, c"Fraction division by zero".as_ptr()) };
                return std::ptr::null_mut();
            }
            let quotient = left.clone() / right.clone();
            let integer = quotient.numer().div_floor(quotient.denom());
            if operation == "floordiv" {
                unsafe { result_integer(&integer) }
            } else {
                let remainder = left - right * BigRational::from_integer(integer.clone());
                if operation == "mod" {
                    unsafe { result_tuple(&[remainder.numer().clone(), remainder.denom().clone()]) }
                } else {
                    unsafe { result_tuple(&[integer, remainder.numer().clone(), remainder.denom().clone()]) }
                }
            }
        }
        _ => unreachable!(),
    }
}

macro_rules! binary_method {
    ($name:ident, $operation:literal) => {
        unsafe extern "C" fn $name(
            _module: *mut PyObject,
            args: *mut *mut PyObject,
            nargs: Py_ssize_t,
        ) -> *mut PyObject {
            unsafe { binary_result(args, nargs, $operation) }
        }
    };
}

binary_method!(add, "add");
binary_method!(sub, "sub");
binary_method!(mul, "mul");
binary_method!(truediv, "truediv");
binary_method!(floordiv, "floordiv");
binary_method!(modulo, "mod");
binary_method!(divmod, "divmod");

unsafe extern "C" fn module_clear(_module: *mut PyObject) -> c_int {
    0
}

unsafe extern "C" fn module_free(_module: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static FRACTIONS_METHODS: [PyMethodDef; 10] = [
    PyMethodDef {
        ml_name: c"normalize".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: normalize },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return a normalized numerator and denominator.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_parts".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: parse_parts },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Convert parsed decimal components to a normalized rational.".as_ptr() as *mut c_char,
    },
    PyMethodDef { ml_name: c"add".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: add }, ml_flags: METH_FASTCALL, ml_doc: c"Add two rational values.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"sub".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: sub }, ml_flags: METH_FASTCALL, ml_doc: c"Subtract two rational values.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"mul".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: mul }, ml_flags: METH_FASTCALL, ml_doc: c"Multiply two rational values.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"truediv".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: truediv }, ml_flags: METH_FASTCALL, ml_doc: c"Divide two rational values.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"floordiv".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: floordiv }, ml_flags: METH_FASTCALL, ml_doc: c"Floor-divide two rational values.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"mod".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: modulo }, ml_flags: METH_FASTCALL, ml_doc: c"Return the rational remainder.".as_ptr() as *mut c_char },
    PyMethodDef { ml_name: c"divmod".as_ptr() as *mut c_char, ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: divmod }, ml_flags: METH_FASTCALL, ml_doc: c"Return the integer quotient and rational remainder.".as_ptr() as *mut c_char },
    PyMethodDef::zeroed(),
];

pub static FRACTIONS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_fractions_rs".as_ptr() as *mut _,
        m_doc: c"Exact rational arithmetic support for fractions.Fraction.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &FRACTIONS_METHODS as *const PyMethodDef as *mut _,
        m_slots: std::ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__fractions_rs() -> *mut PyObject {
    FRACTIONS_MODULE.init_multi_phase()
}
