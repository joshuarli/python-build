use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use bzip2::{Action, Compress, Compression, Decompress, Error, Status};
use cpython_sys::METH_FASTCALL;
use cpython_sys::METH_NOARGS;
use cpython_sys::METH_O;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_OSError;
use cpython_sys::PyExc_RuntimeError;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsInt;
use cpython_sys::PyLong_AsSsize_t;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;

const PYBUF_SIMPLE: c_int = 0;
const OUTPUT_CHUNK: usize = 16 * 1024;
const CAPSULE_COMPRESSOR: &std::ffi::CStr = c"_bz2_rs.Compressor";
const CAPSULE_DECOMPRESSOR: &std::ffi::CStr = c"_bz2_rs.Decompressor";

unsafe extern "C" {
    fn PyCapsule_New(
        pointer: *mut c_void,
        name: *const c_char,
        destructor: Option<unsafe extern "C" fn(*mut PyObject)>,
    ) -> *mut PyObject;
    fn PyCapsule_GetPointer(capsule: *mut PyObject, name: *const c_char) -> *mut c_void;
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return Err(());
        }
        Ok(Self {
            view: unsafe { view.assume_init() },
        })
    }

    fn bytes(&self) -> &[u8] {
        if self.view.len == 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

struct CompressorState {
    codec: Compress,
    finished: bool,
}

struct DecompressorState {
    codec: Decompress,
    input: Vec<u8>,
    unused_data: Vec<u8>,
    eof: bool,
    failed: bool,
    needs_input: bool,
}

fn set_type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

fn set_value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
    ptr::null_mut()
}

fn set_os_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_OSError, message.as_ptr()) };
    ptr::null_mut()
}

fn capsule<T>(state: T, name: &'static std::ffi::CStr,
              destructor: unsafe extern "C" fn(*mut PyObject)) -> *mut PyObject {
    let pointer = Box::into_raw(Box::new(state)).cast::<c_void>();
    let result = unsafe { PyCapsule_New(pointer, name.as_ptr(), Some(destructor)) };
    if result.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<T>())) };
    }
    result
}

unsafe fn capsule_state<'a, T>(
    object: *mut PyObject,
    name: &'static std::ffi::CStr,
) -> Option<&'a mut T> {
    let pointer = unsafe { PyCapsule_GetPointer(object, name.as_ptr()) };
    if pointer.is_null() {
        None
    } else {
        Some(unsafe { &mut *pointer.cast::<T>() })
    }
}

unsafe extern "C" fn drop_compressor(object: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(object, CAPSULE_COMPRESSOR.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<CompressorState>())) };
    }
}

unsafe extern "C" fn drop_decompressor(object: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(object, CAPSULE_DECOMPRESSOR.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<DecompressorState>())) };
    }
}

fn codec_error(error: Error) -> *mut PyObject {
    match error {
        Error::Data | Error::DataMagic => set_os_error(c"Invalid data stream"),
        Error::Param => set_value_error(c"Internal error - invalid parameters passed to libbzip2"),
        Error::Sequence => {
            unsafe {
                PyErr_SetString(
                    PyExc_RuntimeError,
                    c"Internal error - Invalid sequence of commands sent to libbzip2".as_ptr(),
                )
            };
            ptr::null_mut()
        }
    }
}

unsafe fn new_bytes(data: &[u8]) -> *mut PyObject {
    if data.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(data.as_ptr().cast::<c_char>(), data.len() as Py_ssize_t)
    }
}

fn compress_into(
    state: &mut CompressorState,
    input: &[u8],
    action: Action,
) -> Result<Vec<u8>, Error> {
    let mut output = Vec::new();
    let mut input_offset = 0usize;
    loop {
        let end = input.len().min(input_offset.saturating_add(u32::MAX as usize));
        let chunk = &input[input_offset..end];
        let before_in = state.codec.total_in();
        let before_out = state.codec.total_out();
        let mut buffer = [0u8; OUTPUT_CHUNK];
        let status = state.codec.compress(chunk, &mut buffer, action)?;
        let consumed = (state.codec.total_in() - before_in) as usize;
        let produced = (state.codec.total_out() - before_out) as usize;
        input_offset += consumed;
        output.extend_from_slice(&buffer[..produced]);

        if action == Action::Run && input_offset == input.len() {
            break;
        }
        if action == Action::Finish && status == Status::StreamEnd {
            state.finished = true;
            break;
        }
        if consumed == 0 && produced == 0 {
            return Err(Error::Sequence);
        }
    }
    Ok(output)
}

unsafe extern "C" fn compressor_new(_module: *mut PyObject, level: *mut PyObject) -> *mut PyObject {
    let level = unsafe { PyLong_AsInt(level) };
    if level == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if !(1..=9).contains(&level) {
        return set_value_error(c"compresslevel must be between 1 and 9");
    }
    capsule(
        CompressorState {
            codec: Compress::new(Compression::new(level as u32), 30),
            finished: false,
        },
        CAPSULE_COMPRESSOR,
        drop_compressor,
    )
}

unsafe extern "C" fn compressor_compress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return set_type_error(c"compressor_compress() takes exactly two arguments");
    }
    let Some(state) = (unsafe { capsule_state::<CompressorState>(*args, CAPSULE_COMPRESSOR) }) else {
        return ptr::null_mut();
    };
    if state.finished {
        return set_value_error(c"Compressor has been flushed");
    }
    let buffer = match unsafe { BorrowedBuffer::from_object(*args.add(1)) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let result = match compress_into(state, buffer.bytes(), Action::Run) {
        Ok(result) => result,
        Err(error) => return codec_error(error),
    };
    unsafe { new_bytes(&result) }
}

unsafe extern "C" fn compressor_finish(_module: *mut PyObject, capsule: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { capsule_state::<CompressorState>(capsule, CAPSULE_COMPRESSOR) }) else {
        return ptr::null_mut();
    };
    if state.finished {
        return set_value_error(c"Compressor has been flushed");
    }
    let result = match compress_into(state, &[], Action::Finish) {
        Ok(result) => result,
        Err(error) => return codec_error(error),
    };
    unsafe { new_bytes(&result) }
}

unsafe extern "C" fn decompressor_new(_module: *mut PyObject, _ignored: *mut PyObject) -> *mut PyObject {
    capsule(
        DecompressorState {
            codec: Decompress::new(false),
            input: Vec::new(),
            unused_data: Vec::new(),
            eof: false,
            failed: false,
            needs_input: true,
        },
        CAPSULE_DECOMPRESSOR,
        drop_decompressor,
    )
}

fn decompress_into(
    state: &mut DecompressorState,
    max_length: Py_ssize_t,
) -> Result<Vec<u8>, Error> {
    let mut output = Vec::new();
    if max_length == 0 {
        state.needs_input = state.input.is_empty();
        return Ok(output);
    }
    let limit = if max_length < 0 {
        usize::MAX
    } else {
        max_length as usize
    };
    let mut consumed_total = 0usize;
    loop {
        let input = &state.input[consumed_total..];
        let chunk_end = input.len().min(u32::MAX as usize);
        let chunk = &input[..chunk_end];
        let room = OUTPUT_CHUNK.min(limit.saturating_sub(output.len()));
        if room == 0 {
            break;
        }
        let before_in = state.codec.total_in();
        let before_out = state.codec.total_out();
        let mut buffer = vec![0u8; room];
        let status = state.codec.decompress(chunk, &mut buffer)?;
        let consumed = (state.codec.total_in() - before_in) as usize;
        let produced = (state.codec.total_out() - before_out) as usize;
        consumed_total += consumed;
        output.extend_from_slice(&buffer[..produced]);

        if status == Status::StreamEnd {
            state.eof = true;
            break;
        }
        if max_length >= 0 && output.len() == limit {
            break;
        }
        if consumed == 0 && produced == 0 {
            break;
        }
        if consumed_total == state.input.len() && produced < room {
            break;
        }
    }
    state.input.drain(..consumed_total);
    if state.eof {
        state.unused_data.extend_from_slice(&state.input);
        state.input.clear();
        state.needs_input = false;
    } else {
        state.needs_input = state.input.is_empty();
    }
    Ok(output)
}

unsafe extern "C" fn decompressor_decompress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return set_type_error(c"decompressor_decompress() takes exactly three arguments");
    }
    let Some(state) = (unsafe { capsule_state::<DecompressorState>(*args, CAPSULE_DECOMPRESSOR) }) else {
        return ptr::null_mut();
    };
    if state.eof {
        return set_value_error(c"End of stream already reached");
    }
    if state.failed {
        return set_value_error(c"Decompressor is unusable after a previous error");
    }
    let max_length = unsafe { PyLong_AsSsize_t(*args.add(2)) };
    if max_length == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let buffer = match unsafe { BorrowedBuffer::from_object(*args.add(1)) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    state.input.extend_from_slice(buffer.bytes());
    match decompress_into(state, max_length) {
        Ok(result) => unsafe { new_bytes(&result) },
        Err(error) => {
            state.failed = true;
            state.needs_input = false;
            state.input.clear();
            codec_error(error)
        }
    }
}

unsafe extern "C" fn decompressor_state(_module: *mut PyObject, capsule: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { capsule_state::<DecompressorState>(capsule, CAPSULE_DECOMPRESSOR) }) else {
        return ptr::null_mut();
    };
    if state.unused_data.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let eof = unsafe { PyBool_FromLong(state.eof as c_long) };
    let needs_input = unsafe { PyBool_FromLong(state.needs_input as c_long) };
    let unused = unsafe {
        PyBytes_FromStringAndSize(
            state.unused_data.as_ptr().cast::<c_char>(),
            state.unused_data.len() as Py_ssize_t,
        )
    };
    if eof.is_null() || needs_input.is_null() || unused.is_null() {
        unsafe { cpython_sys::Py_DecRef(result) };
        if !eof.is_null() {
            unsafe { cpython_sys::Py_DecRef(eof) };
        }
        if !needs_input.is_null() {
            unsafe { cpython_sys::Py_DecRef(needs_input) };
        }
        if !unused.is_null() {
            unsafe { cpython_sys::Py_DecRef(unused) };
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 0, eof) } != 0
        || unsafe { PyTuple_SetItem(result, 1, needs_input) } != 0
        || unsafe { PyTuple_SetItem(result, 2, unused) } != 0
    {
        unsafe { cpython_sys::Py_DecRef(result) };
        return ptr::null_mut();
    }
    result
}

pub extern "C" fn _bz2_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _bz2_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _BZ2_RS_MODULE_METHODS: [PyMethodDef; 7] = {
    [
        PyMethodDef {
            ml_name: c"compressor_new".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: compressor_new },
            ml_flags: METH_O,
            ml_doc: c"Create a Rust bzip2 compression stream.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"compressor_compress".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_compress },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Compress the next input block.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"compressor_finish".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: compressor_finish },
            ml_flags: METH_O,
            ml_doc: c"Finish a Rust bzip2 compression stream.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"decompressor_new".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: decompressor_new },
            ml_flags: METH_NOARGS,
            ml_doc: c"Create a Rust bzip2 decompression stream.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"decompressor_decompress".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_decompress },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Decompress the next input block.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"decompressor_state".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: decompressor_state },
            ml_flags: METH_O,
            ml_doc: c"Return the decompressor's public state.".as_ptr() as *mut c_char,
        },
        PyMethodDef::zeroed(),
    ]
};

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

// These are the generated slot IDs in the pinned CPython 3.16 fork.
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

// Codec state is capsule-owned, so interpreters do not share mutable state.
static _BZ2_RS_MODULE_SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: PY_MOD_EXEC,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

pub static _BZ2_RS_MODULE: ModuleDef = {
    ModuleDef {
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_bz2_rs".as_ptr() as *mut _,
            m_doc: c"Rust bzip2 streaming codec.".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_BZ2_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: _BZ2_RS_MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
            m_traverse: None,
            m_clear: Some(_bz2_rs_clear),
            m_free: Some(_bz2_rs_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__bz2_rs() -> *mut PyObject {
    _BZ2_RS_MODULE.init_multi_phase()
}
