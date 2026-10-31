use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_binding::ffi::{
    _PyBytes_Resize, Py_DecRef, Py_ssize_t, PyBytes_AsString, PyBytes_FromStringAndSize, PyObject,
};
use cpython_binding::{Exception, Outcome, Owned, Sink, Stop, raise};

/// A `bytes` object that the engine fills in place and resizes to exactly the
/// room it asks for, so the allocation the engine doubles is the allocation
/// that exists. `cpython_binding::BytesSink` over-allocates every growth by a
/// quarter, which on top of doubling holds more memory than the output needs.
pub struct ExactBytesSink {
    object: *mut PyObject,
    capacity: usize,
    written: usize,
}

fn output_too_large() -> Stop {
    raise(Exception::MemoryError, c"output too large")
}

fn object_size(size: usize) -> Outcome<Py_ssize_t> {
    Py_ssize_t::try_from(size).map_err(|_| output_too_large())
}

impl ExactBytesSink {
    pub fn with_capacity(capacity: usize) -> Outcome<Self> {
        let capacity = capacity.max(1);
        let object = unsafe { PyBytes_FromStringAndSize(ptr::null(), object_size(capacity)?) };
        if object.is_null() {
            return Err(Stop::Raised);
        }
        Ok(Self {
            object,
            capacity,
            written: 0,
        })
    }

    fn resize(&mut self, capacity: usize) -> Outcome<()> {
        let size = object_size(capacity)?;
        if unsafe { _PyBytes_Resize(&mut self.object, size) } != 0 {
            return Err(Stop::Raised);
        }
        self.capacity = capacity;
        Ok(())
    }

    pub fn finish(mut self) -> Outcome<Owned> {
        if self.written == 0 {
            return unsafe { Owned::from_new_reference(PyBytes_FromStringAndSize(c"".as_ptr(), 0)) };
        }
        if self.written != self.capacity {
            self.resize(self.written)?;
        }
        let object = self.object;
        self.object = ptr::null_mut();
        unsafe { Owned::from_new_reference(object) }
    }
}

impl Sink for ExactBytesSink {
    fn written(&self) -> usize {
        self.written
    }

    fn spare(&mut self) -> &mut [MaybeUninit<u8>] {
        let start = unsafe { PyBytes_AsString(self.object) }.cast::<MaybeUninit<u8>>();
        unsafe { slice::from_raw_parts_mut(start.add(self.written), self.capacity - self.written) }
    }

    fn grow(&mut self, additional: usize) -> Outcome<()> {
        let capacity = self
            .capacity
            .checked_add(additional)
            .ok_or_else(output_too_large)?;
        self.resize(capacity)
    }

    unsafe fn advance(&mut self, count: usize) {
        self.written += count;
    }
}

impl Drop for ExactBytesSink {
    fn drop(&mut self) {
        if !self.object.is_null() {
            unsafe { Py_DecRef(self.object) };
        }
    }
}

