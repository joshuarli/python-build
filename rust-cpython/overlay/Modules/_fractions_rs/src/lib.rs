//! Exact rational arithmetic without a separate standard runtime or heap.
#![cfg_attr(not(test), no_std)]

extern crate alloc;

use alloc::{ffi::CString, format, vec};
use core::ffi::{c_int, c_void};

use cpython_binding::ffi::{
    Py_DecRef, Py_ssize_t, PyErr_NoMemory, PyErr_SetString, PyExc_TypeError, PyExc_ValueError,
    PyExc_ZeroDivisionError, PyLong_AsNativeBytes, PyLong_FromNativeBytes, PyMethodDef,
    PyObject, PyTuple_New, PyTuple_SetItem,
};
use cpython_binding::{Module, fastcall, method_table_end};

#[cfg(not(test))]
#[global_allocator]
static ALLOCATOR: cpython_binding::pymem::AttachedThreadAllocator =
    cpython_binding::pymem::AttachedThreadAllocator;

use num_bigint::{BigInt, Sign};
use num_integer::Integer;
use num_rational::BigRational;

unsafe fn set_error(exception: *mut PyObject, message: &str) {
    if let Ok(message) = CString::new(message) {
        unsafe { PyErr_SetString(exception, message.as_ptr()) };
    } else {
        unsafe { PyErr_SetString(PyExc_ValueError, c"invalid integer text".as_ptr()) };
    }
}

unsafe fn integer_from_object(object: *mut PyObject) -> Result<BigInt, ()> {
    const LITTLE_ENDIAN: c_int = 1;
    let size = unsafe { PyLong_AsNativeBytes(object, core::ptr::null_mut(), 0, LITTLE_ENDIAN) };
    if size < 0 {
        return Err(());
    }
    // Small integers need no temporary heap byte buffer. The arbitrary
    // precision path below handles every value that exceeds this capacity.
    let mut stack = [0_u8; 64];
    if size as usize <= stack.len() {
        let written = unsafe {
            PyLong_AsNativeBytes(object, stack.as_mut_ptr().cast(), stack.len() as Py_ssize_t, LITTLE_ENDIAN)
        };
        if written < 0 {
            return Err(());
        }
        if written as usize <= stack.len() {
            return Ok(BigInt::from_signed_bytes_le(&stack[..written as usize]));
        }
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
    let size = value.bits() / 8 + 1;
    let mut stack = [0_u8; 64];
    if size <= stack.len() as u64 {
        let size = size as usize;
        for (index, digit) in value.iter_u64_digits().enumerate() {
            let start = index * 8;
            let count = (size - start).min(8);
            stack[start..start + count].copy_from_slice(&digit.to_le_bytes()[..count]);
        }
        if value.sign() == Sign::Minus {
            let mut carry = true;
            for byte in &mut stack[..size] {
                let (next, overflow) = (!*byte).overflowing_add(u8::from(carry));
                *byte = next;
                carry = overflow;
            }
        }
        return unsafe { PyLong_FromNativeBytes(stack.as_ptr().cast(), size, LITTLE_ENDIAN) };
    }
    let bytes = value.to_signed_bytes_le();
    unsafe { PyLong_FromNativeBytes(bytes.as_ptr().cast::<c_void>(), bytes.len(), LITTLE_ENDIAN) }
}

unsafe fn result_tuple(values: &[&BigInt]) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if tuple.is_null() {
        return tuple;
    }
    for (index, value) in values.iter().enumerate() {
        let item = unsafe { result_integer(value) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return core::ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return core::ptr::null_mut();
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
        return core::ptr::null_mut();
    }
    let ratio = match unsafe { ratio_from_args(args) } {
        Ok(ratio) => ratio,
        Err(()) => return core::ptr::null_mut(),
    };
    unsafe { result_tuple(&[ratio.numer(), ratio.denom()]) }
}

unsafe extern "C" fn parse_parts(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 8) } {
        return core::ptr::null_mut();
    }
    let sign = match unsafe { integer_from_object(*args) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let mut numerator = match unsafe { integer_from_object(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let denominator = match unsafe { integer_from_object(*args.add(2)) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let decimal = match unsafe { integer_from_object(*args.add(3)) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let decimal_places = match unsafe { integer_from_object(*args.add(4)) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let exponent = match unsafe { integer_from_object(*args.add(5)) } {
        Ok(value) => value,
        Err(()) => return core::ptr::null_mut(),
    };
    let has_denominator = match unsafe { integer_from_object(*args.add(6)) } {
        Ok(value) => value != BigInt::from(0),
        Err(()) => return core::ptr::null_mut(),
    };
    let has_decimal = match unsafe { integer_from_object(*args.add(7)) } {
        Ok(value) => value != BigInt::from(0),
        Err(()) => return core::ptr::null_mut(),
    };

    let mut denominator = if has_denominator { denominator } else { BigInt::from(1) };

    if has_decimal {
        let places = match decimal_places.to_str_radix(10).parse::<u32>() {
            Ok(value) => value,
            Err(_) => {
                unsafe { PyErr_NoMemory() };
                return core::ptr::null_mut();
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
            return core::ptr::null_mut();
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
        return core::ptr::null_mut();
    }
    let ratio = BigRational::new(numerator, denominator);
    unsafe { result_tuple(&[ratio.numer(), ratio.denom()]) }
}

unsafe fn binary_result(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    operation: &str,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 4) } {
        return core::ptr::null_mut();
    }
    let right_args = unsafe { args.add(2) };
    let (left, right) = match unsafe { ratio_pair(args, right_args) } {
        Ok(pair) => pair,
        Err(()) => return core::ptr::null_mut(),
    };
    match operation {
        "add" => {
            let result = left + right;
            unsafe { result_tuple(&[result.numer(), result.denom()]) }
        }
        "sub" => {
            let result = left - right;
            unsafe { result_tuple(&[result.numer(), result.denom()]) }
        }
        "mul" => {
            let result = left * right;
            unsafe { result_tuple(&[result.numer(), result.denom()]) }
        }
        "truediv" => {
            if right.numer() == &BigInt::from(0) {
                unsafe { PyErr_SetString(PyExc_ZeroDivisionError, c"Fraction division by zero".as_ptr()) };
                return core::ptr::null_mut();
            }
            let result = left / right;
            unsafe { result_tuple(&[result.numer(), result.denom()]) }
        }
        "floordiv" | "mod" | "divmod" => {
            if right.numer() == &BigInt::from(0) {
                unsafe { PyErr_SetString(PyExc_ZeroDivisionError, c"Fraction division by zero".as_ptr()) };
                return core::ptr::null_mut();
            }
            let quotient = left.clone() / right.clone();
            let integer = quotient.numer().div_floor(quotient.denom());
            if operation == "floordiv" {
                unsafe { result_integer(&integer) }
            } else {
                let remainder = left - right * BigRational::from_integer(integer.clone());
                if operation == "mod" {
                    unsafe { result_tuple(&[remainder.numer(), remainder.denom()]) }
                } else {
                    unsafe { result_tuple(&[&integer, remainder.numer(), remainder.denom()]) }
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

static METHODS: [PyMethodDef; 10] = [
    fastcall(c"normalize", normalize, c"Return a normalized numerator and denominator."),
    fastcall(
        c"parse_parts",
        parse_parts,
        c"Convert parsed decimal components to a normalized rational.",
    ),
    fastcall(c"add", add, c"Add two rational values."),
    fastcall(c"sub", sub, c"Subtract two rational values."),
    fastcall(c"mul", mul, c"Multiply two rational values."),
    fastcall(c"truediv", truediv, c"Divide two rational values."),
    fastcall(c"floordiv", floordiv, c"Floor-divide two rational values."),
    fastcall(c"mod", modulo, c"Return the rational remainder."),
    fastcall(c"divmod", divmod, c"Return the integer quotient and rational remainder."),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_fractions_rs",
    c"Exact rational arithmetic support for fractions.Fraction.",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__fractions_rs() -> *mut PyObject {
    MODULE.init()
}
