use core::ffi::{c_char, c_int, c_void};
use core::ptr;
use core::cell::UnsafeCell;
use core::sync::atomic::{AtomicBool, Ordering};

// The declarations use the 64-bit GIL-enabled CPython ABI. Keeping this small
// boundary local lets the matcher avoid mapping the Rust standard runtime.
pub type Py_ssize_t = isize;

#[repr(C)]
pub struct PyObject {
    pub ob_refcnt: Py_ssize_t,
    pub ob_type: *mut c_void,
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    pub void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    pub ml_name: *mut c_char,
    pub ml_meth: PyMethodDefFuncPointer,
    pub ml_flags: c_int,
    pub ml_doc: *mut c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
pub struct PyModuleDef_Base {
    pub ob_base: PyObject,
    pub m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    pub m_index: Py_ssize_t,
    pub m_copy: *mut PyObject,
}

#[repr(C)]
pub struct PyModuleDef_Slot {
    pub slot: c_int,
    pub value: *mut c_void,
}

unsafe impl Sync for PyModuleDef_Slot {}

#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    pub m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<extern "C" fn(*mut c_void)>,
}

pub const METH_FASTCALL: c_int = 0x0080;
pub const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 3;
pub const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2usize as *mut c_void;
/// `_Py_IMMORTAL_INITIAL_REFCNT | ((_Py_STATICALLY_ALLOCATED_FLAG |
/// _Py_IMMORTAL_FLAGS) << 48)` for the 64-bit GIL-enabled build.
const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);


pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject { ob_refcnt: STATIC_IMMORTAL_REFCNT, ob_type: ptr::null_mut() },
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_os = "macos", link(name = "System"))]
#[cfg_attr(target_os = "linux", link(name = "c"))]
unsafe extern "C" {
    pub static mut PyExc_TypeError: *mut PyObject;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyBool_FromLong(value: core::ffi::c_long) -> *mut PyObject;
    pub fn PyBytes_AsStringAndSize(object: *mut PyObject, data: *mut *mut c_char, size: *mut Py_ssize_t) -> c_int;
    pub fn Py_DecRef(object: *mut PyObject);
    pub fn PyErr_Clear();
    pub fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub fn PyUnicode_GetLength(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_New(size: Py_ssize_t, maxchar: u32) -> *mut PyObject;
    pub fn PyUnicode_ReadChar(object: *mut PyObject, index: Py_ssize_t) -> u32;
    pub fn PyUnicode_WriteChar(object: *mut PyObject, index: Py_ssize_t, character: u32) -> c_int;
    fn malloc(size: usize) -> *mut c_void;
    fn free(pointer: *mut c_void);
    fn posix_memalign(pointer: *mut *mut c_void, alignment: usize, size: usize) -> c_int;
    fn abort() -> !;
}

// Small matcher allocations share reusable storage. This avoids creating
// private malloc pages for each vector and tree-node size while retaining the
// same process ownership for cached patterns. Larger or fragmented requests
// use libc, so cache capacity and accepted pattern sizes remain unrestricted.
const HEAP_BYTES: usize = 64 * 1024;
const HEAP_ALIGNMENT: usize = 16;

// Total block size includes this header and stays a multiple of 16 bytes.
// Allocated blocks retain the size; only free blocks link to their successor.
#[repr(C)]
struct BlockHeader {
    block_bytes: usize,
    next_free: *mut BlockHeader,
}

const _: () = assert!(core::mem::size_of::<BlockHeader>() == HEAP_ALIGNMENT);

#[repr(align(16))]
struct HeapStorage(UnsafeCell<[u8; HEAP_BYTES]>);

struct HeapState {
    initialized: bool,
    first: *mut BlockHeader,
}

struct MatcherHeap {
    locked: AtomicBool,
    state: UnsafeCell<HeapState>,
    storage: HeapStorage,
}

// The allocation list and every block header are accessed under this lock.
// User allocation contents remain owned exclusively by their Rust values.
unsafe impl Sync for MatcherHeap {}

impl MatcherHeap {
    fn base(&self) -> *mut u8 {
        self.storage.0.get().cast()
    }

    fn lock(&self) {
        while self.locked.compare_exchange_weak(
            false, true, Ordering::Acquire, Ordering::Relaxed,
        ).is_err() {
            core::hint::spin_loop();
        }
    }

    fn unlock(&self) {
        self.locked.store(false, Ordering::Release);
    }

    unsafe fn allocate(&self, bytes: usize) -> *mut u8 {
        let header = core::mem::size_of::<BlockHeader>();
        let Some(rounded) = bytes.checked_add(HEAP_ALIGNMENT - 1) else {
            return ptr::null_mut();
        };
        let Some(needed) = (rounded & !(HEAP_ALIGNMENT - 1)).checked_add(header) else {
            return ptr::null_mut();
        };
        if needed > HEAP_BYTES {
            return ptr::null_mut();
        }
        self.lock();
        let state = unsafe { &mut *self.state.get() };
        if !state.initialized {
            let first = self.base().cast::<BlockHeader>();
            unsafe { first.write(BlockHeader { block_bytes: HEAP_BYTES, next_free: ptr::null_mut() }) };
            state.first = first;
            state.initialized = true;
        }
        let mut previous: *mut BlockHeader = ptr::null_mut();
        let mut block = state.first;
        while !block.is_null() {
            if unsafe { (*block).block_bytes } >= needed {
                let remaining = unsafe { (*block).block_bytes } - needed;
                let next = if remaining >= header + HEAP_ALIGNMENT {
                    let split = unsafe { block.cast::<u8>().add(needed).cast::<BlockHeader>() };
                    unsafe {
                        split.write(BlockHeader { block_bytes: remaining, next_free: (*block).next_free });
                        (*block).block_bytes = needed;
                    }
                    split
                } else {
                    unsafe { (*block).next_free }
                };
                if previous.is_null() {
                    state.first = next;
                } else {
                    unsafe { (*previous).next_free = next };
                }
                unsafe { (*block).next_free = ptr::null_mut() };
                self.unlock();
                return unsafe { block.cast::<u8>().add(header) };
            }
            previous = block;
            block = unsafe { (*block).next_free };
        }
        self.unlock();
        ptr::null_mut()
    }

    fn contains(&self, pointer: *mut u8) -> bool {
        let address = pointer as usize;
        let base = self.base() as usize;
        address >= base && address < base + HEAP_BYTES
    }

    unsafe fn release(&self, pointer: *mut u8) {
        let header = core::mem::size_of::<BlockHeader>();
        let block = unsafe { pointer.sub(header).cast::<BlockHeader>() };
        self.lock();
        let state = unsafe { &mut *self.state.get() };
        let mut previous: *mut BlockHeader = ptr::null_mut();
        let mut next = state.first;
        while !next.is_null() && (next as usize) < block as usize {
            previous = next;
            next = unsafe { (*next).next_free };
        }
        unsafe { (*block).next_free = next };
        if previous.is_null() {
            state.first = block;
        } else {
            unsafe { (*previous).next_free = block };
        }
        // Address ordering makes adjacent freed regions easy to coalesce.
        if !next.is_null() && unsafe { block.cast::<u8>().add((*block).block_bytes) } == next.cast::<u8>() {
            unsafe {
                (*block).block_bytes += (*next).block_bytes;
                (*block).next_free = (*next).next_free;
            }
        }
        if !previous.is_null() && unsafe { previous.cast::<u8>().add((*previous).block_bytes) } == block.cast::<u8>() {
            unsafe {
                (*previous).block_bytes += (*block).block_bytes;
                (*previous).next_free = (*block).next_free;
            }
        }
        self.unlock();
    }
}

static MATCHER_HEAP: MatcherHeap = MatcherHeap {
    locked: AtomicBool::new(false),
    state: UnsafeCell::new(HeapState { initialized: false, first: ptr::null_mut() }),
    storage: HeapStorage(UnsafeCell::new([0; HEAP_BYTES])),
};

struct Allocator;

unsafe impl core::alloc::GlobalAlloc for Allocator {
    unsafe fn alloc(&self, layout: core::alloc::Layout) -> *mut u8 {
        if layout.align() <= HEAP_ALIGNMENT {
            let pointer = unsafe { MATCHER_HEAP.allocate(layout.size()) };
            if !pointer.is_null() {
                return pointer;
            }
            unsafe { malloc(layout.size()).cast() }
        } else {
            let mut pointer = ptr::null_mut();
            if unsafe { posix_memalign(&mut pointer, layout.align(), layout.size()) } == 0 {
                pointer.cast()
            } else {
                ptr::null_mut()
            }
        }
    }

    unsafe fn dealloc(&self, pointer: *mut u8, _layout: core::alloc::Layout) {
        if MATCHER_HEAP.contains(pointer) {
            unsafe { MATCHER_HEAP.release(pointer) };
        } else {
            unsafe { free(pointer.cast()) };
        }
    }
}

#[global_allocator]
static ALLOCATOR: Allocator = Allocator;

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}
