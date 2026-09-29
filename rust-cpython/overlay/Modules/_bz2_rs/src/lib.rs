use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::{Cell, UnsafeCell};
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

// libbz2-rs-sys requests its block-sort tables through `alloc_zeroed`: about
// 7 MiB per level-9 compressor and 3.6 MiB per decompressor. The system
// allocator satisfies that from its recycled-block cache with a full memset,
// which makes every page resident even when the input needs a fraction of
// them. The reference C libbzip2 uses plain `malloc` and writes every table
// entry before reading it, and this port mirrors that code path for path, so
// inside a codec call large "zeroed" requests are served without the memset.
// The relaxed mode is scoped to the calling thread and to the codec calls
// below; every other allocation keeps the exact `GlobalAlloc` contract.
struct CodecAllocator;

const UNZEROED_THRESHOLD: usize = 128 * 1024;

thread_local! {
    static IN_CODEC: Cell<bool> = const { Cell::new(false) };
}

struct CodecScope(bool);

impl CodecScope {
    fn enter() -> Self {
        Self(IN_CODEC.replace(true))
    }
}

impl Drop for CodecScope {
    fn drop(&mut self) {
        IN_CODEC.set(self.0);
    }
}

unsafe impl GlobalAlloc for CodecAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        unsafe { System.alloc(layout) }
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        if layout.size() >= UNZEROED_THRESHOLD && IN_CODEC.get() {
            unsafe { System.alloc(layout) }
        } else {
            unsafe { System.alloc_zeroed(layout) }
        }
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) }
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        unsafe { System.realloc(pointer, layout, new_size) }
    }
}

#[global_allocator]
static ALLOCATOR: CodecAllocator = CodecAllocator;

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
    fn PyBytes_AsString(object: *mut PyObject) -> *mut c_char;
    fn _PyBytes_Resize(object: *mut *mut PyObject, size: Py_ssize_t) -> c_int;
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
        let status = {
            let _codec = CodecScope::enter();
            state.codec.compress(chunk, &mut buffer, action)?
        };
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
    let _codec = CodecScope::enter();
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
    let _codec = CodecScope::enter();
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

/// A `bytes` object filled in place. Decompressed output is written straight
/// into it and trimmed at the end, so no second copy of the result exists.
struct OutBytes {
    object: *mut PyObject,
    len: usize,
    cap: usize,
}

impl OutBytes {
    /// On failure the Python exception is already set.
    unsafe fn with_capacity(cap: usize) -> Option<Self> {
        let object = unsafe { PyBytes_FromStringAndSize(ptr::null(), cap as Py_ssize_t) };
        (!object.is_null()).then_some(Self { object, len: 0, cap })
    }

    unsafe fn spare(&mut self) -> &mut [u8] {
        unsafe {
            let start = PyBytes_AsString(self.object).cast::<u8>().add(self.len);
            slice::from_raw_parts_mut(start, self.cap - self.len)
        }
    }

    unsafe fn resize(&mut self, cap: usize) -> bool {
        let mut object = self.object;
        if unsafe { _PyBytes_Resize(&mut object, cap as Py_ssize_t) } != 0 {
            // The object was released and the exception set.
            self.object = ptr::null_mut();
            return false;
        }
        self.object = object;
        self.cap = cap;
        true
    }

    unsafe fn finish(mut self) -> *mut PyObject {
        if self.cap != self.len && !unsafe { self.resize(self.len) } {
            return ptr::null_mut();
        }
        std::mem::replace(&mut self.object, ptr::null_mut())
    }
}

impl Drop for OutBytes {
    fn drop(&mut self) {
        if !self.object.is_null() {
            unsafe { cpython_sys::Py_DecRef(self.object) };
        }
    }
}

enum Failure {
    Codec(Error),
    /// A Python exception is already set.
    Python,
}

impl From<Error> for Failure {
    fn from(error: Error) -> Self {
        Self::Codec(error)
    }
}

const SCRATCH: usize = 1024;

unsafe fn decompress_into(
    state: &mut DecompressorState,
    fresh: &[u8],
    max_length: Py_ssize_t,
) -> Result<*mut PyObject, Failure> {
    if max_length == 0 {
        state.input.extend_from_slice(fresh);
        state.needs_input = state.input.is_empty();
        return Ok(unsafe { PyBytes_FromStringAndSize(ptr::null(), 0) });
    }
    let limit = if max_length < 0 {
        isize::MAX as usize
    } else {
        max_length as usize
    };
    // Input left over from earlier calls is kept ahead of the new bytes;
    // otherwise the caller's buffer is decoded in place without a copy.
    let owned = !state.input.is_empty();
    if owned {
        state.input.extend_from_slice(fresh);
    }
    let DecompressorState { codec, input, .. } = &mut *state;
    let source: &[u8] = if owned { input } else { fresh };
    let mut output = unsafe { OutBytes::with_capacity(limit.min(OUTPUT_CHUNK)) }
        .ok_or(Failure::Python)?;
    let mut consumed_total = 0usize;
    let mut eof = false;
    loop {
        let remaining = limit - output.len;
        if remaining == 0 {
            break;
        }
        let rest = &source[consumed_total..];
        let chunk = &rest[..rest.len().min(u32::MAX as usize)];
        let before_in = codec.total_in();
        let before_out = codec.total_out();
        let spare = output.cap - output.len;
        let (status, room, scratch);
        let mut probe = [0u8; SCRATCH];
        if spare > 0 {
            room = spare.min(remaining);
            status = {
                let _codec = CodecScope::enter();
                codec.decompress(chunk, &mut unsafe { output.spare() }[..room])?
            };
            scratch = 0;
        } else {
            // The buffer is exactly full: probe with a small scratch area so
            // the buffer only grows when more output really exists.
            room = SCRATCH.min(remaining);
            status = {
                let _codec = CodecScope::enter();
                codec.decompress(chunk, &mut probe[..room])?
            };
            scratch = (codec.total_out() - before_out) as usize;
        }
        let consumed = (codec.total_in() - before_in) as usize;
        let produced = (codec.total_out() - before_out) as usize;
        consumed_total += consumed;
        if scratch > 0 {
            let grown = output.cap.saturating_mul(2).min(limit).max(output.len + scratch);
            if !unsafe { output.resize(grown) } {
                return Err(Failure::Python);
            }
            let room = unsafe { output.spare() };
            room[..scratch].copy_from_slice(&probe[..scratch]);
        }
        output.len += produced;

        if status == Status::StreamEnd {
            eof = true;
            break;
        }
        if max_length >= 0 && output.len == limit {
            break;
        }
        if consumed == 0 && produced == 0 {
            break;
        }
        if consumed_total == source.len() && produced < room {
            break;
        }
    }
    if owned {
        input.drain(..consumed_total);
    } else {
        input.extend_from_slice(&fresh[consumed_total..]);
    }
    if eof {
        state.eof = true;
        state.unused_data.extend_from_slice(&state.input);
        state.input.clear();
        state.needs_input = false;
    } else {
        state.needs_input = state.input.is_empty();
    }
    let result = unsafe { output.finish() };
    if result.is_null() {
        return Err(Failure::Python);
    }
    Ok(result)
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
    match unsafe { decompress_into(state, buffer.bytes(), max_length) } {
        Ok(result) => result,
        Err(failure) => {
            state.failed = true;
            state.needs_input = false;
            state.input.clear();
            match failure {
                Failure::Codec(error) => codec_error(error),
                Failure::Python => ptr::null_mut(),
            }
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
