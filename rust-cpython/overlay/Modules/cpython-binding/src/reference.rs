use core::marker::PhantomData;
use core::ptr::{self, NonNull};

use crate::ffi::{_Py_NoneStruct, Py_DecRef, Py_NewRef, Py_ssize_t, PyObject};
use crate::outcome::{Outcome, Stop};

/// A strong reference, released on drop.
pub struct Owned(NonNull<PyObject>);

impl Owned {
    /// Take over a new reference returned by the C API.
    ///
    /// # Safety
    /// `pointer` is null or a strong reference this value now owns, and the
    /// thread holds an attached thread state.
    #[inline]
    pub unsafe fn from_new_reference(pointer: *mut PyObject) -> Outcome<Self> {
        NonNull::new(pointer).map(Self).ok_or(Stop::Raised)
    }

    #[inline]
    pub fn none() -> Self {
        let none = unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
        Self(unsafe { NonNull::new_unchecked(none) })
    }

    #[inline]
    pub fn as_ptr(&self) -> *mut PyObject {
        self.0.as_ptr()
    }

    #[inline]
    pub fn borrow(&self) -> Borrowed<'_> {
        Borrowed(self.0, PhantomData)
    }

    /// Give the reference to the caller of the C API.
    #[inline]
    pub fn into_raw(self) -> *mut PyObject {
        let pointer = self.0.as_ptr();
        core::mem::forget(self);
        pointer
    }
}

impl Drop for Owned {
    #[inline]
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0.as_ptr()) };
    }
}

/// A reference some other owner keeps alive for `'a`.
#[derive(Clone, Copy)]
#[repr(transparent)]
pub struct Borrowed<'a>(NonNull<PyObject>, PhantomData<&'a PyObject>);

impl<'a> Borrowed<'a> {
    /// # Safety
    /// `pointer` is non-null and stays alive for `'a`.
    #[inline]
    pub unsafe fn from_raw(pointer: *mut PyObject) -> Self {
        Self(unsafe { NonNull::new_unchecked(pointer) }, PhantomData)
    }

    #[inline]
    pub fn as_ptr(self) -> *mut PyObject {
        self.0.as_ptr()
    }

    #[inline]
    pub fn to_owned(self) -> Owned {
        let pointer = unsafe { Py_NewRef(self.0.as_ptr()) };
        Owned(unsafe { NonNull::new_unchecked(pointer) })
    }
}

/// The positional arguments of a `METH_FASTCALL` call.
///
/// # Safety
/// `args` points to `count` non-null objects that stay alive for `'a`.
#[inline]
pub unsafe fn fastcall_arguments<'a>(
    args: *mut *mut PyObject,
    count: Py_ssize_t,
) -> &'a [Borrowed<'a>] {
    if count <= 0 {
        return &[];
    }
    unsafe { core::slice::from_raw_parts(args.cast::<Borrowed<'a>>(), count as usize) }
}
