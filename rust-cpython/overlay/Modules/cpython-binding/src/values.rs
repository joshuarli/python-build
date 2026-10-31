use core::ffi::c_ulong;

use crate::ffi::{PyBool_FromLong, PyLong_FromSsize_t, PyTuple_New, PyTuple_SetItem, Py_ssize_t};
use crate::ffi_extra::PyLong_FromUnsignedLong;
use crate::outcome::{Outcome, Stop};
use crate::reference::Owned;

pub fn boolean(value: bool) -> Owned {
    let object = unsafe { PyBool_FromLong(value.into()) };
    unsafe { Owned::from_new_reference(object) }.expect("bool objects are immortal")
}

pub fn unsigned_long(value: c_ulong) -> Outcome<Owned> {
    unsafe { Owned::from_new_reference(PyLong_FromUnsignedLong(value)) }
}

pub fn ssize(value: Py_ssize_t) -> Outcome<Owned> {
    unsafe { Owned::from_new_reference(PyLong_FromSsize_t(value)) }
}

/// A tuple that owns `items`.
pub fn tuple<const N: usize>(items: [Owned; N]) -> Outcome<Owned> {
    let tuple = unsafe { Owned::from_new_reference(PyTuple_New(N as Py_ssize_t)) }?;
    for (index, item) in items.into_iter().enumerate() {
        if unsafe { PyTuple_SetItem(tuple.as_ptr(), index as Py_ssize_t, item.into_raw()) } != 0 {
            return Err(Stop::Raised);
        }
    }
    Ok(tuple)
}
