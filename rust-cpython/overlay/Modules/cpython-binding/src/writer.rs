use core::mem::{ManuallyDrop, MaybeUninit};
use core::ptr;
use core::slice;

use crate::ffi::{
    PyBytes_AsString, PyBytes_FromStringAndSize, PyErr_NoMemory, Py_DecRef, Py_ssize_t,
    _PyBytes_Resize, PyObject,
};
use crate::outcome::{Outcome, Stop};
use crate::reference::Owned;

/// A `bytes` object whose contents are written in place and trimmed to the
/// written size when finished, so the result is never copied and a small
/// result costs one allocation.
pub struct BytesWriter {
    object: *mut PyObject,
    size: usize,
    capacity: usize,
}

#[inline]
fn size_argument(size: usize) -> Outcome<Py_ssize_t> {
    Py_ssize_t::try_from(size).map_err(|_| {
        unsafe { PyErr_NoMemory() };
        Stop::Raised
    })
}

impl BytesWriter {
    /// A writer whose current size is `size` bytes, all uninitialized.
    #[inline]
    pub fn create(size: usize) -> Outcome<Self> {
        let raw = unsafe { PyBytes_FromStringAndSize(ptr::null(), size_argument(size)?) };
        if raw.is_null() {
            return Err(Stop::Raised);
        }
        Ok(Self {
            object: raw,
            size,
            capacity: size,
        })
    }

    #[inline]
    pub fn len(&self) -> usize {
        self.size
    }

    #[inline]
    pub fn is_empty(&self) -> bool {
        self.size == 0
    }

    /// The bytes up to the current size. Growing the writer invalidates them.
    #[inline]
    pub fn uninit(&mut self) -> &mut [MaybeUninit<u8>] {
        let data = unsafe { PyBytes_AsString(self.object) };
        unsafe { slice::from_raw_parts_mut(data.cast::<MaybeUninit<u8>>(), self.size) }
    }

    fn resize_object(&mut self, capacity: usize) -> Outcome<()> {
        let capacity_argument = size_argument(capacity)?;
        if unsafe { _PyBytes_Resize(&mut self.object, capacity_argument) } != 0 {
            self.size = 0;
            self.capacity = 0;
            return Err(Stop::Raised);
        }
        self.capacity = capacity;
        Ok(())
    }

    /// Extend the current size by `additional` uninitialized bytes.
    pub fn grow(&mut self, additional: usize) -> Outcome<()> {
        let size = self.size.checked_add(additional).ok_or_else(|| {
            unsafe { PyErr_NoMemory() };
            Stop::Raised
        })?;
        if size > self.capacity {
            self.resize_object(size.max(self.capacity.saturating_add(self.capacity / 4)))?;
        }
        self.size = size;
        Ok(())
    }

    /// Extend the current size by `additional` uninitialized bytes, resizing
    /// the object to exactly that size when it does not fit. For callers that
    /// choose their own growth policy.
    pub fn grow_exact(&mut self, additional: usize) -> Outcome<()> {
        let size = self.size.checked_add(additional).ok_or_else(|| {
            unsafe { PyErr_NoMemory() };
            Stop::Raised
        })?;
        if size > self.capacity {
            self.resize_object(size)?;
        }
        self.size = size;
        Ok(())
    }

    /// Append `bytes` after the current size.
    pub fn append(&mut self, bytes: &[u8]) -> Outcome<()> {
        let start = self.size;
        self.grow(bytes.len())?;
        for (slot, byte) in self.uninit()[start..].iter_mut().zip(bytes) {
            slot.write(*byte);
        }
        Ok(())
    }

    /// A `bytes` object holding a copy of `bytes`.
    #[inline]
    pub fn copy_of(bytes: &[u8]) -> Outcome<Owned> {
        let object = unsafe {
            PyBytes_FromStringAndSize(bytes.as_ptr().cast(), size_argument(bytes.len())?)
        };
        unsafe { Owned::from_new_reference(object) }
    }

    /// Finish into a `bytes` object holding the first `initialized` bytes.
    ///
    /// # Safety
    /// The first `initialized` bytes of the writer are initialized, and
    /// `initialized <= self.len()`.
    #[inline]
    pub unsafe fn finish(mut self, initialized: usize) -> Outcome<Owned> {
        debug_assert!(initialized <= self.size);
        if initialized != self.capacity {
            self.resize_object(initialized)?;
        }
        let writer = ManuallyDrop::new(self);
        unsafe { Owned::from_new_reference(writer.object) }
    }
}

impl Drop for BytesWriter {
    #[inline]
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.object) };
    }
}
