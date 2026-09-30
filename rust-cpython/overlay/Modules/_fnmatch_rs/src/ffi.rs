use core::ffi::{c_char, c_int, c_void};
use core::ptr;

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

struct Allocator;

// libc supplies the same heap used by the standard Rust allocator. Alignments
// beyond its ordinary guarantee use the POSIX aligned-allocation interface.
unsafe impl core::alloc::GlobalAlloc for Allocator {
    unsafe fn alloc(&self, layout: core::alloc::Layout) -> *mut u8 {
        if layout.align() <= 16 {
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
        unsafe { free(pointer.cast()) };
    }
}

#[global_allocator]
static ALLOCATOR: Allocator = Allocator;

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}
