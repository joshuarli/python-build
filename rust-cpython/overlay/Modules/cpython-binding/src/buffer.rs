use core::mem::MaybeUninit;
use core::slice;

use crate::ffi::{PyBUF_SIMPLE, PyBuffer_Release, PyObject_GetBuffer, Py_buffer};
use crate::outcome::{Outcome, Stop};
use crate::reference::Borrowed;

/// A simple (contiguous bytes) `Py_buffer` view, released on drop.
pub struct Buffer {
    view: Py_buffer,
}

impl Buffer {
    #[inline]
    pub fn acquire(object: Borrowed<'_>) -> Outcome<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object.as_ptr(), view.as_mut_ptr(), PyBUF_SIMPLE) } != 0 {
            return Err(Stop::Raised);
        }
        Ok(Self {
            view: unsafe { view.assume_init() },
        })
    }

    #[inline]
    pub fn as_bytes(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for Buffer {
    #[inline]
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) };
    }
}
