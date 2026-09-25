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
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyCapsule_GetPointer;
use cpython_sys::PyCapsule_New;
use cpython_sys::PyErr_NoMemory;
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
use cpython_sys::Py_ssize_t;

use zstd::stream::raw::{Decoder, Encoder, Operation, OutBuffer};

const PYBUF_SIMPLE: c_int = 0;
const OUTPUT_BUFFER_SIZE: usize = 64 * 1024;
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

struct StreamCompressor {
    encoder: Encoder<'static>,
    frame_has_input: bool,
}

impl StreamCompressor {
    fn new(level: i32) -> io::Result<Self> {
        Ok(Self {
            encoder: Encoder::new(level)?,
            frame_has_input: false,
        })
    }

    fn compress(&mut self, data: &[u8], mode: i32) -> io::Result<Vec<u8>> {
        if mode != 0 && mode != 1 && mode != 2 {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid compression mode"));
        }
        if mode == 2 && !self.frame_has_input {
            self.encoder.set_pledged_src_size(Some(data.len() as u64))?;
        }
        let mut output = Vec::new();
        run_input(&mut self.encoder, data, &mut output)?;
        self.frame_has_input |= !data.is_empty();
        match mode {
            0 => {}
            1 => finish_pending(&mut self.encoder, &mut output, false)?,
            2 => {
                finish_pending(&mut self.encoder, &mut output, true)?;
                self.encoder.reinit()?;
                self.frame_has_input = false;
            }
            _ => unreachable!(),
        }
        Ok(output)
    }

    fn flush(&mut self, mode: i32) -> io::Result<Vec<u8>> {
        if mode != 1 && mode != 2 {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid flush mode"));
        }
        let mut output = Vec::new();
        finish_pending(&mut self.encoder, &mut output, mode == 2)?;
        if mode == 2 {
            self.encoder.reinit()?;
            self.frame_has_input = false;
        }
        Ok(output)
    }
}

struct StreamDecompressor {
    decoder: Decoder<'static>,
    frame_finished: bool,
}

impl StreamDecompressor {
    fn new() -> io::Result<Self> {
        Ok(Self {
            decoder: Decoder::new()?,
            frame_finished: false,
        })
    }

    fn decompress(&mut self, data: &[u8]) -> io::Result<Vec<u8>> {
        if data.is_empty() {
            return Ok(Vec::new());
        }
        if self.frame_finished {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "frame already finished"));
        }

        let mut output = Vec::new();
        let mut input_offset = 0;
        loop {
            let mut buffer = output_buffer()?;
            let status = self
                .decoder
                .run_on_buffers(&data[input_offset..], &mut buffer)?;
            input_offset += status.bytes_read;
            append_output(&mut output, &buffer[..status.bytes_written])?;

            if status.remaining == 0 {
                self.frame_finished = true;
                break;
            }
            if input_offset == data.len() && status.bytes_written < buffer.len() {
                break;
            }
            if status.bytes_read == 0 && status.bytes_written == 0 {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "decoder made no progress"));
            }
        }
        Ok(output)
    }
}

fn run_input(
    encoder: &mut Encoder<'static>,
    data: &[u8],
    output: &mut Vec<u8>,
) -> io::Result<()> {
    let mut input_offset = 0;
    loop {
        let mut buffer = output_buffer()?;
        let status = encoder.run_on_buffers(&data[input_offset..], &mut buffer)?;
        input_offset += status.bytes_read;
        append_output(output, &buffer[..status.bytes_written])?;

        if input_offset == data.len() && status.bytes_written < buffer.len() {
            return Ok(());
        }
        if status.bytes_read == 0 && status.bytes_written == 0 {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "encoder made no progress"));
        }
    }
}

fn finish_pending(
    encoder: &mut Encoder<'static>,
    output: &mut Vec<u8>,
    finish_frame: bool,
) -> io::Result<()> {
    loop {
        let mut buffer = output_buffer()?;
        let mut out = OutBuffer::around(&mut buffer);
        let remaining = if finish_frame {
            encoder.finish(&mut out, true)?
        } else {
            encoder.flush(&mut out)?
        };
        let written = out.pos();
        drop(out);
        append_output(output, &buffer[..written])?;
        if remaining == 0 {
            return Ok(());
        }
        if written == 0 {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "encoder flush made no progress"));
        }
    }
}

fn output_buffer() -> io::Result<Vec<u8>> {
    let mut buffer = Vec::new();
    buffer
        .try_reserve_exact(OUTPUT_BUFFER_SIZE)
        .map_err(|error| io::Error::new(io::ErrorKind::OutOfMemory, error))?;
    buffer.resize(OUTPUT_BUFFER_SIZE, 0);
    Ok(buffer)
}

fn append_output(output: &mut Vec<u8>, bytes: &[u8]) -> io::Result<()> {
    output
        .try_reserve(bytes.len())
        .map_err(|error| io::Error::new(io::ErrorKind::OutOfMemory, error))?;
    output.extend_from_slice(bytes);
    Ok(())
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

fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
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
        Ok(output) => bytes_from_slice(&output),
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
        Ok(output) => bytes_from_slice(&output),
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
        Ok(output) => bytes_from_slice(&output),
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
