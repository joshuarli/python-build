use core::alloc::{GlobalAlloc, Layout};
use core::mem::{align_of, size_of};
use core::ptr;

use crate::ffi::{PyMem_Free, PyMem_Malloc, PyMem_Realloc};

/// A global allocator backed by `PyMem_Malloc`.
///
/// Every allocation, reallocation and release must run on a thread with an
/// attached thread state, and no block may outlive the interpreter that
/// allocated it. A module installs it only when all of its Rust allocation
/// happens inside C-API entry points it is called through.
pub struct AttachedThreadAllocator;

const HEADER: usize = size_of::<*mut u8>();

unsafe impl GlobalAlloc for AttachedThreadAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if layout.align() <= align_of::<usize>() {
            return unsafe { PyMem_Malloc(layout.size()).cast() };
        }
        let Some(size) = layout.size().checked_add(layout.align()) else {
            return ptr::null_mut();
        };
        let base = unsafe { PyMem_Malloc(size).cast::<u8>() };
        if base.is_null() {
            return base;
        }
        let offset = layout.align() - (base as usize % layout.align());
        let aligned = unsafe { base.add(offset) };
        unsafe { aligned.sub(HEADER).cast::<*mut u8>().write(base) };
        aligned
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        let base = if layout.align() <= align_of::<usize>() {
            pointer
        } else {
            unsafe { pointer.sub(HEADER).cast::<*mut u8>().read() }
        };
        unsafe { PyMem_Free(base.cast()) };
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if layout.align() <= align_of::<usize>() {
            return unsafe { PyMem_Realloc(pointer.cast(), size).cast() };
        }
        let Ok(replacement_layout) = Layout::from_size_align(size, layout.align()) else {
            return ptr::null_mut();
        };
        let replacement = unsafe { self.alloc(replacement_layout) };
        if !replacement.is_null() {
            unsafe {
                ptr::copy_nonoverlapping(pointer, replacement, layout.size().min(size));
                self.dealloc(pointer, layout);
            }
        }
        replacement
    }
}
