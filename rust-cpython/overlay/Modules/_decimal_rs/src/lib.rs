//! Exact decimal coefficients with inline limbs and owned Python buffers.
#![no_std]
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::{ptr, slice};

type Py_ssize_t = isize;

// The supported hosts use the 64-bit, GIL-enabled CPython object header.
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
        Self { ml_name: ptr::null_mut(), ml_meth: PyMethodDefFuncPointer { Void: ptr::null_mut() },
               ml_flags: 0, ml_doc: ptr::null_mut() }
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
    m_name: *mut c_char,
    m_doc: *mut c_char,
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
    ob_base: PyObject { ob_refcnt: (3_isize << 30) | (5_isize << 48), ob_type: ptr::null_mut() },
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_ValueError: *mut PyObject;
    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyErr_NoMemory() -> *mut PyObject;
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyUnicode_FromStringAndSize(value: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn PyMem_Malloc(size: usize) -> *mut c_void;
    fn PyMem_Free(pointer: *mut c_void);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

fn memory_error() {
    unsafe { PyErr_NoMemory(); }
}

// Each buffer is unique, remains under the calling interpreter's GIL, and
// dies before the C entry point returns. Python allocations provide the
// alignment required by u32 limbs; no Rust allocator or allocation handler
// is linked, and allocation failure preserves Python's MemoryError.
struct PythonBuffer {
    pointer: *mut c_void,
}

impl PythonBuffer {
    fn new(bytes: usize) -> Result<Self, ()> {
        if bytes > Py_ssize_t::MAX as usize {
            memory_error();
            return Err(());
        }
        let pointer = unsafe { PyMem_Malloc(bytes) };
        if pointer.is_null() {
            memory_error();
            Err(())
        } else {
            Ok(Self { pointer })
        }
    }
}

impl Drop for PythonBuffer {
    fn drop(&mut self) {
        unsafe { PyMem_Free(self.pointer) }
    }
}

// Decimal coefficients stay in base 10^9, so parsing and formatting never
// require binary-radix conversion. Thirty inline limbs cover both inputs and
// the product of the public route's two at-most-128-digit coefficients.
const BASE: u64 = 1_000_000_000;
const INLINE_LIMBS: usize = 30;

enum Limbs {
    Inline([u32; INLINE_LIMBS]),
    Large { buffer: PythonBuffer, length: usize },
}

impl Limbs {
    fn zeroed(length: usize) -> Result<Self, ()> {
        if length <= INLINE_LIMBS {
            Ok(Self::Inline([0; INLINE_LIMBS]))
        } else {
            let bytes = match length.checked_mul(core::mem::size_of::<u32>()) {
                Some(bytes) => bytes,
                None => { memory_error(); return Err(()); }
            };
            let buffer = PythonBuffer::new(bytes)?;
            unsafe { ptr::write_bytes(buffer.pointer.cast::<u32>(), 0, length) };
            Ok(Self::Large { buffer, length })
        }
    }

    fn digits(&self) -> &[u32] {
        match self {
            Self::Inline(digits) => digits,
            Self::Large { buffer, length } => unsafe { slice::from_raw_parts(buffer.pointer.cast::<u32>(), *length) },
        }
    }

    fn digits_mut(&mut self) -> &mut [u32] {
        match self {
            Self::Inline(digits) => digits,
            Self::Large { buffer, length } => unsafe { slice::from_raw_parts_mut(buffer.pointer.cast::<u32>(), *length) },
        }
    }
}

struct Coefficient {
    limbs: Limbs,
    length: usize,
}

impl Coefficient {
    fn parse(mut bytes: &[u8]) -> Result<Option<Self>, ()> {
        if bytes.first() == Some(&b'+') {
            bytes = &bytes[1..];
        }
        if !matches!(bytes.first(), Some(b'0'..=b'9')) {
            return Ok(None);
        }
        let mut significant = 0;
        let mut nonzero = false;
        for &byte in bytes {
            match byte {
                b'0'..=b'9' => {
                    nonzero |= byte != b'0';
                    significant += usize::from(nonzero);
                }
                b'_' => {}
                _ => return Ok(None),
            }
        }
        let length = significant.max(1).div_ceil(9);
        let mut result = Self { limbs: Limbs::zeroed(length)?, length };
        let digits = result.limbs.digits_mut();
        let mut position = 0;
        let mut place = 1;
        for &byte in bytes.iter().rev() {
            if byte == b'_' {
                continue;
            }
            if position >= significant {
                break;
            }
            digits[position / 9] += u32::from(byte - b'0') * place;
            position += 1;
            place = if position % 9 == 0 { 1 } else { place * 10 };
        }
        Ok(Some(result))
    }

    fn add(&self, other: &Self) -> Result<Self, ()> {
        let length = self.length.max(other.length);
        let mut result = Self { limbs: Limbs::zeroed(length + 1)?, length: length + 1 };
        let mut carry = 0;
        for index in 0..length {
            let left = if index < self.length { self.limbs.digits()[index] } else { 0 };
            let right = if index < other.length { other.limbs.digits()[index] } else { 0 };
            let value = u64::from(left) + u64::from(right) + carry;
            result.limbs.digits_mut()[index] = (value % BASE) as u32;
            carry = value / BASE;
        }
        result.limbs.digits_mut()[length] = carry as u32;
        result.normalize();
        Ok(result)
    }

    fn multiply(&self, other: &Self) -> Result<Self, ()> {
        let length = match self.length.checked_add(other.length) {
            Some(length) => length,
            None => { memory_error(); return Err(()); }
        };
        let mut result = Self { limbs: Limbs::zeroed(length)?, length };
        let digits = result.limbs.digits_mut();
        for left in 0..self.length {
            let mut carry = 0;
            for right in 0..other.length {
                // Each limb and carry is below BASE. Their product plus the
                // accumulated limb and carry is below BASE squared, fitting u64.
                let value = u64::from(self.limbs.digits()[left])
                    * u64::from(other.limbs.digits()[right])
                    + u64::from(digits[left + right]) + carry;
                digits[left + right] = (value % BASE) as u32;
                carry = value / BASE;
            }
            digits[left + other.length] = carry as u32;
        }
        result.normalize();
        Ok(result)
    }

    fn normalize(&mut self) {
        while self.length > 1 && self.limbs.digits()[self.length - 1] == 0 {
            self.length -= 1;
        }
    }

    unsafe fn unicode(&self) -> *mut PyObject {
        let capacity = match self.length.checked_mul(9) {
            Some(capacity) => capacity,
            None => { memory_error(); return ptr::null_mut(); }
        };
        let mut inline = [0u8; INLINE_LIMBS * 9];
        let large = if capacity > inline.len() {
            match PythonBuffer::new(capacity) {
                Ok(buffer) => Some(buffer),
                Err(()) => return ptr::null_mut(),
            }
        } else {
            None
        };
        let bytes = match large.as_ref() {
            Some(buffer) => unsafe { slice::from_raw_parts_mut(buffer.pointer.cast::<u8>(), capacity) },
            None => &mut inline[..capacity],
        };
        let mut position = capacity;
        for &limb in &self.limbs.digits()[..self.length] {
            let mut value = limb;
            for _ in 0..9 {
                position -= 1;
                bytes[position] = b'0' + (value % 10) as u8;
                value /= 10;
            }
        }
        let first = bytes.iter().position(|&byte| byte != b'0').unwrap_or(capacity - 1);
        unsafe {
            PyUnicode_FromStringAndSize(bytes[first..].as_ptr().cast::<c_char>(),
                                        (capacity - first) as Py_ssize_t)
        }
    }
}

unsafe fn parse_integer(object: *mut PyObject) -> Result<Coefficient, ()> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    match Coefficient::parse(bytes) {
        Ok(Some(value)) => Ok(value),
        Err(()) => Err(()),
        Ok(None) => {
            unsafe { PyErr_SetString(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
            Err(())
        }
    }
}

unsafe fn exact_integers(args: *mut *mut PyObject, nargs: Py_ssize_t,
                        multiply: bool) -> *mut PyObject {
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
    let result = match if multiply { left.multiply(&right) } else { left.add(&right) } {
        Ok(result) => result,
        Err(()) => return ptr::null_mut(),
    };
    unsafe { result.unicode() }
}

unsafe extern "C" fn add_exact_integers(
    _module: *mut PyObject, args: *mut *mut PyObject, nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integers(args, nargs, false) }
}

unsafe extern "C" fn multiply_exact_integers(
    _module: *mut PyObject, args: *mut *mut PyObject, nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integers(args, nargs, true) }
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
