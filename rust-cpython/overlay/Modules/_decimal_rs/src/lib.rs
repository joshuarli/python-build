//! Exact decimal coefficient arithmetic with temporary Python-managed buffers.
#![no_std]
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

extern crate alloc;

use core::alloc::{GlobalAlloc, Layout};
use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::{ptr, slice};

// These C layouts describe the 64-bit, GIL-enabled CPython module boundary.
type Py_ssize_t = isize;

#[repr(C)]
pub struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut c_void,
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject,
    Void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

impl PyMethodDef {
    const fn zeroed() -> Self {
        Self {
            ml_name: ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer { Void: ptr::null_mut() },
            ml_flags: 0,
            ml_doc: ptr::null_mut(),
        }
    }
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
struct PyModuleDef_Slot {
    slot: c_int,
    value: *mut c_void,
}

#[repr(C)]
struct PyModuleDef {
    m_base: PyModuleDef_Base,
    m_name: *const c_char,
    m_doc: *const c_char,
    m_size: Py_ssize_t,
    m_methods: *mut PyMethodDef,
    m_slots: *mut PyModuleDef_Slot,
    m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
// Immortal reference count and static allocation flags in the 64-bit GIL ABI.
const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject {
        ob_refcnt: (3_isize << 30) | (5_isize << 48),
        ob_type: ptr::null_mut(),
    },
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_ValueError: *mut PyObject;
    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyUnicode_FromStringAndSize(value: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn PyMem_Malloc(size: usize) -> *mut c_void;
    fn PyMem_Realloc(pointer: *mut c_void, size: usize) -> *mut c_void;
    fn PyMem_Free(pointer: *mut c_void);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

// All arithmetic runs under the GIL and all temporary buffers die before the
// C entry point returns. Reusing Python's small-block pools avoids retaining
// a second allocator's size classes after the first integer operation.
struct PythonAllocator;

unsafe impl GlobalAlloc for PythonAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if layout.align() <= core::mem::align_of::<usize>() {
            return unsafe { PyMem_Malloc(layout.size()).cast() };
        }
        let Some(size) = layout.size().checked_add(layout.align()) else {
            return core::ptr::null_mut();
        };
        let base = unsafe { PyMem_Malloc(size).cast::<u8>() };
        if base.is_null() {
            return base;
        }
        let offset = layout.align() - (base as usize % layout.align());
        let aligned = unsafe { base.add(offset) };
        unsafe { aligned.sub(core::mem::size_of::<usize>()).cast::<*mut u8>().write(base) };
        aligned
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        let base = if layout.align() <= core::mem::align_of::<usize>() {
            pointer
        } else {
            unsafe { pointer.sub(core::mem::size_of::<usize>()).cast::<*mut u8>().read() }
        };
        unsafe { PyMem_Free(base.cast()) };
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if layout.align() <= core::mem::align_of::<usize>() {
            return unsafe { PyMem_Realloc(pointer.cast(), size).cast() };
        }
        let Ok(replacement_layout) = Layout::from_size_align(size, layout.align()) else {
            return core::ptr::null_mut();
        };
        let replacement = unsafe { self.alloc(replacement_layout) };
        if !replacement.is_null() {
            unsafe {
                core::ptr::copy_nonoverlapping(pointer, replacement, layout.size().min(size));
                self.dealloc(pointer, layout);
            }
        }
        replacement
    }
}

#[global_allocator]
static ALLOCATOR: PythonAllocator = PythonAllocator;

use num_bigint::BigUint;

enum Integer {
    Small(u128),
    Large(BigUint),
}

impl Integer {
    fn into_big(self) -> BigUint {
        match self {
            Self::Small(value) => BigUint::from(value),
            Self::Large(value) => value,
        }
    }
}

// Decimal coefficients usually fit a machine integer. Keep their parsing,
// arithmetic, and formatting on the stack; overflow retains exact precision.
fn parse_small(bytes: &[u8]) -> Option<u128> {
    if bytes.is_empty() {
        return None;
    }
    let mut value = 0u128;
    for &byte in bytes {
        if !byte.is_ascii_digit() {
            return None;
        }
        value = value.checked_mul(10)?.checked_add(u128::from(byte - b'0'))?;
    }
    Some(value)
}

unsafe fn small_result(mut value: u128) -> *mut PyObject {
    let mut digits = [0u8; 39];
    let mut start = digits.len();
    loop {
        start -= 1;
        digits[start] = b'0' + (value % 10) as u8;
        value /= 10;
        if value == 0 {
            break;
        }
    }
    unsafe {
        PyUnicode_FromStringAndSize(
            digits[start..].as_ptr().cast::<c_char>(),
            (digits.len() - start) as Py_ssize_t,
        )
    }
}

unsafe fn parse_integer(object: *mut PyObject) -> Result<Integer, ()> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    if let Some(value) = parse_small(bytes) {
        return Ok(Integer::Small(value));
    }
    match BigUint::parse_bytes(bytes, 10) {
        Some(value) => Ok(Integer::Large(value)),
        None => {
            unsafe { PyErr_SetString(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
            Err(())
        }
    }
}

unsafe extern "C" fn add_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }
    let left = match unsafe { parse_integer(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let right = match unsafe { parse_integer(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let result = match (left, right) {
        (Integer::Small(left), Integer::Small(right)) => {
            if let Some(result) = left.checked_add(right) {
                return unsafe { small_result(result) };
            }
            (BigUint::from(left) + BigUint::from(right)).to_str_radix(10)
        }
        (left, right) => (left.into_big() + right.into_big()).to_str_radix(10),
    };
    unsafe {
        PyUnicode_FromStringAndSize(result.as_ptr().cast::<c_char>(), result.len() as Py_ssize_t)
    }
}

unsafe extern "C" fn multiply_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }
    let left = match unsafe { parse_integer(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let right = match unsafe { parse_integer(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let result = match (left, right) {
        (Integer::Small(left), Integer::Small(right)) => {
            if let Some(result) = left.checked_mul(right) {
                return unsafe { small_result(result) };
            }
            (BigUint::from(left) * BigUint::from(right)).to_str_radix(10)
        }
        (left, right) => (left.into_big() * right.into_big()).to_str_radix(10),
    };
    unsafe {
        PyUnicode_FromStringAndSize(result.as_ptr().cast::<c_char>(), result.len() as Py_ssize_t)
    }
}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"multiply_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: multiply_exact_integers },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Multiply two nonnegative decimal integer coefficients exactly.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"add_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: add_exact_integers },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Add two nonnegative decimal integer coefficients exactly.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

struct ModuleSlots([PyModuleDef_Slot; 2]);

unsafe impl Sync for ModuleSlots {}

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: 2usize as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_decimal_rs".as_ptr() as *mut _,
    m_doc: c"Exact integer coefficient arithmetic for decimal.Decimal.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: SLOTS.0.as_ptr() as *mut _,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__decimal_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
