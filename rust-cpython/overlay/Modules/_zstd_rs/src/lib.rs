//! Rust-backed Zstandard operations used by the public compression wrapper.

use std::cell::UnsafeCell;
use std::ffi::{CStr, CString, c_char, c_int, c_void};
use std::io;
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_buffer;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyCapsule_GetPointer;
use cpython_sys::PyCapsule_New;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_OverflowError;
use cpython_sys::PyExc_RuntimeError;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_PyBytes_Resize;

use zstd::zstd_safe::zstd_sys::ZSTD_EndDirective;
use zstd::zstd_safe::{
    CCtx, CParameter, DCtx, InBuffer, OutBuffer, ResetDirective, WriteBuf, compress_bound,
    find_frame_compressed_size, get_error_name, get_frame_content_size,
};

const PYBUF_SIMPLE: c_int = 0;
const MIN_OUTPUT_SIZE: usize = 16 * 1024;
const MAX_SIZE_HINT: u64 = 256 * 1024 * 1024;
const ENCODER_CAPSULE_NAME: &CStr = c"_zstd_rs.encoder";
const DECODER_CAPSULE_NAME: &CStr = c"_zstd_rs.decoder";

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        let result = unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) };
        if result != 0 {
            return Err(());
        }
        Ok(Self {
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
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

/// A `bytes` object that zstd writes into directly. The object is resized to
/// the written length on success, so no intermediate copy is made.
struct PyBuf {
    object: *mut PyObject,
    cap: usize,
    len: usize,
}

impl PyBuf {
    fn new(cap: usize) -> io::Result<Self> {
        let cap = cap.max(1);
        if cap > Py_ssize_t::MAX as usize {
            return Err(io::Error::new(io::ErrorKind::OutOfMemory, "output too large"));
        }
        let object =
            unsafe { PyBytes_FromStringAndSize(ptr::null(), cap as Py_ssize_t) };
        if object.is_null() {
            unsafe { PyErr_Clear() };
            return Err(io::Error::from(io::ErrorKind::OutOfMemory));
        }
        Ok(Self { object, cap, len: 0 })
    }

    fn resize(&mut self, cap: usize) -> io::Result<()> {
        if cap > Py_ssize_t::MAX as usize {
            return Err(io::Error::new(io::ErrorKind::OutOfMemory, "output too large"));
        }
        if unsafe { _PyBytes_Resize(&mut self.object, cap as Py_ssize_t) } != 0 {
            // The object was released by the failed resize.
            unsafe { PyErr_Clear() };
            self.cap = 0;
            self.len = 0;
            return Err(io::Error::from(io::ErrorKind::OutOfMemory));
        }
        self.cap = cap;
        Ok(())
    }

    fn is_full(&self) -> bool {
        self.len == self.cap
    }

    fn grow(&mut self) -> io::Result<()> {
        let cap = self
            .cap
            .checked_mul(2)
            .ok_or_else(|| io::Error::from(io::ErrorKind::OutOfMemory))?;
        self.resize(cap)
    }

    fn into_object(mut self) -> io::Result<*mut PyObject> {
        if self.len == 0 {
            return Ok(unsafe { PyBytes_FromStringAndSize(c"".as_ptr(), 0) });
        }
        if self.len != self.cap {
            self.resize(self.len)?;
        }
        let object = self.object;
        self.object = ptr::null_mut();
        Ok(object)
    }
}

impl Drop for PyBuf {
    fn drop(&mut self) {
        if !self.object.is_null() {
            unsafe { Py_DecRef(self.object) };
        }
    }
}

unsafe impl WriteBuf for PyBuf {
    fn as_slice(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(PyBytes_AsString(self.object).cast::<u8>(), self.len) }
    }

    fn capacity(&self) -> usize {
        self.cap
    }

    fn as_mut_ptr(&mut self) -> *mut u8 {
        unsafe { PyBytes_AsString(self.object).cast::<u8>() }
    }

    unsafe fn filled_until(&mut self, n: usize) {
        self.len = n;
    }
}

fn zstd_error(code: usize) -> io::Error {
    io::Error::other(get_error_name(code))
}

struct StreamCompressor {
    cctx: CCtx<'static>,
    frame_has_input: bool,
}

impl StreamCompressor {
    fn new(level: i32) -> io::Result<Self> {
        let mut cctx = CCtx::create();
        cctx.set_parameter(CParameter::CompressionLevel(level))
            .map_err(zstd_error)?;
        Ok(Self {
            cctx,
            frame_has_input: false,
        })
    }

    fn compress(&mut self, data: &[u8], mode: i32) -> io::Result<*mut PyObject> {
        let directive = match mode {
            0 => ZSTD_EndDirective::ZSTD_e_continue,
            1 => ZSTD_EndDirective::ZSTD_e_flush,
            2 => ZSTD_EndDirective::ZSTD_e_end,
            _ => {
                return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid compression mode"));
            }
        };
        if mode == 2 && !self.frame_has_input {
            self.cctx
                .set_pledged_src_size(Some(data.len() as u64))
                .map_err(zstd_error)?;
        }
        // One call with the frame's directive lets libzstd compress straight
        // into the result without staging the input in the context.
        let mut output = PyBuf::new(compress_bound(data.len()))?;
        drive(&mut self.cctx, data, &mut output, directive)?;
        self.frame_has_input |= !data.is_empty();
        if mode == 2 {
            self.cctx.reset(ResetDirective::SessionOnly).map_err(zstd_error)?;
            self.frame_has_input = false;
        }
        output.into_object()
    }

    fn flush(&mut self, mode: i32) -> io::Result<*mut PyObject> {
        let directive = match mode {
            1 => ZSTD_EndDirective::ZSTD_e_flush,
            2 => ZSTD_EndDirective::ZSTD_e_end,
            _ => return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid flush mode")),
        };
        let mut output = PyBuf::new(MIN_OUTPUT_SIZE)?;
        drive(&mut self.cctx, &[], &mut output, directive)?;
        if mode == 2 {
            self.cctx.reset(ResetDirective::SessionOnly).map_err(zstd_error)?;
            self.frame_has_input = false;
        }
        output.into_object()
    }
}

struct StreamDecompressor {
    dctx: DCtx<'static>,
    frame_started: bool,
    frame_finished: bool,
}

impl StreamDecompressor {
    fn new() -> io::Result<Self> {
        Ok(Self {
            dctx: DCtx::create(),
            frame_started: false,
            frame_finished: false,
        })
    }

    fn decompress(&mut self, data: &[u8]) -> io::Result<*mut PyObject> {
        if data.is_empty() {
            return Ok(unsafe { PyBytes_FromStringAndSize(c"".as_ptr(), 0) });
        }
        if self.frame_finished {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "frame already finished"));
        }

        // The first chunk of a frame usually carries the decompressed size.
        // When it also holds the whole frame, decode it in one pass straight
        // into an exactly sized result, without the context's window buffer.
        let mut hint = None;
        if !self.frame_started {
            self.frame_started = true;
            if let Ok(Some(size)) = get_frame_content_size(data) {
                if size <= MAX_SIZE_HINT {
                    hint = Some(size as usize);
                    if let Ok(frame_len) = find_frame_compressed_size(data) {
                        let mut output = PyBuf::new(size as usize)?;
                        self.dctx
                            .decompress(&mut output, &data[..frame_len])
                            .map_err(zstd_error)?;
                        self.frame_finished = true;
                        return output.into_object();
                    }
                }
            }
        }

        let mut output =
            PyBuf::new(hint.unwrap_or(data.len().saturating_mul(4)).max(MIN_OUTPUT_SIZE))?;
        let mut input = InBuffer::around(data);
        loop {
            let before = (input.pos(), output.len);
            let mut out = OutBuffer::around_pos(&mut output, before.1);
            let remaining = self
                .dctx
                .decompress_stream(&mut out, &mut input)
                .map_err(zstd_error)?;
            drop(out);

            if remaining == 0 {
                self.frame_finished = true;
                break;
            }
            if output.is_full() {
                output.grow()?;
                continue;
            }
            if input.pos() == data.len() {
                break;
            }
            if before == (input.pos(), output.len) {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "decoder made no progress"));
            }
        }
        output.into_object()
    }
}

fn drive(
    cctx: &mut CCtx<'static>,
    data: &[u8],
    output: &mut PyBuf,
    directive: ZSTD_EndDirective,
) -> io::Result<()> {
    let mut input = InBuffer::around(data);
    loop {
        let before = (input.pos(), output.len);
        let mut out = OutBuffer::around_pos(output, before.1);
        let remaining = cctx
            .compress_stream2(&mut out, &mut input, directive)
            .map_err(zstd_error)?;
        drop(out);

        let done = if directive == ZSTD_EndDirective::ZSTD_e_continue {
            input.pos() == data.len() && !output.is_full()
        } else {
            remaining == 0
        };
        if done {
            return Ok(());
        }
        if output.is_full() {
            output.grow()?;
        } else if before == (input.pos(), output.len) {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "encoder made no progress"));
        }
    }
}

fn runtime_error(error: impl std::fmt::Display) -> *mut PyObject {
    let message = CString::new(error.to_string())
        .unwrap_or_else(|_| CString::new("Zstandard operation failed").unwrap());
    unsafe { PyErr_SetString(PyExc_RuntimeError, message.as_ptr()) };
    ptr::null_mut()
}

fn type_error(message: &'static CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

unsafe fn read_integer(object: *mut PyObject) -> Option<i32> {
    let value = unsafe { PyLong_AsLong(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    match i32::try_from(value) {
        Ok(value) => Some(value),
        Err(_) => {
            unsafe {
                PyErr_SetString(
                    PyExc_OverflowError,
                    c"Python int too large to convert to Rust i32".as_ptr(),
                )
            };
            None
        }
    }
}

unsafe fn capsule_ref<'a, T>(capsule: *mut PyObject, name: &CStr) -> Option<&'a mut T> {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, name.as_ptr()) };
    if pointer.is_null() {
        return None;
    }
    Some(unsafe { &mut *pointer.cast::<T>() })
}

unsafe extern "C" fn drop_encoder(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, ENCODER_CAPSULE_NAME.as_ptr()) };
    if !pointer.is_null() {
        drop(unsafe { Box::from_raw(pointer.cast::<StreamCompressor>()) });
    }
}

unsafe extern "C" fn drop_decoder(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, DECODER_CAPSULE_NAME.as_ptr()) };
    if !pointer.is_null() {
        drop(unsafe { Box::from_raw(pointer.cast::<StreamDecompressor>()) });
    }
}

unsafe extern "C" fn encoder_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"encoder_new() takes one argument");
    }
    let Some(level) = (unsafe { read_integer(*args) }) else {
        return ptr::null_mut();
    };
    let encoder = match StreamCompressor::new(level) {
        Ok(encoder) => Box::into_raw(Box::new(encoder)).cast::<c_void>(),
        Err(error) => return runtime_error(error),
    };
    let capsule = unsafe {
        PyCapsule_New(encoder, ENCODER_CAPSULE_NAME.as_ptr(), Some(drop_encoder))
    };
    if capsule.is_null() {
        drop(unsafe { Box::from_raw(encoder.cast::<StreamCompressor>()) });
    }
    capsule
}

unsafe extern "C" fn encoder_compress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return type_error(c"encoder_compress() takes three arguments");
    }
    let Some(encoder) = (unsafe { capsule_ref::<StreamCompressor>(*args, ENCODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    let buffer = match unsafe { BorrowedBuffer::from_object(*args.add(1)) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let Some(mode) = (unsafe { read_integer(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    match encoder.compress(buffer.bytes(), mode) {
        Ok(output) => output,
        Err(error) => runtime_error(error),
    }
}

unsafe extern "C" fn encoder_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"encoder_flush() takes two arguments");
    }
    let Some(encoder) = (unsafe { capsule_ref::<StreamCompressor>(*args, ENCODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    let Some(mode) = (unsafe { read_integer(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    match encoder.flush(mode) {
        Ok(output) => output,
        Err(error) => runtime_error(error),
    }
}

unsafe extern "C" fn decoder_new(
    _module: *mut PyObject,
    _args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 0 {
        return type_error(c"decoder_new() takes no arguments");
    }
    let decoder = match StreamDecompressor::new() {
        Ok(decoder) => Box::into_raw(Box::new(decoder)).cast::<c_void>(),
        Err(error) => return runtime_error(error),
    };
    let capsule = unsafe {
        PyCapsule_New(decoder, DECODER_CAPSULE_NAME.as_ptr(), Some(drop_decoder))
    };
    if capsule.is_null() {
        drop(unsafe { Box::from_raw(decoder.cast::<StreamDecompressor>()) });
    }
    capsule
}

unsafe extern "C" fn decoder_decompress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"decoder_decompress() takes two arguments");
    }
    let Some(decoder) = (unsafe { capsule_ref::<StreamDecompressor>(*args, DECODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    let buffer = match unsafe { BorrowedBuffer::from_object(*args.add(1)) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    match decoder.decompress(buffer.bytes()) {
        Ok(output) => output,
        Err(error) => runtime_error(error),
    }
}

static METHODS: [PyMethodDef; 6] = [
    PyMethodDef {
        ml_name: c"encoder_new".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: encoder_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a Zstandard stream encoder".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"encoder_compress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: encoder_compress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compress bytes with an incremental Zstandard encoder".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"encoder_flush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: encoder_flush },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Flush an incremental Zstandard encoder".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decoder_new".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decoder_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a Zstandard stream decoder".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decoder_decompress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decoder_decompress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decompress bytes with an incremental Zstandard decoder".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__zstd_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_zstd_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust Zstandard codec support".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: None,
        m_free: None,
    }),
};
