use std::alloc::{GlobalAlloc, Layout};
use std::cell::Cell;
use std::ffi::c_void;
use std::slice;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;

use cpython_binding::pymem::AttachedThreadAllocator;

unsafe extern "C" {
    fn malloc(size: usize) -> *mut c_void;
    fn free(pointer: *mut c_void);
}

const PREFIX: usize = 8;

thread_local! {
    static ATTACHED: Cell<bool> = const { Cell::new(false) };
}

static DETACHED_CALLS: AtomicUsize = AtomicUsize::new(0);

fn attached<T>(body: impl FnOnce() -> T) -> T {
    ATTACHED.with(|state| state.set(true));
    let result = body();
    ATTACHED.with(|state| state.set(false));
    result
}

fn require_attached() {
    if !ATTACHED.with(Cell::get) {
        DETACHED_CALLS.fetch_add(1, Ordering::SeqCst);
    }
}

#[unsafe(no_mangle)]
extern "C" fn PyMem_Malloc(size: usize) -> *mut c_void {
    require_attached();
    let raw = unsafe { malloc(size + 2 * PREFIX) }.cast::<u8>();
    if raw.is_null() {
        return std::ptr::null_mut();
    }
    unsafe {
        raw.cast::<usize>().write(size);
        raw.add(PREFIX).cast()
    }
}

#[unsafe(no_mangle)]
extern "C" fn PyMem_Free(pointer: *mut c_void) {
    require_attached();
    if !pointer.is_null() {
        unsafe { free(pointer.cast::<u8>().sub(PREFIX).cast()) };
    }
}

#[unsafe(no_mangle)]
extern "C" fn PyMem_Realloc(pointer: *mut c_void, size: usize) -> *mut c_void {
    require_attached();
    let replacement = PyMem_Malloc(size);
    if !replacement.is_null() && !pointer.is_null() {
        let old = unsafe { pointer.cast::<u8>().sub(PREFIX).cast::<usize>().read() };
        unsafe {
            std::ptr::copy_nonoverlapping(
                pointer.cast::<u8>(),
                replacement.cast::<u8>(),
                old.min(size),
            );
        }
        PyMem_Free(pointer);
    }
    replacement
}

const ALLOCATOR: AttachedThreadAllocator = AttachedThreadAllocator;
const ALIGNMENTS: [usize; 6] = [1, 8, 16, 32, 64, 4096];

fn layout(size: usize, align: usize) -> Layout {
    Layout::from_size_align(size, align).unwrap()
}

fn fill(pointer: *mut u8, length: usize) {
    for index in 0..length {
        unsafe { pointer.add(index).write((index % 251) as u8 + 1) };
    }
}

fn prefix_intact(pointer: *mut u8, length: usize) -> bool {
    unsafe { slice::from_raw_parts(pointer, length) }
        .iter()
        .enumerate()
        .all(|(index, &byte)| byte == (index % 251) as u8 + 1)
}

#[test]
fn allocations_honor_the_requested_alignment() {
    attached(|| {
        for align in ALIGNMENTS {
            let pointer = unsafe { ALLOCATOR.alloc(layout(40, align)) };
            assert!(!pointer.is_null());
            assert_eq!(pointer as usize % align, 0);
            fill(pointer, 40);
            assert!(prefix_intact(pointer, 40));
            unsafe { ALLOCATOR.dealloc(pointer, layout(40, align)) };
        }
    });
}

#[test]
fn zeroed_allocation_is_zero_after_a_dirty_block_is_freed() {
    attached(|| {
        for align in ALIGNMENTS {
            let size = 300;
            let dirty = unsafe { ALLOCATOR.alloc(layout(size, align)) };
            unsafe { std::ptr::write_bytes(dirty, 0xAA, size) };
            unsafe { ALLOCATOR.dealloc(dirty, layout(size, align)) };
            let pointer = unsafe { ALLOCATOR.alloc_zeroed(layout(size, align)) };
            assert_eq!(pointer as usize % align, 0);
            assert!(unsafe { slice::from_raw_parts(pointer, size) }.iter().all(|&byte| byte == 0));
            unsafe { ALLOCATOR.dealloc(pointer, layout(size, align)) };
        }
    });
}

#[test]
fn realloc_keeps_the_common_prefix_and_alignment() {
    attached(|| {
        for align in ALIGNMENTS {
            let pointer = unsafe { ALLOCATOR.alloc(layout(48, align)) };
            fill(pointer, 48);
            let grown = unsafe { ALLOCATOR.realloc(pointer, layout(48, align), 5000) };
            assert_eq!(grown as usize % align, 0);
            assert!(prefix_intact(grown, 48));
            fill(grown, 5000);
            let shrunk = unsafe { ALLOCATOR.realloc(grown, layout(5000, align), 24) };
            assert_eq!(shrunk as usize % align, 0);
            assert!(prefix_intact(shrunk, 24));
            unsafe { ALLOCATOR.dealloc(shrunk, layout(24, align)) };
        }
    });
}

#[test]
fn every_thread_attaches_before_it_allocates() {
    let workers: Vec<_> = (0..4)
        .map(|_| {
            thread::spawn(|| {
                attached(|| {
                    let pointer = unsafe { ALLOCATOR.alloc(layout(64, 16)) };
                    assert!(!pointer.is_null());
                    unsafe { ALLOCATOR.dealloc(pointer, layout(64, 16)) };
                });
            })
        })
        .collect();
    for worker in workers {
        worker.join().unwrap();
    }
    assert_eq!(DETACHED_CALLS.load(Ordering::SeqCst), 0);
}
