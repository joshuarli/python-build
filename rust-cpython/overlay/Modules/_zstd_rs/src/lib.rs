//! Rust-backed Zstandard operations used by the public compression wrapper.

use std::cell::UnsafeCell;
use std::ffi::{CStr, CString, c_char, c_int, c_long, c_void};
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
use cpython_sys::PyEval_RestoreThread;
use cpython_sys::PyEval_SaveThread;
use cpython_sys::PyExc_MemoryError;
use cpython_sys::PyLong_AsSsize_t;
use cpython_sys::PyLong_AsUnsignedLongLong;
use cpython_sys::Py_IncRef;
use cpython_sys::_Py_NoneStruct;
use cpython_sys::PyLong_FromLong;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
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

/// Run `f` with the GIL released. `f` must not touch any Python object.
fn without_gil<R>(f: impl FnOnce() -> R) -> R {
    let state = unsafe { PyEval_SaveThread() };
    let result = f();
    unsafe { PyEval_RestoreThread(state) };
    result
}

/// A `bytes` object that zstd writes into directly. The object is resized to
/// the written length on success, so no intermediate copy is made. The data
/// pointer is cached so zstd can run without the GIL.
struct PyBuf {
    object: *mut PyObject,
    ptr: *mut u8,
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
        let ptr = unsafe { PyBytes_AsString(object) }.cast::<u8>();
        Ok(Self { object, ptr, cap, len: 0 })
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
        self.ptr = unsafe { PyBytes_AsString(self.object) }.cast::<u8>();
        self.cap = cap;
        Ok(())
    }

    fn is_full(&self) -> bool {
        self.len == self.cap
    }

    /// Double the capacity, but never past `limit`.
    fn grow(&mut self, limit: Option<usize>) -> io::Result<()> {
        let mut cap = self
            .cap
            .checked_mul(2)
            .ok_or_else(|| io::Error::from(io::ErrorKind::OutOfMemory))?;
        if let Some(limit) = limit {
            cap = cap.min(limit);
        }
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
        unsafe { slice::from_raw_parts(self.ptr, self.len) }
    }

    fn capacity(&self) -> usize {
        self.cap
    }

    fn as_mut_ptr(&mut self) -> *mut u8 {
        self.ptr
    }

    unsafe fn filled_until(&mut self, n: usize) {
        self.len = n;
    }
}

fn zstd_error(code: usize) -> io::Error {
    io::Error::other(get_error_name(code))
}

struct StreamCompressor {
    // A completed frame needs no compression history. Keep its configured
    // level while releasing the native workspace until another frame starts.
    cctx: Option<CCtx<'static>>,
    level: i32,
}

impl StreamCompressor {
    fn new(level: i32) -> io::Result<Self> {
        let mut cctx = CCtx::create();
        cctx.set_parameter(CParameter::CompressionLevel(level))
            .map_err(zstd_error)?;
        Ok(Self { cctx: Some(cctx), level })
    }

    fn context(&mut self) -> io::Result<&mut CCtx<'static>> {
        if self.cctx.is_none() {
            let mut cctx = CCtx::try_create()
                .ok_or_else(|| io::Error::from(io::ErrorKind::OutOfMemory))?;
            cctx.set_parameter(CParameter::CompressionLevel(self.level))
                .map_err(zstd_error)?;
            self.cctx = Some(cctx);
        }
        Ok(self.cctx.as_mut().unwrap())
    }

    fn reset(&mut self) {
        if let Some(cctx) = self.cctx.as_mut() {
            let _ = cctx.reset(ResetDirective::SessionOnly);
        }
    }

    fn set_pledged(&mut self, size: u64) -> io::Result<()> {
        let size = if size == u64::MAX { None } else { Some(size) };
        self.context()?.set_pledged_src_size(size).map_err(zstd_error)?;
        Ok(())
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
        // One call with the frame's directive lets libzstd compress straight
        // into the result without staging the input in the context.
        let result = PyBuf::new(compress_bound(data.len()))
            .and_then(|mut output| drive(self.context()?, data, &mut output, directive).map(|()| output));
        self.finish(result, mode)
    }

    fn flush(&mut self, mode: i32) -> io::Result<*mut PyObject> {
        let directive = match mode {
            1 => ZSTD_EndDirective::ZSTD_e_flush,
            2 => ZSTD_EndDirective::ZSTD_e_end,
            _ => return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid flush mode")),
        };
        let result = PyBuf::new(MIN_OUTPUT_SIZE)
            .and_then(|mut output| drive(self.context()?, &[], &mut output, directive).map(|()| output));
        self.finish(result, mode)
    }

    fn finish(&mut self, result: io::Result<PyBuf>, mode: i32) -> io::Result<*mut PyObject> {
        match result {
            Ok(output) => {
                if mode == 2 {
                    // Discard the finished frame before result resizing can
                    // fail, so the next call starts with a fresh session.
                    self.cctx = None;
                }
                output.into_object()
            }
            Err(error) => {
                // A failed call abandons the frame, as the C module does.
                self.reset();
                Err(error)
            }
        }
    }
}

/// What a decompress call reports besides its output.
const FLAG_EOF: c_long = 1;
const FLAG_NEEDS_INPUT: c_long = 2;

struct StreamDecompressor {
    dctx: DCtx<'static>,
    /// Input the last call left unconsumed, from `begin` on.
    pending: Vec<u8>,
    begin: usize,
    frame_started: bool,
    eof: bool,
}

impl StreamDecompressor {
    fn new() -> io::Result<Self> {
        Ok(Self {
            dctx: DCtx::create(),
            pending: Vec::new(),
            begin: 0,
            frame_started: false,
            eof: false,
        })
    }

    fn reset(&mut self) {
        let _ = self.dctx.reset(ResetDirective::SessionOnly);
        self.pending = Vec::new();
        self.begin = 0;
        self.frame_started = false;
        self.eof = false;
    }

    fn unused_data(&self) -> *mut PyObject {
        let tail = &self.pending[self.begin..];
        unsafe { PyBytes_FromStringAndSize(tail.as_ptr().cast(), tail.len() as Py_ssize_t) }
    }

    fn decompress(&mut self, data: &[u8], max_length: i64) -> io::Result<(PyBuf, c_long)> {
        let result = self.decompress_inner(data, usize::try_from(max_length).ok());
        if result.is_err() {
            self.reset();
        }
        result
    }

    fn decompress_inner(
        &mut self,
        data: &[u8],
        limit: Option<usize>,
    ) -> io::Result<(PyBuf, c_long)> {
        if self.eof {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "frame already finished"));
        }
        let use_pending = self.begin < self.pending.len();

        // The first chunk of a frame usually carries the decompressed size.
        // When it also holds the whole frame and the result fits, decode it in
        // one pass straight into an exactly sized result, without the
        // context's window buffer.
        let mut hint = None;
        if !self.frame_started && !use_pending && !data.is_empty() {
            self.frame_started = true;
            if let Ok(Some(size)) = get_frame_content_size(data) {
                if size <= MAX_SIZE_HINT {
                    hint = Some(size as usize);
                    if limit.is_none_or(|limit| size as usize <= limit) {
                        if let Ok(frame_len) = find_frame_compressed_size(data) {
                            let mut output = PyBuf::new(size as usize)?;
                            let ptr = output.ptr;
                            let cap = output.cap;
                            let written = without_gil(|| {
                                // SAFETY: `ptr` addresses `cap` bytes owned by `output`.
                                let dst = unsafe { slice::from_raw_parts_mut(ptr, cap) };
                                self.dctx.decompress(dst, &data[..frame_len])
                            })
                            .map_err(zstd_error)?;
                            output.len = written;
                            self.eof = true;
                            self.pending.clear();
                            self.pending.extend_from_slice(&data[frame_len..]);
                            self.begin = 0;
                            return Ok((output, FLAG_EOF));
                        }
                    }
                }
            }
        }

        if use_pending && !data.is_empty() {
            if self.begin > 0 {
                self.pending.drain(..self.begin);
                self.begin = 0;
            }
            self.pending.extend_from_slice(data);
        }
        let input: &[u8] = if use_pending { &self.pending[self.begin..] } else { data };
        let input_len = input.len();
        let initial = hint.unwrap_or(input_len.saturating_mul(4)).max(MIN_OUTPUT_SIZE);
        let (output, pos, eof) = stream_decode(&mut self.dctx, input, limit, initial)?;

        self.eof = eof;
        let mut flags = if eof { FLAG_EOF } else { 0 };
        if pos == input_len {
            if !eof && limit != Some(output.len) {
                flags |= FLAG_NEEDS_INPUT;
            }
            if use_pending {
                self.pending = Vec::new();
                self.begin = 0;
            }
        } else if use_pending {
            self.begin += pos;
        } else {
            self.pending.clear();
            self.pending.extend_from_slice(&data[pos..]);
            self.begin = 0;
        }
        Ok((output, flags))
    }
}

/// Decode `input` until it is consumed, the frame ends, or `limit` output
/// bytes exist. Returns the output, the input consumed, and whether the frame
/// ended.
fn stream_decode(
    dctx: &mut DCtx<'static>,
    input_bytes: &[u8],
    limit: Option<usize>,
    initial: usize,
) -> io::Result<(PyBuf, usize, bool)> {
    let mut input = InBuffer::around(input_bytes);
    if limit == Some(0) {
        // Nothing may be returned, but zstd still consumes what it can.
        let mut empty = [0u8; 0];
        let mut out = OutBuffer::around(&mut empty[..]);
        let remaining = dctx.decompress_stream(&mut out, &mut input).map_err(zstd_error)?;
        drop(out);
        return Ok((PyBuf::new(1)?, input.pos(), remaining == 0));
    }
    let cap = limit.map_or(initial, |limit| initial.min(limit));
    let mut output = PyBuf::new(cap)?;
    let mut eof = false;
    loop {
        let before = (input.pos(), output.len);
        let mut out = OutBuffer::around_pos(&mut output, before.1);
        let remaining = without_gil(|| dctx.decompress_stream(&mut out, &mut input))
            .map_err(zstd_error)?;
        drop(out);

        if remaining == 0 {
            eof = true;
            break;
        }
        if output.is_full() {
            if limit == Some(output.len) {
                break;
            }
            output.grow(limit)?;
            continue;
        }
        if input.pos() == input_bytes.len() {
            break;
        }
        if before == (input.pos(), output.len) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "decoder made no progress"));
        }
    }
    Ok((output, input.pos(), eof))
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
        let remaining =
            without_gil(|| cctx.compress_stream2(&mut out, &mut input, directive))
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
            output.grow(None)?;
        } else if before == (input.pos(), output.len) {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "encoder made no progress"));
        }
    }
}

fn io_error(error: io::Error) -> *mut PyObject {
    if error.kind() == io::ErrorKind::OutOfMemory {
        unsafe { PyErr_SetString(PyExc_MemoryError, c"out of memory".as_ptr()) };
        return ptr::null_mut();
    }
    runtime_error(error)
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
        Err(error) => return io_error(error),
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
        Err(error) => io_error(error),
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
        Err(error) => io_error(error),
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
        Err(error) => return io_error(error),
    };
    let capsule = unsafe {
        PyCapsule_New(decoder, DECODER_CAPSULE_NAME.as_ptr(), Some(drop_decoder))
    };
    if capsule.is_null() {
        drop(unsafe { Box::from_raw(decoder.cast::<StreamDecompressor>()) });
    }
    capsule
}

unsafe extern "C" fn encoder_set_pledged(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"encoder_set_pledged() takes two arguments");
    }
    let Some(encoder) = (unsafe { capsule_ref::<StreamCompressor>(*args, ENCODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    let size = unsafe { PyLong_AsUnsignedLongLong(*args.add(1)) };
    if size == u64::MAX && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    match encoder.set_pledged(size) {
        Ok(()) => unsafe {
            let none = ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>();
            Py_IncRef(none);
            none
        },
        Err(error) => io_error(error),
    }
}

unsafe extern "C" fn decoder_decompress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return type_error(c"decoder_decompress() takes three arguments");
    }
    let Some(decoder) = (unsafe { capsule_ref::<StreamDecompressor>(*args, DECODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    let buffer = match unsafe { BorrowedBuffer::from_object(*args.add(1)) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let max_length = unsafe { PyLong_AsSsize_t(*args.add(2)) };
    if max_length == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let (output, flags) = match decoder.decompress(buffer.bytes(), max_length as i64) {
        Ok(result) => result,
        Err(error) => return io_error(error),
    };
    let output = match output.into_object() {
        Ok(output) => output,
        Err(error) => return io_error(error),
    };
    let flags = unsafe { PyLong_FromLong(flags) };
    let result = unsafe { PyTuple_New(2) };
    if flags.is_null() || result.is_null() {
        unsafe {
            Py_DecRef(output);
            if !flags.is_null() {
                Py_DecRef(flags);
            }
            if !result.is_null() {
                Py_DecRef(result);
            }
        }
        return ptr::null_mut();
    }
    unsafe {
        PyTuple_SetItem(result, 0, output);
        PyTuple_SetItem(result, 1, flags);
    }
    result
}

unsafe extern "C" fn decoder_unused_data(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"decoder_unused_data() takes one argument");
    }
    let Some(decoder) = (unsafe { capsule_ref::<StreamDecompressor>(*args, DECODER_CAPSULE_NAME) }) else {
        return ptr::null_mut();
    };
    decoder.unused_data()
}

static METHODS: [PyMethodDef; 8] = [
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
        ml_name: c"encoder_set_pledged".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: encoder_set_pledged },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pledge the size of the next Zstandard frame".as_ptr() as *mut c_char,
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
    PyMethodDef {
        ml_name: c"decoder_unused_data".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decoder_unused_data },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the input left after the end of the frame".as_ptr() as *mut c_char,
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
