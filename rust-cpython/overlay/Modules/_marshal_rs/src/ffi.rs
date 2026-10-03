//! Only the CPython declarations used by this codec. Objects with fields
//! accessed below use the 64-bit, little-endian, GIL-enabled release layout.
//! Type objects, methods and long writers are only passed by pointer.
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_long, c_longlong, c_void};
use core::ptr;

#[cfg(not(all(target_pointer_width = "64", target_endian = "little")))]
compile_error!("marshal object layouts require a 64-bit little-endian CPython build");

pub type Py_ssize_t = isize;

#[repr(C)]
pub struct PyTypeObject { _opaque: [u8; 0] }
#[repr(C)]
pub struct PyLongWriter { _opaque: [u8; 0] }
#[repr(C)]
pub struct PyMethodDef { _opaque: [u8; 0] }

#[repr(C)]
pub union ObjectRefcount {
    pub ob_refcnt_full: i64,
}
#[repr(C)]
pub struct _object {
    pub __bindgen_anon_1: ObjectRefcount,
    pub ob_type: *mut PyTypeObject,
}
#[repr(transparent)]
pub struct PyObject(UnsafeCell<_object>);
#[repr(C)]
pub struct PyVarObject {
    pub ob_base: PyObject,
    pub ob_size: Py_ssize_t,
}
#[repr(C)]
pub struct PyFloatObject {
    pub ob_base: PyObject,
    pub ob_fval: f64,
}
#[repr(C)]
pub struct PyListObject {
    pub ob_base: PyVarObject,
    pub ob_item: *mut *mut PyObject,
    pub allocated: Py_ssize_t,
}
#[repr(C)]
pub struct PyTupleObject {
    pub ob_base: PyVarObject,
    pub ob_hash: Py_ssize_t,
    pub ob_item: [*mut PyObject; 1],
}
#[repr(C)]
pub struct LongValue {
    pub lv_tag: usize,
    pub ob_digit: [u32; 1],
}
#[repr(C)]
pub struct _longobject {
    pub ob_base: PyObject,
    pub long_value: LongValue,
}
#[repr(C)]
pub struct PyLongLayout {
    pub bits_per_digit: u8,
    pub digit_size: u8,
    pub digits_order: i8,
    pub digit_endianness: i8,
}
#[repr(C)]
pub struct PyLongExport {
    pub value: i64,
    pub negative: u8,
    pub ndigits: Py_ssize_t,
    pub digits: *const c_void,
    pub _reserved: usize,
}

type Visit = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int;
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
#[repr(C)]
pub struct PyModuleDef {
    pub m_base: PyModuleDef_Base,
    pub m_name: *const c_char,
    pub m_doc: *const c_char,
    pub m_size: Py_ssize_t,
    pub m_methods: *mut PyMethodDef,
    pub m_slots: *mut PyModuleDef_Slot,
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, Option<Visit>, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

// A module definition has the same immortal static head as CPython's macro.
const STATIC_IMMORTAL_REFCNT: i64 = (3_i64 << 30) | (5_i64 << 48);
pub const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject(UnsafeCell::new(_object {
        __bindgen_anon_1: ObjectRefcount { ob_refcnt_full: STATIC_IMMORTAL_REFCNT },
        ob_type: ptr::null_mut(),
    })),
    m_init: None,
    m_index: 0,
    m_copy: ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
#[cfg_attr(target_os = "linux", link(name = "c"))]
unsafe extern "C" {
    pub static mut PyBool_Type: PyTypeObject;
    pub static mut PyBytes_Type: PyTypeObject;
    pub static mut PyComplex_Type: PyTypeObject;
    pub static mut PyCode_Type: PyTypeObject;
    pub static mut PyDict_Type: PyTypeObject;
    pub static mut PyFloat_Type: PyTypeObject;
    pub static mut PyFrozenSet_Type: PyTypeObject;
    pub static mut PyList_Type: PyTypeObject;
    pub static mut PyLong_Type: PyTypeObject;
    pub static mut PySet_Type: PyTypeObject;
    pub static mut PyTuple_Type: PyTypeObject;
    pub static mut PyUnicode_Type: PyTypeObject;
    pub static mut _Py_NoneStruct: PyObject;

    pub fn PyBool_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyBytes_AsString(value: *mut PyObject) -> *mut c_char;
    pub fn PyBytes_Size(value: *mut PyObject) -> Py_ssize_t;
    pub fn _PyBytes_Resize(value: *mut *mut PyObject, size: Py_ssize_t) -> c_int;
    pub fn PyCapsule_New(data: *mut c_void, name: *const c_char,
        destructor: Option<unsafe extern "C" fn(*mut PyObject)>) -> *mut PyObject;
    pub fn PyComplex_FromDoubles(real: f64, imag: f64) -> *mut PyObject;
    pub fn PyComplex_ImagAsDouble(value: *mut PyObject) -> f64;
    pub fn PyComplex_RealAsDouble(value: *mut PyObject) -> f64;
    pub fn Py_DecRef(value: *mut PyObject);
    pub fn Py_IncRef(value: *mut PyObject);
    pub fn PyDict_New() -> *mut PyObject;
    pub fn PyDict_Next(value: *mut PyObject, position: *mut Py_ssize_t,
        key: *mut *mut PyObject, item: *mut *mut PyObject) -> c_int;
    pub fn PyDict_SetItem(value: *mut PyObject, key: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PyErr_Clear();
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyFloat_FromDouble(value: f64) -> *mut PyObject;
    pub fn PyFrozenSet_New(value: *mut PyObject) -> *mut PyObject;
    pub fn PyIter_Next(value: *mut PyObject) -> *mut PyObject;
    pub fn PyList_Append(value: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PyList_GetItem(value: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_SetItem(value: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    pub fn PyList_Size(value: *mut PyObject) -> Py_ssize_t;
    pub fn PyList_Sort(value: *mut PyObject) -> c_int;
    pub fn PyLong_AsLongLongAndOverflow(value: *mut PyObject, overflow: *mut c_int) -> c_longlong;
    pub fn PyLong_Export(value: *mut PyObject, export: *mut PyLongExport) -> c_int;
    pub fn PyLong_FreeExport(export: *mut PyLongExport);
    pub fn PyLong_FromLongLong(value: c_longlong) -> *mut PyObject;
    pub fn PyLong_GetNativeLayout() -> *const PyLongLayout;
    pub fn PyLongWriter_Create(negative: c_int, size: Py_ssize_t,
        digits: *mut *mut c_void) -> *mut PyLongWriter;
    pub fn PyLongWriter_Discard(writer: *mut PyLongWriter);
    pub fn PyLongWriter_Finish(writer: *mut PyLongWriter) -> *mut PyObject;
    pub fn PyMem_Calloc(count: usize, size: usize) -> *mut c_void;
    pub fn PyMem_Free(value: *mut c_void);
    pub fn PyMem_Realloc(value: *mut c_void, size: usize) -> *mut c_void;
    pub fn PyModule_Add(module: *mut PyObject, name: *const c_char, value: *mut PyObject) -> c_int;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyObject_GetIter(value: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_IsTrue(value: *mut PyObject) -> c_int;
    pub fn PySet_Add(value: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PySet_New(value: *mut PyObject) -> *mut PyObject;
    pub fn PyTuple_GetItem(value: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_SetItem(value: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    pub fn PyUnicode_AsEncodedString(value: *mut PyObject, encoding: *const c_char,
        errors: *const c_char) -> *mut PyObject;
    pub fn PyUnicode_DecodeUTF8(data: *const c_char, size: Py_ssize_t,
        errors: *const c_char) -> *mut PyObject;
    pub fn PyUnicode_InternInPlace(value: *mut *mut PyObject);
    #[cfg(not(feature = "static-module"))]
    fn abort() -> !;
}

#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

// Layout assertions cover every locally described value and accessed field.
const _: () = {
    assert!(core::mem::size_of::<c_long>() == 8);
    assert!(core::mem::size_of::<c_longlong>() == 8);
    assert!(core::mem::size_of::<Py_ssize_t>() == 8);
    assert!(core::mem::size_of::<_object>() == 16);
    assert!(core::mem::align_of::<_object>() == 8);
    assert!(core::mem::offset_of!(_object, __bindgen_anon_1) == 0);
    assert!(core::mem::offset_of!(_object, ob_type) == 8);
    assert!(core::mem::size_of::<PyObject>() == 16);
    assert!(core::mem::align_of::<PyObject>() == 8);
    assert!(core::mem::size_of::<PyVarObject>() == 24);
    assert!(core::mem::align_of::<PyVarObject>() == 8);
    assert!(core::mem::offset_of!(PyVarObject, ob_base) == 0);
    assert!(core::mem::offset_of!(PyVarObject, ob_size) == 16);
    assert!(core::mem::size_of::<PyFloatObject>() == 24);
    assert!(core::mem::align_of::<PyFloatObject>() == 8);
    assert!(core::mem::offset_of!(PyFloatObject, ob_base) == 0);
    assert!(core::mem::offset_of!(PyFloatObject, ob_fval) == 16);
    assert!(core::mem::size_of::<PyListObject>() == 40);
    assert!(core::mem::align_of::<PyListObject>() == 8);
    assert!(core::mem::offset_of!(PyListObject, ob_base) == 0);
    assert!(core::mem::offset_of!(PyListObject, ob_item) == 24);
    assert!(core::mem::offset_of!(PyListObject, allocated) == 32);
    assert!(core::mem::size_of::<PyTupleObject>() == 40);
    assert!(core::mem::align_of::<PyTupleObject>() == 8);
    assert!(core::mem::offset_of!(PyTupleObject, ob_base) == 0);
    assert!(core::mem::offset_of!(PyTupleObject, ob_hash) == 24);
    assert!(core::mem::offset_of!(PyTupleObject, ob_item) == 32);
    assert!(core::mem::size_of::<LongValue>() == 16);
    assert!(core::mem::align_of::<LongValue>() == 8);
    assert!(core::mem::offset_of!(LongValue, lv_tag) == 0);
    assert!(core::mem::offset_of!(LongValue, ob_digit) == 8);
    assert!(core::mem::size_of::<_longobject>() == 32);
    assert!(core::mem::align_of::<_longobject>() == 8);
    assert!(core::mem::offset_of!(_longobject, ob_base) == 0);
    assert!(core::mem::offset_of!(_longobject, long_value) == 16);
    assert!(core::mem::size_of::<PyLongLayout>() == 4);
    assert!(core::mem::align_of::<PyLongLayout>() == 1);
    assert!(core::mem::offset_of!(PyLongLayout, bits_per_digit) == 0);
    assert!(core::mem::offset_of!(PyLongLayout, digit_size) == 1);
    assert!(core::mem::offset_of!(PyLongLayout, digits_order) == 2);
    assert!(core::mem::offset_of!(PyLongLayout, digit_endianness) == 3);
    assert!(core::mem::size_of::<PyLongExport>() == 40);
    assert!(core::mem::align_of::<PyLongExport>() == 8);
    assert!(core::mem::offset_of!(PyLongExport, value) == 0);
    assert!(core::mem::offset_of!(PyLongExport, negative) == 8);
    assert!(core::mem::offset_of!(PyLongExport, ndigits) == 16);
    assert!(core::mem::offset_of!(PyLongExport, digits) == 24);
    assert!(core::mem::offset_of!(PyLongExport, _reserved) == 32);
    assert!(core::mem::size_of::<PyModuleDef_Base>() == 40);
    assert!(core::mem::align_of::<PyModuleDef_Base>() == 8);
    assert!(core::mem::offset_of!(PyModuleDef_Base, ob_base) == 0);
    assert!(core::mem::offset_of!(PyModuleDef_Base, m_init) == 16);
    assert!(core::mem::offset_of!(PyModuleDef_Base, m_index) == 24);
    assert!(core::mem::offset_of!(PyModuleDef_Base, m_copy) == 32);
    assert!(core::mem::size_of::<PyModuleDef_Slot>() == 16);
    assert!(core::mem::align_of::<PyModuleDef_Slot>() == 8);
    assert!(core::mem::offset_of!(PyModuleDef_Slot, slot) == 0);
    assert!(core::mem::offset_of!(PyModuleDef_Slot, value) == 8);
    assert!(core::mem::size_of::<PyModuleDef>() == 104);
    assert!(core::mem::align_of::<PyModuleDef>() == 8);
    assert!(core::mem::offset_of!(PyModuleDef, m_base) == 0);
    assert!(core::mem::offset_of!(PyModuleDef, m_name) == 40);
    assert!(core::mem::offset_of!(PyModuleDef, m_doc) == 48);
    assert!(core::mem::offset_of!(PyModuleDef, m_size) == 56);
    assert!(core::mem::offset_of!(PyModuleDef, m_methods) == 64);
    assert!(core::mem::offset_of!(PyModuleDef, m_slots) == 72);
    assert!(core::mem::offset_of!(PyModuleDef, m_traverse) == 80);
    assert!(core::mem::offset_of!(PyModuleDef, m_clear) == 88);
    assert!(core::mem::offset_of!(PyModuleDef, m_free) == 96);
};
