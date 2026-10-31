use core::ffi::CStr;

use alloc::boxed::Box;

use crate::ffi::{PyCapsule_GetPointer, PyCapsule_New, PyObject};
use crate::outcome::{Outcome, Stop};
use crate::reference::{Borrowed, Owned};

/// State that a capsule of the given name owns.
pub trait CapsuleState: Sized {
    const NAME: &'static CStr;
}

unsafe extern "C" fn destroy<T: CapsuleState>(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, T::NAME.as_ptr()) };
    if !pointer.is_null() {
        drop(unsafe { Box::from_raw(pointer.cast::<T>()) });
    }
}

/// A capsule object that owns `state` and drops it with the capsule.
pub fn new_capsule<T: CapsuleState>(state: T) -> Outcome<Owned> {
    let pointer = Box::into_raw(Box::new(state));
    let capsule = unsafe { PyCapsule_New(pointer.cast(), T::NAME.as_ptr(), Some(destroy::<T>)) };
    match unsafe { Owned::from_new_reference(capsule) } {
        Ok(capsule) => Ok(capsule),
        Err(stop) => {
            drop(unsafe { Box::from_raw(pointer) });
            Err(stop)
        }
    }
}

/// The state of a capsule created by [`new_capsule`] for the same `T`.
///
/// A capsule of another name raises the interpreter's own error.
///
/// # Safety
/// No other reference to this capsule's state exists while the result lives,
/// which holds when the caller does not re-enter Python meanwhile.
pub unsafe fn capsule_state<'a, T: CapsuleState>(object: Borrowed<'a>) -> Outcome<&'a mut T> {
    let pointer = unsafe { PyCapsule_GetPointer(object.as_ptr(), T::NAME.as_ptr()) };
    if pointer.is_null() {
        return Err(Stop::Raised);
    }
    Ok(unsafe { &mut *pointer.cast::<T>() })
}
