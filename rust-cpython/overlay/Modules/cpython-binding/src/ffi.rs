#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_long, c_uint, c_ulong, c_void};

pub type Py_ssize_t = isize;

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
pub struct PyObject {
    pub ob_refcnt: Py_ssize_t,
    pub ob_type: *mut PyTypeObject,
}

pub type PyCFunction = unsafe extern "C" fn(*mut PyObject, *mut PyObject) -> *mut PyObject;
pub type PyCFunctionFast =
    unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject;
pub type visitproc = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int;

#[repr(C)]
pub union PyMethodDefFuncPointer {
    pub PyCFunction: PyCFunction,
    pub PyCFunctionFast: PyCFunctionFast,
    pub void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    pub ml_name: *const c_char,
    pub ml_meth: PyMethodDefFuncPointer,
    pub ml_flags: c_int,
    pub ml_doc: *const c_char,
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
    pub m_traverse: Option<unsafe extern "C" fn(*mut PyObject, visitproc, *mut c_void) -> c_int>,
    pub m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    pub m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

#[repr(C)]
pub struct Py_buffer {
    pub buf: *mut c_void,
    pub obj: *mut PyObject,
    pub len: Py_ssize_t,
    pub itemsize: Py_ssize_t,
    pub readonly: c_int,
    pub ndim: c_int,
    pub format: *mut c_char,
    pub shape: *mut Py_ssize_t,
    pub strides: *mut Py_ssize_t,
    pub suboffsets: *mut Py_ssize_t,
    pub internal: *mut c_void,
}

pub type getter = unsafe extern "C" fn(*mut PyObject, *mut c_void) -> *mut PyObject;
pub type setter = unsafe extern "C" fn(*mut PyObject, *mut PyObject, *mut c_void) -> c_int;

#[repr(C)]
pub struct PyGetSetDef {
    pub name: *const c_char,
    pub get: Option<getter>,
    pub set: Option<setter>,
    pub doc: *const c_char,
    pub closure: *mut c_void,
}

unsafe impl Sync for PyGetSetDef {}

#[repr(C)]
pub struct PyType_Slot {
    pub slot: c_int,
    pub pfunc: *mut c_void,
}

unsafe impl Sync for PyType_Slot {}

#[repr(C)]
pub struct PyType_Spec {
    pub name: *const c_char,
    pub basicsize: c_int,
    pub itemsize: c_int,
    pub flags: c_uint,
    pub slots: *mut PyType_Slot,
}

unsafe impl Sync for PyType_Spec {}

#[repr(C)]
pub struct PyBytesWriter {
    _opaque: [u8; 0],
}

#[repr(C)]
pub struct PyThreadState {
    _opaque: [u8; 0],
}

pub type PyCapsule_Destructor = Option<unsafe extern "C" fn(*mut PyObject)>;

pub const METH_VARARGS: c_int = 0x0001;
pub const METH_O: c_int = 0x0008;
pub const METH_NOARGS: c_int = 0x0004;
pub const METH_FASTCALL: c_int = 0x0080;

pub const PyBUF_SIMPLE: c_int = 0;

pub const Py_mod_exec: c_int = 85;
pub const Py_tp_dealloc: c_int = 52;
pub const Py_tp_getset: c_int = 73;
pub const Py_tp_hash: c_int = 59;
pub const Py_tp_methods: c_int = 64;
pub const Py_tp_repr: c_int = 66;

pub const Py_TPFLAGS_DEFAULT: c_uint = 0;
pub const Py_TPFLAGS_DISALLOW_INSTANTIATION: c_uint = 1 << 7;
pub const Py_TPFLAGS_IMMUTABLETYPE: c_uint = 1 << 8;
pub const Py_TPFLAGS_UNICODE_SUBCLASS: c_ulong = 1 << 28;

pub const Py_mod_multiple_interpreters: c_int = 86;
pub const Py_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2usize as *mut c_void;

/// `_Py_STATIC_IMMORTAL_INITIAL_REFCNT` of the 64-bit GIL-enabled build:
/// `(3 << 30) | ((_Py_STATICALLY_ALLOCATED_FLAG | _Py_IMMORTAL_FLAGS) << 48)`.
pub const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);

unsafe extern "C" {
    pub static mut _Py_NoneStruct: PyObject;
    pub static mut PyExc_IndexError: *mut PyObject;
    pub static mut PyExc_MemoryError: *mut PyObject;
    pub static mut PyExc_OSError: *mut PyObject;
    pub static mut PyExc_OverflowError: *mut PyObject;
    pub static mut PyExc_RuntimeError: *mut PyObject;
    pub static mut PyExc_TypeError: *mut PyObject;
    pub static mut PyExc_ValueError: *mut PyObject;
    pub static mut PyExc_ZeroDivisionError: *mut PyObject;
    pub static mut PyCFunction_Type: PyTypeObject;
    pub static mut PyBool_Type: PyTypeObject;
    pub static mut PyByteArray_Type: PyTypeObject;
    pub static mut PyBytes_Type: PyTypeObject;
    pub static mut PyDict_Type: PyTypeObject;
    pub static mut PyFloat_Type: PyTypeObject;
    pub static mut PyList_Type: PyTypeObject;
    pub static mut PyLong_Type: PyTypeObject;
    pub static mut PyTuple_Type: PyTypeObject;
    pub static mut PyUnicode_Type: PyTypeObject;

    pub fn Py_DecRef(object: *mut PyObject);
    pub fn Py_GetConstant(constant_id: u32) -> *mut PyObject;
    pub fn Py_IncRef(object: *mut PyObject);
    pub fn Py_NewRef(object: *mut PyObject) -> *mut PyObject;

    pub fn PyBool_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyBuffer_Release(view: *mut Py_buffer);
    pub fn PyBytesWriter_Create(size: Py_ssize_t) -> *mut PyBytesWriter;
    pub fn PyBytesWriter_Discard(writer: *mut PyBytesWriter);
    pub fn PyBytesWriter_FinishWithSize(
        writer: *mut PyBytesWriter,
        size: Py_ssize_t,
    ) -> *mut PyObject;
    pub fn PyBytesWriter_GetData(writer: *mut PyBytesWriter) -> *mut c_void;
    pub fn PyBytesWriter_GetSize(writer: *mut PyBytesWriter) -> Py_ssize_t;
    pub fn PyBytesWriter_Grow(writer: *mut PyBytesWriter, size: Py_ssize_t) -> c_int;
    pub fn PyBytesWriter_WriteBytes(
        writer: *mut PyBytesWriter,
        bytes: *const c_void,
        size: Py_ssize_t,
    ) -> c_int;
    pub fn PyBytes_AsString(object: *mut PyObject) -> *mut c_char;
    pub fn PyBytes_AsStringAndSize(
        object: *mut PyObject,
        data: *mut *mut c_char,
        length: *mut Py_ssize_t,
    ) -> c_int;
    pub fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyBytes_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyErr_Clear();
    pub fn PyErr_NoMemory() -> *mut PyObject;
    pub fn PyErr_Occurred() -> *mut PyObject;
    pub fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    pub fn PyIter_Next(iterator: *mut PyObject) -> *mut PyObject;
    pub fn PyCapsule_GetPointer(capsule: *mut PyObject, name: *const c_char) -> *mut c_void;
    pub fn PyCapsule_IsValid(capsule: *mut PyObject, name: *const c_char) -> c_int;
    pub fn PyCapsule_New(
        pointer: *mut c_void,
        name: *const c_char,
        destructor: PyCapsule_Destructor,
    ) -> *mut PyObject;
    pub fn PyCFunction_GetFunction(object: *mut PyObject) -> Option<PyCFunction>;
    pub fn PyCFunction_GetSelf(object: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_Contains(dict: *mut PyObject, key: *mut PyObject) -> c_int;
    pub fn PyDict_GetItemString(dict: *mut PyObject, key: *const c_char) -> *mut PyObject;
    pub fn PyDict_GetItemWithError(dict: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    pub fn PyDict_New() -> *mut PyObject;
    pub fn PyDict_SetItem(dict: *mut PyObject, key: *mut PyObject, value: *mut PyObject)
    -> c_int;
    pub fn PyErr_CheckSignals() -> c_int;
    pub fn PyErr_SetFromErrno(exception: *mut PyObject) -> *mut PyObject;
    pub fn PyEval_RestoreThread(state: *mut PyThreadState);
    pub fn PyEval_SaveThread() -> *mut PyThreadState;
    pub fn PyLong_AsInt(object: *mut PyObject) -> c_int;
    pub fn PyLong_AsLong(object: *mut PyObject) -> c_long;
    pub fn PyLong_AsNativeBytes(
        object: *mut PyObject,
        buffer: *mut c_void,
        size: Py_ssize_t,
        flags: c_int,
    ) -> Py_ssize_t;
    pub fn PyLong_AsUnsignedLongMask(object: *mut PyObject) -> c_ulong;
    pub fn PyLong_FromNativeBytes(buffer: *const c_void, size: usize, flags: c_int)
    -> *mut PyObject;
    pub fn PyLong_FromUnsignedLong(value: c_ulong) -> *mut PyObject;
    pub fn PyModule_GetDict(module: *mut PyObject) -> *mut PyObject;
    pub fn PyNumber_Index(object: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_CallNoArgs(callable: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetAttr(object: *mut PyObject, name: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_Vectorcall(
        callable: *mut PyObject,
        args: *const *mut PyObject,
        nargsf: usize,
        kwnames: *mut PyObject,
    ) -> *mut PyObject;
    pub fn PyType_GetFlags(class: *mut PyTypeObject) -> c_ulong;
    pub fn PyUnicode_Concat(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    pub fn PyUnicode_InternFromString(text: *const c_char) -> *mut PyObject;
    pub fn PyUnicode_New(size: Py_ssize_t, maxchar: u32) -> *mut PyObject;
    pub fn PyUnicode_ReadChar(object: *mut PyObject, index: Py_ssize_t) -> u32;
    pub fn PyUnicode_WriteChar(object: *mut PyObject, index: Py_ssize_t, character: u32) -> c_int;
    pub fn _PyBytes_Resize(object: *mut *mut PyObject, size: Py_ssize_t) -> c_int;
    pub fn PyErr_SetObject(exception: *mut PyObject, value: *mut PyObject);
    pub fn PyLong_FromLong(value: c_long) -> *mut PyObject;
    pub fn PyModule_AddObject(
        module: *mut PyObject,
        name: *const c_char,
        value: *mut PyObject,
    ) -> c_int;
    pub fn PyObject_Free(pointer: *mut c_void);
    pub fn PyObject_GetAttrString(object: *mut PyObject, name: *const c_char) -> *mut PyObject;
    pub fn PyObject_HashNotImplemented(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyType_FromSpec(spec: *mut PyType_Spec) -> *mut PyObject;
    pub fn PyType_GenericAlloc(type_object: *mut PyTypeObject, nitems: Py_ssize_t)
    -> *mut PyObject;
    pub fn PyUnicode_FromFormat(format: *const c_char, ...) -> *mut PyObject;
    pub fn PyList_Append(list: *mut PyObject, item: *mut PyObject) -> c_int;
    pub fn PyList_GetItem(list: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyList_SetItem(list: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    pub fn PyList_Size(list: *mut PyObject) -> Py_ssize_t;
    pub fn PyFloat_AsDouble(object: *mut PyObject) -> f64;
    pub fn PyFloat_FromDouble(value: f64) -> *mut PyObject;
    pub fn PyLong_AsSsize_t(object: *mut PyObject) -> Py_ssize_t;
    pub fn PyLong_AsLongLong(object: *mut PyObject) -> i64;
    pub fn PyLong_AsUnsignedLongLong(object: *mut PyObject) -> u64;
    pub fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    pub fn PyLong_FromSsize_t(value: Py_ssize_t) -> *mut PyObject;
    pub fn PyLong_FromUnsignedLongLong(value: u64) -> *mut PyObject;
    pub fn PyMem_Free(pointer: *mut c_void);
    pub fn PyMem_Malloc(size: usize) -> *mut c_void;
    pub fn PyMem_Realloc(pointer: *mut c_void, size: usize) -> *mut c_void;
    pub fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    pub fn PyNumber_Subtract(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_CallMethod(
        object: *mut PyObject,
        name: *const c_char,
        format: *const c_char,
        ...
    ) -> *mut PyObject;
    pub fn PyObject_CallOneArg(callable: *mut PyObject, arg: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetBuffer(object: *mut PyObject, view: *mut Py_buffer, flags: c_int)
    -> c_int;
    pub fn PyObject_GetItem(object: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_GetIter(object: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_IsTrue(object: *mut PyObject) -> c_int;
    pub fn PyObject_Type(object: *mut PyObject) -> *mut PyObject;
    pub fn PyObject_RichCompareBool(left: *mut PyObject, right: *mut PyObject, op: c_int) -> c_int;
    pub fn PyObject_SetItem(object: *mut PyObject, key: *mut PyObject, value: *mut PyObject)
    -> c_int;
    pub fn PyObject_Size(object: *mut PyObject) -> Py_ssize_t;
    pub fn PySequence_Contains(sequence: *mut PyObject, value: *mut PyObject) -> c_int;
    pub fn PyTuple_GetItem(tuple: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    pub fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject)
    -> c_int;
    pub fn PyTuple_Size(tuple: *mut PyObject) -> Py_ssize_t;
    pub fn PyUnicode_AsUCS4(
        object: *mut PyObject,
        target: *mut u32,
        targetsize: Py_ssize_t,
        copy_null: c_int,
    ) -> *mut u32;
    pub fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t)
    -> *const c_char;
    pub fn PyUnicode_DecodeUTF8(
        data: *const c_char,
        size: Py_ssize_t,
        errors: *const c_char,
    ) -> *mut PyObject;
    pub fn PyUnicode_FromKindAndData(
        kind: c_int,
        buffer: *const c_void,
        size: Py_ssize_t,
    ) -> *mut PyObject;
    pub fn PyUnicode_FromStringAndSize(text: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    pub fn PyUnicode_GetLength(object: *mut PyObject) -> Py_ssize_t;
}
