use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_TypeError,
    PyExc_ValueError, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize,
    PyIter_Next, PyList_Append, PyList_AsTuple, PyList_New, PyLong_AsSsize_t,
    PyLong_FromLong, PyLong_FromUnsignedLongLong, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    PyModuleDef_Slot, PyObject, PyObject_Length, PyTuple_New, PyTuple_SetItem,
    Py_IncRef, Py_ssize_t,
};

struct Owned(*mut PyObject);

impl Owned {
    fn new(object: *mut PyObject) -> Option<Self> {
        (!object.is_null()).then_some(Self(object))
    }

    fn into_raw(mut self) -> *mut PyObject {
        let object = self.0;
        self.0 = ptr::null_mut();
        object
    }
}

impl Drop for Owned {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

fn bytes(data: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(data.as_ptr().cast(), data.len() as Py_ssize_t) }
}

fn frame_parts(parts: &[&[u8]], payload: *mut PyObject) -> *mut PyObject {
    let Some(tuple) = Owned::new(unsafe { PyTuple_New((parts.len() + 1) as Py_ssize_t) }) else {
        return ptr::null_mut();
    };
    for (index, part) in parts.iter().enumerate() {
        let item = bytes(part);
        if item.is_null() {
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple.0, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(item) };
            return ptr::null_mut();
        }
    }
    unsafe { Py_IncRef(payload) };
    if unsafe { PyTuple_SetItem(tuple.0, parts.len() as Py_ssize_t, payload) } != 0 {
        unsafe { Py_DecRef(payload) };
        return ptr::null_mut();
    }
    tuple.into_raw()
}

unsafe extern "C" fn frame(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"frame expects one payload".as_ptr()) };
        return ptr::null_mut();
    }
    let payload = unsafe { *args };
    let size = unsafe { PyObject_Length(payload) };
    if size < 0 {
        return ptr::null_mut();
    }
    if size > i32::MAX as Py_ssize_t {
        return frame_parts(&[&(-1_i32).to_be_bytes(), &(size as u64).to_be_bytes()], payload);
    }
    let header = (size as i32).to_be_bytes();
    if size > 16_384 {
        return frame_parts(&[&header], payload);
    }

    // The small payload and its header travel in one write. Empty payloads
    // also take this route so the pipe never receives a separate empty write.
    let mut view = std::mem::MaybeUninit::<cpython_sys::Py_buffer>::uninit();
    if unsafe { cpython_sys::PyObject_GetBuffer(payload, view.as_mut_ptr(), 0) } != 0 {
        return ptr::null_mut();
    }
    let mut view = unsafe { view.assume_init() };
    let payload_bytes = if view.len == 0 {
        &[]
    } else {
        unsafe { slice::from_raw_parts(view.buf.cast::<u8>(), view.len as usize) }
    };
    let mut joined = Vec::with_capacity(4 + payload_bytes.len());
    joined.extend_from_slice(&header);
    joined.extend_from_slice(payload_bytes);
    unsafe { cpython_sys::PyBuffer_Release(&mut view) };
    bytes(&joined)
}

unsafe extern "C" fn frame_length(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"frame_length expects one header".as_ptr()) };
        return ptr::null_mut();
    }
    let mut data = ptr::null_mut();
    let mut length = 0;
    if unsafe { PyBytes_AsStringAndSize(*args, &mut data, &mut length) } != 0 {
        return ptr::null_mut();
    }
    let data = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    match data {
        [a, b, c, d] => unsafe { PyLong_FromLong(i32::from_be_bytes([*a, *b, *c, *d]).into()) },
        [a, b, c, d, e, f, g, h] => unsafe {
            PyLong_FromUnsignedLongLong(u64::from_be_bytes([*a, *b, *c, *d, *e, *f, *g, *h]))
        },
        _ => {
            unsafe { PyErr_SetString(PyExc_ValueError, c"invalid frame header length".as_ptr()) };
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn take_chunk(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"take_chunk expects iterator and size".as_ptr()) };
        return ptr::null_mut();
    }
    let size = unsafe { PyLong_AsSsize_t(*args.add(1)) };
    if size == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if size < 0 {
        unsafe { PyErr_SetString(PyExc_ValueError, c"Stop argument for islice() must be None or an integer: 0 <= x <= sys.maxsize.".as_ptr()) };
        return ptr::null_mut();
    }
    let Some(items) = Owned::new(unsafe { PyList_New(0) }) else {
        return ptr::null_mut();
    };
    for _ in 0..size {
        let item = unsafe { PyIter_Next(*args) };
        if item.is_null() {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            break;
        }
        let appended = unsafe { PyList_Append(items.0, item) };
        unsafe { Py_DecRef(item) };
        if appended != 0 {
            return ptr::null_mut();
        }
    }
    unsafe { PyList_AsTuple(items.0) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);
unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);
unsafe impl Sync for ModuleSlots {}

static METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"frame".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: frame },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Build a multiprocessing wire frame.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"frame_length".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: frame_length },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decode a multiprocessing wire header.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"take_chunk".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: take_chunk },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Collect one pool task batch from an iterator.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

static SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot { slot: 85, value: module_exec as *const () as *mut c_void },
    PyModuleDef_Slot { slot: 86, value: 2 as *mut c_void },
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_multiprocessing_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust wire framing and pool batching.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__multiprocessing_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
