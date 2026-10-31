#![no_std]

use core::ffi::c_char;
use core::ptr;
use core::slice;

use cpython_binding::ffi::{
    PyErr_SetString, PyExc_OverflowError, PyExc_TypeError, PyExc_ValueError, PyMethodDef,
    PyObject, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_ssize_t,
};
use cpython_binding::{Module, fastcall, method_table_end};
use cpython_binding::module::PER_INTERPRETER_GIL;

const MAX_INPUT_DIGITS: usize = 128;
const MAX_RESULT_DIGITS: usize = MAX_INPUT_DIGITS * 2;

#[derive(Clone, Copy)]
struct Digits {
    values: [u8; MAX_RESULT_DIGITS],
    len: usize,
}

impl Digits {
    const fn zeroed() -> Self {
        Self {
            values: [0; MAX_RESULT_DIGITS],
            len: 0,
        }
    }
}

unsafe fn set_error(exception: *mut PyObject, message: *const c_char) {
    unsafe {
        // SAFETY: the caller holds the GIL and supplies a live exception object and static C string.
        PyErr_SetString(exception, message);
    }
}

unsafe fn parse_coefficient(object: *mut PyObject) -> Option<Digits> {
    if object.is_null() {
        unsafe { set_error(PyExc_TypeError, c"expected decimal integer strings".as_ptr()) };
        return None;
    }

    let mut size = 0;
    // SAFETY: object is a live argument owned by the active CPython call.
    let text = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if text.is_null() {
        return None;
    }
    if size <= 0 || size as usize > MAX_INPUT_DIGITS {
        unsafe { set_error(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
        return None;
    }

    // SAFETY: CPython returns a readable UTF-8 buffer covering the reported positive byte length.
    let bytes = unsafe { slice::from_raw_parts(text.cast::<u8>(), size as usize) };
    let mut digits = Digits::zeroed();
    digits.len = bytes.len();
    for (index, byte) in bytes.iter().rev().enumerate() {
        if !byte.is_ascii_digit() {
            unsafe { set_error(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
            return None;
        }
        digits.values[index] = *byte - b'0';
    }
    Some(digits)
}

fn add(left: &Digits, right: &Digits) -> Option<Digits> {
    let mut result = Digits::zeroed();
    let width = left.len.max(right.len);
    let mut carry = 0u16;

    for index in 0..width {
        let sum = u16::from(left.values[index]) + u16::from(right.values[index]) + carry;
        result.values[index] = (sum % 10) as u8;
        carry = sum / 10;
    }
    result.len = width;
    if carry != 0 {
        *result.values.get_mut(width)? = carry as u8;
        result.len += 1;
    }
    Some(result)
}

fn multiply(left: &Digits, right: &Digits) -> Option<Digits> {
    let mut result = Digits::zeroed();
    if (left.len == 1 && left.values[0] == 0) || (right.len == 1 && right.values[0] == 0) {
        result.len = 1;
        return Some(result);
    }

    for left_index in 0..left.len {
        let mut carry = 0u16;
        for right_index in 0..right.len {
            let index = left_index + right_index;
            let product = u16::from(result.values[index])
                + u16::from(left.values[left_index]) * u16::from(right.values[right_index])
                + carry;
            result.values[index] = (product % 10) as u8;
            carry = product / 10;
        }

        let mut index = left_index + right.len;
        while carry != 0 {
            let digit = result.values.get_mut(index)?;
            let sum = u16::from(*digit) + carry;
            *digit = (sum % 10) as u8;
            carry = sum / 10;
            index += 1;
        }
    }

    result.len = left.len.checked_add(right.len)?;
    while result.len > 1 && result.values[result.len - 1] == 0 {
        result.len -= 1;
    }
    Some(result)
}

unsafe fn exact_integer_operation(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    operation: fn(&Digits, &Digits) -> Option<Digits>,
) -> *mut PyObject {
    if nargs != 2 || args.is_null() {
        unsafe { set_error(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }

    // SAFETY: CPython's FASTCALL contract provides nargs argument pointers when nargs is two.
    let left_object = unsafe { *args };
    // SAFETY: CPython's FASTCALL contract provides nargs argument pointers when nargs is two.
    let right_object = unsafe { *args.add(1) };
    let Some(left) = (unsafe { parse_coefficient(left_object) }) else {
        return ptr::null_mut();
    };
    let Some(right) = (unsafe { parse_coefficient(right_object) }) else {
        return ptr::null_mut();
    };
    let Some(result) = operation(&left, &right) else {
        unsafe { set_error(PyExc_OverflowError, c"decimal integer result is too large".as_ptr()) };
        return ptr::null_mut();
    };

    let mut text = [0u8; MAX_RESULT_DIGITS];
    for index in 0..result.len {
        text[result.len - index - 1] = b'0' + result.values[index];
    }
    // SAFETY: text contains result.len initialized ASCII bytes for the duration of the call.
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), result.len as Py_ssize_t) }
}

unsafe extern "C" fn add_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integer_operation(args, nargs, add) }
}

unsafe extern "C" fn multiply_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integer_operation(args, nargs, multiply) }
}

static METHODS: [PyMethodDef; 3] = [
    fastcall(
        c"multiply_exact_integers",
        multiply_exact_integers,
        c"Multiply two nonnegative decimal integer coefficients exactly.",
    ),
    fastcall(
        c"add_exact_integers",
        add_exact_integers,
        c"Add two nonnegative decimal integer coefficients exactly.",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_decimal_rs",
    c"Exact integer coefficient arithmetic for decimal.Decimal.",
    &METHODS,
).with_slots(&PER_INTERPRETER_GIL);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__decimal_rs() -> *mut PyObject {
    MODULE.init()
}
