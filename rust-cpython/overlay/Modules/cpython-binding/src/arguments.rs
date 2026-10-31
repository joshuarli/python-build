use core::ffi::{CStr, c_int, c_ulong};

use crate::ffi::{
    PyErr_Occurred, PyLong_AsLong, PyLong_AsLongLong, PyLong_AsSsize_t, Py_DecRef, Py_ssize_t,
};
use crate::ffi::{PyLong_AsUnsignedLongMask, PyNumber_Index};
use crate::outcome::{Exception, Outcome, Stop, raise};
use crate::reference::Borrowed;

fn raised_after(failure_value: bool) -> Outcome<()> {
    if failure_value && !unsafe { PyErr_Occurred() }.is_null() {
        return Err(Stop::Raised);
    }
    Ok(())
}

/// An `int` argument that must fit a C `int`.
pub fn c_int_argument(object: Borrowed<'_>) -> Outcome<c_int> {
    let value = unsafe { PyLong_AsLong(object.as_ptr()) };
    raised_after(value == -1)?;
    c_int::try_from(value).map_err(|_| {
        raise(
            Exception::OverflowError,
            c"Python int too large to convert to C int",
        )
    })
}

/// An `int` argument that must fit a `long long`.
pub fn long_long_argument(object: Borrowed<'_>) -> Outcome<i64> {
    let value = unsafe { PyLong_AsLongLong(object.as_ptr()) };
    raised_after(value == -1)?;
    Ok(value)
}

/// An `int` argument that must fit a `Py_ssize_t`.
pub fn ssize_argument(object: Borrowed<'_>) -> Outcome<Py_ssize_t> {
    let value = unsafe { PyLong_AsSsize_t(object.as_ptr()) };
    raised_after(value == -1)?;
    Ok(value)
}

/// An argument converted through `__index__`, like a C `Py_ssize_t` parameter.
pub fn index_argument(object: Borrowed<'_>) -> Outcome<Py_ssize_t> {
    let index = unsafe { PyNumber_Index(object.as_ptr()) };
    if index.is_null() {
        return Err(Stop::Raised);
    }
    let value = unsafe { PyLong_AsSsize_t(index) };
    unsafe { Py_DecRef(index) };
    raised_after(value == -1)?;
    Ok(value)
}

/// An `int` argument reduced modulo 2**(bits of `unsigned long`).
pub fn unsigned_long_mask_argument(object: Borrowed<'_>) -> Outcome<c_ulong> {
    let value = unsafe { PyLong_AsUnsignedLongMask(object.as_ptr()) };
    raised_after(value == c_ulong::MAX)?;
    Ok(value)
}

/// The positional arguments of a call that takes exactly `N`.
pub fn exactly<'a, const N: usize>(
    arguments: &'a [Borrowed<'a>],
    message: &CStr,
) -> Outcome<&'a [Borrowed<'a>; N]> {
    <&[Borrowed<'a>; N]>::try_from(arguments).map_err(|_| raise(Exception::TypeError, message))
}
