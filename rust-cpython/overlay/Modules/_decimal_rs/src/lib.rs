use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, PyErr_SetString, PyExc_TypeError, PyExc_ValueError, PyMethodDef,
    PyMethodDefFuncPointer, PyABIInfo, PySlot, PySlot__bindgen_ty_1,
    PySlot__bindgen_ty_2, Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods,
    PySlot_INTPTR, PySlot_STATIC, PyObject, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize,
    Py_ssize_t,
};
use num_bigint::BigUint;

unsafe fn parse_integer(object: *mut PyObject) -> Result<BigUint, ()> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    match BigUint::parse_bytes(bytes, 10) {
        Some(value) => Ok(value),
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
    let result = (left + right).to_str_radix(10);
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
    let result = (left * right).to_str_radix(10);
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

// These tables live for the process. The loader copies their values into
// interpreter-owned modules without writing to the helper's mapped image.
struct ModuleSlots([PySlot; 6]);
unsafe impl Sync for ModuleSlots {}

// The full non-stable ABI requires the locked CPython 3.16 GIL build.
// The loader checks major/minor and GIL compatibility; the source lock pins
// the exact revision because the loader does not enforce release-level bits.
static ABI_INFO: PyABIInfo = PyABIInfo {
    abiinfo_major_version: 1, abiinfo_minor_version: 0, flags: 2,
    build_version: 0x031000a0, abi_version: 0x031000a0,
};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("decimal slot export requires the supported 64-bit CPython ABI");

const _: () = {
    assert!(std::mem::size_of::<PySlot>() == 16);
    assert!(std::mem::align_of::<PySlot>() == 8);
    assert!(std::mem::offset_of!(PySlot, sl_id) == 0);
    assert!(std::mem::offset_of!(PySlot, sl_flags) == 2);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_1) == 4);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_2) == 8);
    assert!(std::mem::size_of::<PyABIInfo>() == 12);
    assert!(std::mem::align_of::<PyABIInfo>() == 4);
};

const fn data_slot(id: u32, value: *mut c_void) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: PySlot_INTPTR as u16,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: value } }
}

// The interpreter retains the method definitions after copying the slots.
// Their immutable process-lifetime array requires explicit static ownership.
const fn static_data_slot(id: u32, value: *mut c_void) -> PySlot {
    let mut slot = data_slot(id, value);
    slot.sl_flags |= PySlot_STATIC as u16;
    slot
}

// The binding generator omits the function-like compatibility macro for
// this slot. A native header oracle verifies its identifier and integer value.
const MODULE_MULTIPLE_INTERPRETERS_SLOT: u16 = 86;

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    data_slot(Py_mod_abi, &ABI_INFO as *const PyABIInfo as *mut c_void),
    data_slot(Py_mod_name, c"_decimal_rs".as_ptr() as *mut c_void),
    data_slot(Py_mod_doc, c"Exact integer coefficient arithmetic for decimal.Decimal.".as_ptr() as *mut c_void),
    static_data_slot(Py_mod_methods, METHODS.as_ptr() as *mut c_void),
    PySlot { sl_id: MODULE_MULTIPLE_INTERPRETERS_SLOT, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_uint64: 2 } },
    PySlot { sl_id: 0, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: ptr::null_mut() } },
]);

#[unsafe(no_mangle)]
pub extern "C" fn PyModExport__decimal_rs() -> *mut PySlot {
    MODULE_SLOTS.0.as_ptr() as *mut PySlot
}
