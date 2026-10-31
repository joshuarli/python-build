use core::ffi::CStr;
use core::ptr;

use crate::ffi::{
    PyErr_SetString, PyExc_IndexError, PyExc_OverflowError, PyExc_TypeError, PyExc_ValueError,
    PyObject,
};
use crate::reference::Owned;

/// Why an operation produced no value.
///
/// `Unsupported` leaves no Python state behind: the caller returns `None` so
/// the Python implementation handles the call. `Raised` means a Python
/// exception is already set and the caller returns a null pointer.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stop {
    Unsupported,
    Raised,
}

pub type Outcome<T> = Result<T, Stop>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Exception {
    IndexError,
    OverflowError,
    TypeError,
    ValueError,
}

pub fn raise(exception: Exception, message: &'static CStr) -> Stop {
    unsafe {
        let class = match exception {
            Exception::IndexError => PyExc_IndexError,
            Exception::OverflowError => PyExc_OverflowError,
            Exception::TypeError => PyExc_TypeError,
            Exception::ValueError => PyExc_ValueError,
        };
        PyErr_SetString(class, message.as_ptr());
    }
    Stop::Raised
}

/// The value a C-API entry point returns for an outcome.
pub fn into_return(outcome: Outcome<Owned>) -> *mut PyObject {
    match outcome {
        Ok(value) => value.into_raw(),
        Err(Stop::Unsupported) => Owned::none().into_raw(),
        Err(Stop::Raised) => ptr::null_mut(),
    }
}
