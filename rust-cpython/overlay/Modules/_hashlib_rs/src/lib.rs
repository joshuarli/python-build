use std::ffi::{c_char, c_int, c_long, c_void};
use std::mem::{MaybeUninit, size_of};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_NOARGS, METH_O, METH_VARARGS, PyBytes_FromStringAndSize, PyErr_NoMemory,
    PyErr_SetString, PyExc_ValueError, PyGetSetDef, PyLong_FromLong, PyMethodDef,
    PyMethodDefFuncPointer, PyModule_AddObject, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyModuleDef_Slot, PyObject, PyObject_Free, PyObject_GetAttrString, PyObject_GetBuffer,
    PyObject_HashNotImplemented, PyObject_Type, PyType_FromSpec, PyType_GenericAlloc, PyTypeObject, PyType_Slot,
    PyType_Spec, PyUnicode_FromFormat, PyUnicode_FromStringAndSize, Py_NewRef,
    Py_DecRef, Py_buffer, Py_ssize_t, Py_tp_dealloc, Py_tp_getset, Py_tp_hash,
    Py_tp_methods, Py_tp_repr, Py_TPFLAGS_DEFAULT, Py_TPFLAGS_DISALLOW_INSTANTIATION,
    Py_TPFLAGS_IMMUTABLETYPE,
};
use cpython_sys::_Py_NoneStruct;
use sha2::Digest;
use md5::Md5;
use sha1::Sha1;
use sha2::{Sha224, Sha256, Sha384, Sha512};

const PYBUF_SIMPLE: c_int = 0;
const HEX: &[u8; 16] = b"0123456789abcdef";

#[derive(Clone)]
enum HashState {
    Md5(Md5),
    Sha1(Sha1),
    Sha224(Sha224),
    Sha256(Sha256),
    Sha384(Sha384),
    Sha512(Sha512),
}

impl HashState {
    fn new(name: &str) -> Option<Self> {
        match name {
            "md5" => Some(Self::Md5(Md5::new())),
            "sha1" => Some(Self::Sha1(Sha1::new())),
            "sha224" => Some(Self::Sha224(Sha224::new())),
            "sha256" => Some(Self::Sha256(Sha256::new())),
            "sha384" => Some(Self::Sha384(Sha384::new())),
            "sha512" => Some(Self::Sha512(Sha512::new())),
            _ => None,
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Self::Md5(hash) => hash.update(data),
            Self::Sha1(hash) => hash.update(data),
            Self::Sha224(hash) => hash.update(data),
            Self::Sha256(hash) => hash.update(data),
            Self::Sha384(hash) => hash.update(data),
            Self::Sha512(hash) => hash.update(data),
        }
    }

    fn digest(&self) -> Vec<u8> {
        match self {
            Self::Md5(hash) => hash.clone().finalize().to_vec(),
            Self::Sha1(hash) => hash.clone().finalize().to_vec(),
            Self::Sha224(hash) => hash.clone().finalize().to_vec(),
            Self::Sha256(hash) => hash.clone().finalize().to_vec(),
            Self::Sha384(hash) => hash.clone().finalize().to_vec(),
            Self::Sha512(hash) => hash.clone().finalize().to_vec(),
        }
    }

    fn name(&self) -> &'static str {
        match self {
            Self::Md5(_) => "md5",
            Self::Sha1(_) => "sha1",
            Self::Sha224(_) => "sha224",
            Self::Sha256(_) => "sha256",
            Self::Sha384(_) => "sha384",
            Self::Sha512(_) => "sha512",
        }
    }

    fn block_size(&self) -> c_int {
        match self {
            Self::Md5(_) | Self::Sha1(_) | Self::Sha224(_) | Self::Sha256(_) => 64,
            Self::Sha384(_) | Self::Sha512(_) => 128,
        }
    }

    fn digest_size(&self) -> c_int {
        match self {
            Self::Md5(_) => 16,
            Self::Sha1(_) => 20,
            Self::Sha224(_) => 28,
            Self::Sha256(_) => 32,
            Self::Sha384(_) => 48,
            Self::Sha512(_) => 64,
        }
    }
}

#[repr(C)]
struct HashObject {
    base: PyObject,
    state: *mut HashState,
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return None;
        }
        Some(Self {
            view: unsafe { view.assume_init() },
        })
    }

    fn bytes(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { cpython_sys::PyBuffer_Release(&mut self.view) }
    }
}

unsafe fn tuple_item(args: *mut PyObject, index: Py_ssize_t, count: Py_ssize_t) -> Option<*mut PyObject> {
    if unsafe { cpython_sys::PyTuple_Size(args) } != count {
        unsafe { PyErr_SetString(cpython_sys::PyExc_TypeError, c"invalid number of arguments".as_ptr()) };
        return None;
    }
    let item = unsafe { cpython_sys::PyTuple_GetItem(args, index) };
    if item.is_null() { None } else { Some(item) }
}

unsafe fn read_name(object: *mut PyObject) -> Option<String> {
    let mut size: Py_ssize_t = 0;
    let name = unsafe { cpython_sys::PyUnicode_AsUTF8AndSize(object, &mut size) };
    if name.is_null() {
        return None;
    }
    if size < 0 {
        unsafe { PyErr_SetString(PyExc_ValueError, c"digest name has a negative encoded length".as_ptr()) };
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(name.cast::<u8>(), size as usize) };
    Some(String::from_utf8_lossy(bytes).into_owned())
}

unsafe fn object_state(object: *mut PyObject) -> Option<*mut HashState> {
    let hash_object = unsafe { &mut *object.cast::<HashObject>() };
    if hash_object.state.is_null() {
        unsafe { PyErr_SetString(PyExc_ValueError, c"hash object has no state".as_ptr()) };
        return None;
    }
    Some(hash_object.state)
}

fn allocate_hash(type_object: *mut PyTypeObject, state: HashState) -> *mut PyObject {
    let object = unsafe { PyType_GenericAlloc(type_object, 0) };
    if object.is_null() {
        return ptr::null_mut();
    }
    let pointer = Box::into_raw(Box::new(state));
    unsafe { (*object.cast::<HashObject>()).state = pointer };
    object
}

fn return_bytes(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

unsafe extern "C" fn new_hash(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    let Some(name_object) = (unsafe { tuple_item(args, 0, 2) }) else {
        return ptr::null_mut();
    };
    let Some(data_object) = (unsafe { tuple_item(args, 1, 2) }) else {
        return ptr::null_mut();
    };
    let Some(name) = (unsafe { read_name(name_object) }) else {
        return ptr::null_mut();
    };
    let Some(mut state) = HashState::new(&name) else {
        unsafe { PyErr_SetString(PyExc_ValueError, c"unsupported hash algorithm".as_ptr()) };
        return ptr::null_mut();
    };
    let Some(data) = (unsafe { BorrowedBuffer::from_object(data_object) }) else {
        return ptr::null_mut();
    };
    state.update(data.bytes());

    let type_object = unsafe { PyObject_GetAttrString(_module, c"HASH".as_ptr()) };
    if type_object.is_null() {
        return ptr::null_mut();
    }
    let result = allocate_hash(type_object.cast::<PyTypeObject>(), state);
    unsafe { Py_DecRef(type_object) };
    result
}

unsafe extern "C" fn update(object: *mut PyObject, data_object: *mut PyObject) -> *mut PyObject {
    let Some(data) = (unsafe { BorrowedBuffer::from_object(data_object) }) else {
        return ptr::null_mut();
    };
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { &mut *state }.update(data.bytes());
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn copy_hash(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let type_object = unsafe { PyObject_Type(object) };
    if type_object.is_null() {
        return ptr::null_mut();
    }
    let result = allocate_hash(type_object.cast::<PyTypeObject>(), unsafe { &*state }.clone());
    unsafe { Py_DecRef(type_object) };
    result
}

unsafe extern "C" fn digest(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    return_bytes(&unsafe { &*state }.digest())
}

unsafe extern "C" fn hexdigest(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let digest = unsafe { &*state }.digest();
    let mut output = Vec::with_capacity(digest.len() * 2);
    for byte in digest {
        output.push(HEX[(byte >> 4) as usize]);
        output.push(HEX[(byte & 0x0f) as usize]);
    }
    if output.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(output.as_ptr().cast::<c_char>(), output.len() as Py_ssize_t) }
}

unsafe extern "C" fn get_name(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let name = unsafe { &*state }.name();
    unsafe { PyUnicode_FromStringAndSize(name.as_ptr().cast::<c_char>(), name.len() as Py_ssize_t) }
}

unsafe extern "C" fn get_digest_size(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { PyLong_FromLong(unsafe { &*state }.digest_size() as c_long) }
}

unsafe extern "C" fn get_block_size(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { PyLong_FromLong(unsafe { &*state }.block_size() as c_long) }
}

unsafe extern "C" fn hash_repr(object: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let name = match unsafe { &*state }.name() {
        "md5" => c"md5".as_ptr(),
        "sha1" => c"sha1".as_ptr(),
        "sha224" => c"sha224".as_ptr(),
        "sha256" => c"sha256".as_ptr(),
        "sha384" => c"sha384".as_ptr(),
        _ => c"sha512".as_ptr(),
    };
    unsafe { PyUnicode_FromFormat(c"<%s HASH object @ %p>".as_ptr(), name, object.cast::<c_void>()) }
}

unsafe extern "C" fn dealloc(object: *mut PyObject) {
    let hash_object = unsafe { &mut *object.cast::<HashObject>() };
    if !hash_object.state.is_null() {
        unsafe { drop(Box::from_raw(hash_object.state)) };
        hash_object.state = ptr::null_mut();
    }
    unsafe { PyObject_Free(object.cast::<c_void>()) };
}

unsafe extern "C" fn unhashable(object: *mut PyObject) -> isize {
    unsafe { PyObject_HashNotImplemented(object) }
}

pub static HASH_METHODS: [PyMethodDef; 5] = [
    PyMethodDef {
        ml_name: c"update".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: update },
        ml_flags: METH_O,
        ml_doc: c"Update the digest with bytes-like data.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"copy".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: copy_hash },
        ml_flags: METH_NOARGS,
        ml_doc: c"Return a copy of the hash object.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"digest".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: digest },
        ml_flags: METH_NOARGS,
        ml_doc: c"Return the digest of the data passed to update().".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"hexdigest".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: hexdigest },
        ml_flags: METH_NOARGS,
        ml_doc: c"Return the hexadecimal digest of the data passed to update().".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

struct HashGetSet([PyGetSetDef; 4]);

// CPython reads these immutable C definition tables after module initialization.
unsafe impl Sync for HashGetSet {}

static HASH_GETSET: HashGetSet = HashGetSet([
    PyGetSetDef {
        name: c"name".as_ptr() as *mut c_char,
        get: Some(get_name),
        set: None,
        doc: c"Canonical name of this digest algorithm.".as_ptr() as *mut c_char,
        closure: ptr::null_mut(),
    },
    PyGetSetDef {
        name: c"digest_size".as_ptr() as *mut c_char,
        get: Some(get_digest_size),
        set: None,
        doc: c"Size of the digest in bytes.".as_ptr() as *mut c_char,
        closure: ptr::null_mut(),
    },
    PyGetSetDef {
        name: c"block_size".as_ptr() as *mut c_char,
        get: Some(get_block_size),
        set: None,
        doc: c"Internal block size of the hash algorithm in bytes.".as_ptr() as *mut c_char,
        closure: ptr::null_mut(),
    },
    PyGetSetDef {
        name: ptr::null_mut(),
        get: None,
        set: None,
        doc: ptr::null_mut(),
        closure: ptr::null_mut(),
    },
]);

struct HashTypeSlots([PyType_Slot; 6]);

unsafe impl Sync for HashTypeSlots {}

static HASH_TYPE_SLOTS: HashTypeSlots = HashTypeSlots([
    PyType_Slot { slot: Py_tp_dealloc as c_int, pfunc: dealloc as *const () as *mut c_void },
    PyType_Slot { slot: Py_tp_getset as c_int, pfunc: HASH_GETSET.0.as_ptr() as *mut c_void },
    PyType_Slot { slot: Py_tp_hash as c_int, pfunc: unhashable as *const () as *mut c_void },
    PyType_Slot { slot: Py_tp_methods as c_int, pfunc: HASH_METHODS.as_ptr() as *mut c_void },
    PyType_Slot { slot: Py_tp_repr as c_int, pfunc: hash_repr as *const () as *mut c_void },
    PyType_Slot { slot: 0, pfunc: ptr::null_mut() },
]);

struct HashTypeSpec(PyType_Spec);

unsafe impl Sync for HashTypeSpec {}

static HASH_TYPE_SPEC: HashTypeSpec = HashTypeSpec(PyType_Spec {
    name: c"_hashlib_rs.HASH".as_ptr(),
    basicsize: size_of::<HashObject>() as c_int,
    itemsize: 0,
    flags: Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION | Py_TPFLAGS_IMMUTABLETYPE,
    slots: HASH_TYPE_SLOTS.0.as_ptr() as *mut PyType_Slot,
});

unsafe extern "C" fn clear_module(_module: *mut PyObject) -> c_int {
    0
}

unsafe extern "C" fn free_module(_module: *mut c_void) {}

unsafe extern "C" fn exec_module(module: *mut PyObject) -> c_int {
    let hash_type = unsafe { PyType_FromSpec(&HASH_TYPE_SPEC.0 as *const PyType_Spec as *mut PyType_Spec) };
    if hash_type.is_null() {
        return -1;
    }
    if unsafe { PyModule_AddObject(module, c"HASH".as_ptr(), hash_type) } != 0 {
        unsafe { Py_DecRef(hash_type) };
        return -1;
    }
    0
}

struct HashModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for HashModuleSlots {}

// These are the generated slot IDs in the pinned CPython 3.16 fork.
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_MULTIPLE_INTERPRETERS_SUPPORTED: *mut c_void = 1 as *mut c_void;

static MODULE_SLOTS: HashModuleSlots = HashModuleSlots([
    PyModuleDef_Slot { slot: PY_MOD_EXEC, value: exec_module as *const () as *mut c_void },
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_MULTIPLE_INTERPRETERS_SUPPORTED,
    },
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

pub struct ModuleDef {
    ffi: std::cell::UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"new".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: new_hash },
        ml_flags: METH_VARARGS,
        ml_doc: c"Create a Rust-backed fixed-output digest object.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static MODULE: ModuleDef = ModuleDef {
    ffi: std::cell::UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_hashlib_rs".as_ptr() as *mut c_char,
        m_doc: c"RustCrypto digest implementations used by hashlib.".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(clear_module),
        m_free: Some(free_module),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__hashlib_rs() -> *mut PyObject {
    MODULE.init()
}
