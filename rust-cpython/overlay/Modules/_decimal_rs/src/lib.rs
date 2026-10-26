#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;
use core::slice;

type Py_ssize_t = isize;

#[repr(C)]
struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut c_void,
}

type PyCFunctionFast = unsafe extern "C" fn(
    slf: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject;

#[repr(C)]
union PyMethodDefFuncPointer {
    fast: PyCFunctionFast,
    pointer: *mut c_void,
}

#[repr(C)]
struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

// SAFETY: method definitions are immutable after static initialization and CPython only reads them.
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
    m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
const MAX_INPUT_DIGITS: usize = 128;
const MAX_RESULT_DIGITS: usize = MAX_INPUT_DIGITS * 2;
const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_OverflowError: *mut PyObject;
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_ValueError: *mut PyObject;

    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyUnicode_FromStringAndSize(text: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // SAFETY: abort has no preconditions and terminates the process.
    unsafe { abort() }
}

#[derive(Clone, Copy)]
struct Digits {
    values: [u8; MAX_RESULT_DIGITS],
    len: usize,
}

impl Digits {
    const fn zeroed() -> Self {
        Self {
            values: [0; MAX_RESULT_DIGITS],
            len: 0,
        }
    }
}

unsafe fn set_error(exception: *mut PyObject, message: *const c_char) {
    unsafe {
        // SAFETY: the caller holds the GIL and supplies a live exception object and static C string.
        PyErr_SetString(exception, message);
    }
}

unsafe fn parse_coefficient(object: *mut PyObject) -> Option<Digits> {
    if object.is_null() {
        unsafe { set_error(PyExc_TypeError, c"expected decimal integer strings".as_ptr()) };
        return None;
    }

    let mut size = 0;
    // SAFETY: object is a live argument owned by the active CPython call.
    let text = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if text.is_null() {
        return None;
    }
    if size <= 0 || size as usize > MAX_INPUT_DIGITS {
        unsafe { set_error(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
        return None;
    }

    // SAFETY: CPython returns a readable UTF-8 buffer covering the reported positive byte length.
    let bytes = unsafe { slice::from_raw_parts(text.cast::<u8>(), size as usize) };
    let mut digits = Digits::zeroed();
    digits.len = bytes.len();
    for (index, byte) in bytes.iter().rev().enumerate() {
        if !byte.is_ascii_digit() {
            unsafe { set_error(PyExc_ValueError, c"invalid decimal integer".as_ptr()) };
            return None;
        }
        digits.values[index] = *byte - b'0';
    }
    Some(digits)
}

fn add(left: &Digits, right: &Digits) -> Option<Digits> {
    let mut result = Digits::zeroed();
    let width = left.len.max(right.len);
    let mut carry = 0u16;

    for index in 0..width {
        let sum = u16::from(left.values[index]) + u16::from(right.values[index]) + carry;
        result.values[index] = (sum % 10) as u8;
        carry = sum / 10;
    }
    result.len = width;
    if carry != 0 {
        *result.values.get_mut(width)? = carry as u8;
        result.len += 1;
    }
    Some(result)
}

fn multiply(left: &Digits, right: &Digits) -> Option<Digits> {
    let mut result = Digits::zeroed();
    if (left.len == 1 && left.values[0] == 0) || (right.len == 1 && right.values[0] == 0) {
        result.len = 1;
        return Some(result);
    }

    for left_index in 0..left.len {
        let mut carry = 0u16;
        for right_index in 0..right.len {
            let index = left_index + right_index;
            let product = u16::from(result.values[index])
                + u16::from(left.values[left_index]) * u16::from(right.values[right_index])
                + carry;
            result.values[index] = (product % 10) as u8;
            carry = product / 10;
        }

        let mut index = left_index + right.len;
        while carry != 0 {
            let digit = result.values.get_mut(index)?;
            let sum = u16::from(*digit) + carry;
            *digit = (sum % 10) as u8;
            carry = sum / 10;
            index += 1;
        }
    }

    result.len = left.len.checked_add(right.len)?;
    while result.len > 1 && result.values[result.len - 1] == 0 {
        result.len -= 1;
    }
    Some(result)
}

unsafe fn exact_integer_operation(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    operation: fn(&Digits, &Digits) -> Option<Digits>,
) -> *mut PyObject {
    if nargs != 2 || args.is_null() {
        unsafe { set_error(PyExc_TypeError, c"expected two decimal integers".as_ptr()) };
        return ptr::null_mut();
    }

    // SAFETY: CPython's FASTCALL contract provides nargs argument pointers when nargs is two.
    let left_object = unsafe { *args };
    // SAFETY: CPython's FASTCALL contract provides nargs argument pointers when nargs is two.
    let right_object = unsafe { *args.add(1) };
    let Some(left) = (unsafe { parse_coefficient(left_object) }) else {
        return ptr::null_mut();
    };
    let Some(right) = (unsafe { parse_coefficient(right_object) }) else {
        return ptr::null_mut();
    };
    let Some(result) = operation(&left, &right) else {
        unsafe { set_error(PyExc_OverflowError, c"decimal integer result is too large".as_ptr()) };
        return ptr::null_mut();
    };

    let mut text = [0u8; MAX_RESULT_DIGITS];
    for index in 0..result.len {
        text[result.len - index - 1] = b'0' + result.values[index];
    }
    // SAFETY: text contains result.len initialized ASCII bytes for the duration of the call.
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), result.len as Py_ssize_t) }
}

unsafe extern "C" fn add_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integer_operation(args, nargs, add) }
}

unsafe extern "C" fn multiply_exact_integers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { exact_integer_operation(args, nargs, multiply) }
}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"multiply_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            fast: multiply_exact_integers,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Multiply two nonnegative decimal integer coefficients exactly.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"add_exact_integers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            fast: add_exact_integers,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Add two nonnegative decimal integer coefficients exactly.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: ptr::null_mut(),
        ml_meth: PyMethodDefFuncPointer {
            pointer: ptr::null_mut(),
        },
        ml_flags: 0,
        ml_doc: ptr::null_mut(),
    },
];

struct ModuleSlots([PyModuleDef_Slot; 2]);

// SAFETY: the module slots are immutable after static initialization and CPython only reads them.
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

// SAFETY: CPython owns initialization and access to the module definition through its import machinery.
unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_Base {
        ob_base: PyObject {
            ob_refcnt: STATIC_IMMORTAL_REFCNT,
            ob_type: ptr::null_mut(),
        },
        m_init: None,
        m_index: 0,
        m_copy: ptr::null_mut(),
    },
    m_name: c"_decimal_rs".as_ptr(),
    m_doc: c"Exact integer coefficient arithmetic for decimal.Decimal.".as_ptr(),
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: SLOTS.0.as_ptr() as *mut _,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__decimal_rs() -> *mut PyObject {
    // SAFETY: MODULE has static storage, a valid CPython 3.16 module definition layout, and is initialized once by CPython.
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
