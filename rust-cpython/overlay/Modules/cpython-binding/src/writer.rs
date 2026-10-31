use core::mem::{ManuallyDrop, MaybeUninit};
use core::ptr::NonNull;
use core::slice;

use crate::ffi::{
    PyBytesWriter, PyBytesWriter_Create, PyBytesWriter_Discard, PyBytesWriter_FinishWithSize,
    PyBytesWriter_GetData, PyBytesWriter_GetSize, PyBytesWriter_Grow, PyBytesWriter_WriteBytes,
    PyErr_NoMemory, Py_ssize_t,
};
use crate::outcome::{Outcome, Stop};
use crate::reference::Owned;

/// CPython's `PyBytesWriter`: output bytes written in place, with no
/// intermediate buffer, finished into a `bytes` object of the exact size.
pub struct BytesWriter(NonNull<PyBytesWriter>);

fn size_argument(size: usize) -> Outcome<Py_ssize_t> {
    Py_ssize_t::try_from(size).map_err(|_| {
        unsafe { PyErr_NoMemory() };
        Stop::Raised
    })
}

impl BytesWriter {
    /// A writer whose current size is `size` bytes, all uninitialized.
    pub fn create(size: usize) -> Outcome<Self> {
        let raw = unsafe { PyBytesWriter_Create(size_argument(size)?) };
        NonNull::new(raw).map(Self).ok_or(Stop::Raised)
    }

    pub fn len(&self) -> usize {
        unsafe { PyBytesWriter_GetSize(self.0.as_ptr()) as usize }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// The bytes up to the current size. Growing the writer invalidates them.
    pub fn uninit(&mut self) -> &mut [MaybeUninit<u8>] {
        let data = unsafe { PyBytesWriter_GetData(self.0.as_ptr()) };
        unsafe { slice::from_raw_parts_mut(data.cast::<MaybeUninit<u8>>(), self.len()) }
    }

    /// Extend the current size by `additional` uninitialized bytes.
    pub fn grow(&mut self, additional: usize) -> Outcome<()> {
        let additional = size_argument(additional)?;
        match unsafe { PyBytesWriter_Grow(self.0.as_ptr(), additional) } {
            0 => Ok(()),
            _ => Err(Stop::Raised),
        }
    }

    /// Append `bytes` after the current size.
    pub fn append(&mut self, bytes: &[u8]) -> Outcome<()> {
        let size = size_argument(bytes.len())?;
        match unsafe { PyBytesWriter_WriteBytes(self.0.as_ptr(), bytes.as_ptr().cast(), size) } {
            0 => Ok(()),
            _ => Err(Stop::Raised),
        }
    }

    /// A `bytes` object holding a copy of `bytes`.
    pub fn copy_of(bytes: &[u8]) -> Outcome<Owned> {
        let mut writer = Self::create(0)?;
        writer.append(bytes)?;
        unsafe { writer.finish(bytes.len()) }
    }

    /// Finish into a `bytes` object holding the first `initialized` bytes.
    ///
    /// # Safety
    /// The first `initialized` bytes of the writer are initialized, and
    /// `initialized <= self.len()`.
    pub unsafe fn finish(self, initialized: usize) -> Outcome<Owned> {
        debug_assert!(initialized <= self.len());
        let writer = ManuallyDrop::new(self);
        let object =
            unsafe { PyBytesWriter_FinishWithSize(writer.0.as_ptr(), initialized as Py_ssize_t) };
        unsafe { Owned::from_new_reference(object) }
    }
}

impl Drop for BytesWriter {
    fn drop(&mut self) {
        unsafe { PyBytesWriter_Discard(self.0.as_ptr()) };
    }
}
