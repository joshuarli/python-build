use core::ops::{Deref, DerefMut};
use core::ptr::NonNull;
use super::ffi::{PyMem_Free, PyMem_Malloc, PyMem_Realloc};

// Matching scratch values have no destructors, nonzero size, and word alignment.
// Restricting the element types keeps the allocator and bytewise sorter boundary
// independent of generic Rust allocation support.
pub(super) trait MatchElement: Copy {}
impl MatchElement for i64 {}
impl MatchElement for (i64, usize) {}
impl MatchElement for (usize, usize) {}

pub(super) struct MatchBuffer<T: MatchElement> {
    data: *mut T,
    length: usize,
    capacity: usize,
}

impl<T: MatchElement> MatchBuffer<T> {
    pub(super) fn new() -> Self {
        Self { data: NonNull::<T>::dangling().as_ptr(), length: 0, capacity: 0 }
    }

    pub(super) fn try_reserve_exact(&mut self, additional: usize) -> Result<(), ()> {
        let required = self.length.checked_add(additional).ok_or(())?;
        if required <= self.capacity {
            return Ok(());
        }
        let bytes = required.checked_mul(core::mem::size_of::<T>()).ok_or(())?;
        if bytes > isize::MAX as usize {
            return Err(());
        }
        let data = unsafe {
            if self.capacity == 0 {
                PyMem_Malloc(bytes)
            } else {
                PyMem_Realloc(self.data.cast(), bytes)
            }
        }.cast::<T>();
        if data.is_null() {
            return Err(());
        }
        self.data = data;
        self.capacity = required;
        Ok(())
    }

    pub(super) fn try_reserve(&mut self, additional: usize) -> Result<(), ()> {
        self.try_reserve_exact(additional)
    }

    pub(super) fn push(&mut self, value: T) {
        assert!(self.length < self.capacity);
        unsafe { self.data.add(self.length).write(value) };
        self.length += 1;
    }

    pub(super) fn clear(&mut self) {
        self.length = 0;
    }
}

impl<T: MatchElement> Deref for MatchBuffer<T> {
    type Target = [T];
    fn deref(&self) -> &[T] {
        unsafe { core::slice::from_raw_parts(self.data, self.length) }
    }
}

impl<T: MatchElement> DerefMut for MatchBuffer<T> {
    fn deref_mut(&mut self) -> &mut [T] {
        unsafe { core::slice::from_raw_parts_mut(self.data, self.length) }
    }
}

impl<T: MatchElement> Drop for MatchBuffer<T> {
    fn drop(&mut self) {
        if self.capacity != 0 {
            unsafe { PyMem_Free(self.data.cast()) };
        }
    }
}
