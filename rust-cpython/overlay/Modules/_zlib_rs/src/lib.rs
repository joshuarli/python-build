use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyBytes_FromStringAndSize;
use flate2::{Compress, Compression, Decompress, FlushCompress, FlushDecompress, Status};

const PYBUF_SIMPLE: c_int = 0;
const OUTPUT_CHUNK_SIZE: usize = 64 * 1024;
const COMPRESSOR_CAPSULE: &std::ffi::CStr = c"_zlib_rs.Compressor";
const DECOMPRESSOR_CAPSULE: &std::ffi::CStr = c"_zlib_rs.Decompressor";

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
    fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return Err(());
            }
            Ok(Self {
                view: view.assume_init(),
            })
        }
    }

    fn copy_bytes(&self) -> Option<Vec<u8>> {
        if self.view.len < 0 {
            set_value_error(c"buffer length cannot be negative");
            return None;
        }
        if self.view.len == 0 {
            return Some(Vec::new());
        }
        let bytes = unsafe {
            slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize)
        };
        Some(bytes.to_vec())
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

struct Compressor {
    inner: Compress,
    finished: bool,
}

struct Decompressor {
    inner: Decompress,
    pending_input: Vec<u8>,
    pending_output: Vec<u8>,
    unused_data: Vec<u8>,
    stream_end: bool,
    eof: bool,
    needs_input: bool,
    finished: bool,
}

fn set_type_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) }
}

fn set_value_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) }
}

unsafe fn read_buffer(argument: *mut PyObject) -> Option<Vec<u8>> {
    let buffer = match BorrowedBuffer::from_object(argument) {
        Ok(buffer) => buffer,
        Err(()) => return None,
    };
    buffer.copy_bytes()
}

unsafe fn read_capsule<T>(
    argument: *mut PyObject,
    name: &'static std::ffi::CStr,
) -> Option<*mut T> {
    let pointer = unsafe { PyCapsule_GetPointer(argument, name.as_ptr()) };
    if pointer.is_null() {
        return None;
    }
    Some(pointer.cast::<T>())
}

unsafe fn new_capsule<T>(
    value: T,
    name: &'static std::ffi::CStr,
    destructor: unsafe extern "C" fn(*mut PyObject),
) -> *mut PyObject {
    let pointer = Box::into_raw(Box::new(value));
    let capsule = unsafe {
        PyCapsule_New(
            pointer.cast::<c_void>(),
            name.as_ptr(),
            Some(destructor),
        )
    };
    if capsule.is_null() {
        unsafe { drop(Box::from_raw(pointer)) };
    }
    capsule
}

unsafe extern "C" fn free_compressor(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, COMPRESSOR_CAPSULE.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<Compressor>())) };
    }
}

unsafe extern "C" fn free_decompressor(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, DECOMPRESSOR_CAPSULE.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<Decompressor>())) };
    }
}

unsafe fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t)
    }
}

fn flush_compress(mode: std::ffi::c_long) -> Option<FlushCompress> {
    match mode {
        0 => Some(FlushCompress::None),
        1 => Some(FlushCompress::Partial),
        2 => Some(FlushCompress::Sync),
        3 => Some(FlushCompress::Full),
        4 => Some(FlushCompress::Finish),
        // flate2 exposes partial flush but not zlib's block-flush spelling.
        5 => Some(FlushCompress::Partial),
        _ => None,
    }
}

fn compress_bytes(
    compressor: &mut Compressor,
    input: &[u8],
    flush: FlushCompress,
) -> Result<Vec<u8>, ()> {
    if compressor.finished {
        return Err(());
    }
    let mut output = Vec::new();
    let mut consumed = 0usize;
    loop {
        let mut chunk = vec![0u8; OUTPUT_CHUNK_SIZE];
        let before_in = compressor.inner.total_in();
        let before_out = compressor.inner.total_out();
        let status = compressor
            .inner
            .compress(&input[consumed..], &mut chunk, flush)
            .map_err(|_| ())?;
        let used = (compressor.inner.total_in() - before_in) as usize;
        let written = (compressor.inner.total_out() - before_out) as usize;
        consumed = consumed.saturating_add(used);
        output.extend_from_slice(&chunk[..written]);

        if status == Status::StreamEnd {
            compressor.finished = true;
            break;
        }
        if consumed == input.len() && written < chunk.len() {
            break;
        }
        if used == 0 && written == 0 {
            if consumed == input.len() {
                break;
            }
            return Err(());
        }
    }
    if consumed != input.len() {
        return Err(());
    }
    Ok(output)
}

fn decompress_call(
    decompressor: &mut Decompressor,
    limit: usize,
    output: &mut Vec<u8>,
) -> Result<(Status, usize), ()> {
    let mut chunk = vec![0u8; limit];
    let before_in = decompressor.inner.total_in();
    let before_out = decompressor.inner.total_out();
    let status = decompressor
        .inner
        .decompress(&decompressor.pending_input, &mut chunk, FlushDecompress::None)
        .map_err(|_| ())?;
    let used = (decompressor.inner.total_in() - before_in) as usize;
    let written = (decompressor.inner.total_out() - before_out) as usize;
    if used > 0 {
        decompressor.pending_input.drain(..used);
    }
    output.extend_from_slice(&chunk[..written]);
    if status == Status::StreamEnd {
        decompressor.stream_end = true;
        decompressor.eof = decompressor.pending_output.is_empty();
        decompressor.unused_data = std::mem::take(&mut decompressor.pending_input);
        decompressor.needs_input = true;
    }
    Ok((status, written))
}

fn decompress_bytes(
    decompressor: &mut Decompressor,
    input: &[u8],
    max_length: usize,
) -> Result<Vec<u8>, ()> {
    if decompressor.eof {
        decompressor.unused_data.extend_from_slice(input);
        return Ok(Vec::new());
    }
    decompressor.pending_input.extend_from_slice(input);

    let unlimited = max_length == 0;
    let mut output = Vec::new();
    let mut remaining = if unlimited { usize::MAX } else { max_length };
    loop {
        if !decompressor.pending_output.is_empty() {
            let count = decompressor.pending_output.len().min(remaining);
            output.extend_from_slice(&decompressor.pending_output[..count]);
            decompressor.pending_output.drain(..count);
            if !unlimited {
                remaining -= count;
                if remaining == 0 {
                    break;
                }
            }
        }

        if decompressor.stream_end && decompressor.pending_output.is_empty() {
            decompressor.eof = true;
        }

        if decompressor.eof {
            break;
        }
        let limit = if unlimited {
            OUTPUT_CHUNK_SIZE
        } else {
            remaining.min(OUTPUT_CHUNK_SIZE)
        };
        let (status, written) = decompress_call(decompressor, limit, &mut output)?;
        if !unlimited {
            remaining -= written;
            if remaining == 0 {
                break;
            }
        }
        if status == Status::StreamEnd {
            break;
        }
        if written == 0 && decompressor.pending_input.is_empty() {
            decompressor.needs_input = true;
            break;
        }
        if !unlimited && written < limit && decompressor.pending_input.is_empty() {
            decompressor.needs_input = true;
            break;
        }
        if written == 0 && decompressor.pending_input.is_empty() {
            decompressor.needs_input = true;
            break;
        }
    }

    if !unlimited && !decompressor.eof && decompressor.pending_output.is_empty() {
        if decompressor.pending_input.is_empty() && !output.is_empty() {
            let mut probe = Vec::new();
            let (status, written) = decompress_call(decompressor, 1, &mut probe)?;
            if written > 0 {
                decompressor.pending_output = probe;
                if status == Status::StreamEnd {
                    decompressor.eof = false;
                }
                decompressor.needs_input = false;
            } else if status == Status::StreamEnd {
                decompressor.needs_input = true;
            } else {
                decompressor.needs_input = true;
            }
        } else {
            decompressor.needs_input = decompressor.pending_input.is_empty();
        }
    } else {
        decompressor.needs_input = decompressor.pending_input.is_empty()
            && decompressor.pending_output.is_empty();
    }
    if decompressor.stream_end && decompressor.pending_output.is_empty() {
        decompressor.eof = true;
    }
    Ok(output)
}

unsafe extern "C" fn compressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"compressor() takes exactly two arguments");
        return ptr::null_mut();
    }
    let level = unsafe { PyLong_AsLong(*args) };
    if level == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if !(-1..=9).contains(&level) {
        set_value_error(c"compression level must be between -1 and 9");
        return ptr::null_mut();
    }
    let wbits = unsafe { PyLong_AsLong(*args.add(1)) };
    if wbits == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if wbits != 15 && wbits != -15 {
        set_value_error(c"unsupported DEFLATE window size");
        return ptr::null_mut();
    }
    let compressor = Compressor {
        inner: Compress::new(
            if level == -1 {
                Compression::default()
            } else {
                Compression::new(level as u32)
            },
            wbits > 0,
        ),
        finished: false,
    };
    unsafe { new_capsule(compressor, COMPRESSOR_CAPSULE, free_compressor) }
}

unsafe extern "C" fn compressor_compress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"compress() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(compressor) = (unsafe {
        read_capsule::<Compressor>(*args, COMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let Some(input) = (unsafe { read_buffer(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    match compress_bytes(unsafe { &mut *compressor }, &input, FlushCompress::None) {
        Ok(output) => unsafe { bytes_from_slice(&output) },
        Err(()) => {
            set_value_error(c"compressor could not consume the input");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn compressor_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"flush() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(compressor) = (unsafe {
        read_capsule::<Compressor>(*args, COMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let mode = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if mode == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let Some(flush) = flush_compress(mode as std::ffi::c_long) else {
        set_value_error(c"invalid compressor flush mode");
        return ptr::null_mut();
    };
    match compress_bytes(unsafe { &mut *compressor }, &[], flush) {
        Ok(output) => unsafe { bytes_from_slice(&output) },
        Err(()) => {
            set_value_error(c"compressor has already been flushed");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn decompressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"decompressor() takes exactly one argument");
        return ptr::null_mut();
    }
    let wbits = unsafe { PyLong_AsLong(*args) };
    if wbits == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if wbits != 15 && wbits != -15 {
        set_value_error(c"unsupported DEFLATE window size");
        return ptr::null_mut();
    }
    let decompressor = Decompressor {
        inner: Decompress::new(wbits > 0),
        pending_input: Vec::new(),
        pending_output: Vec::new(),
        unused_data: Vec::new(),
        stream_end: false,
        eof: false,
        needs_input: true,
        finished: false,
    };
    unsafe { new_capsule(decompressor, DECOMPRESSOR_CAPSULE, free_decompressor) }
}

unsafe extern "C" fn decompressor_decompress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"decompress() takes exactly three arguments");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let Some(input) = (unsafe { read_buffer(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if unsafe { (*decompressor).finished } {
        set_value_error(c"inconsistent stream state");
        return ptr::null_mut();
    }
    let max_length = unsafe { PyLong_AsLongLong(*args.add(2)) };
    if max_length == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if max_length < 0 {
        set_value_error(c"max_length must be non-negative");
        return ptr::null_mut();
    }
    match decompress_bytes(unsafe { &mut *decompressor }, &input, max_length as usize) {
        Ok(output) => unsafe { bytes_from_slice(&output) },
        Err(()) => {
            set_value_error(c"invalid DEFLATE stream");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn decompressor_eof(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"eof() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let eof = unsafe { (*decompressor).eof };
    unsafe { cpython_sys::PyBool_FromLong(if eof { 1 } else { 0 }) }
}

unsafe extern "C" fn decompressor_needs_input(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"needs_input() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let needs_input = unsafe { (*decompressor).needs_input };
    unsafe { cpython_sys::PyBool_FromLong(if needs_input { 1 } else { 0 }) }
}

unsafe extern "C" fn decompressor_unused_data(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"unused_data() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let unused_data = unsafe { (*decompressor).unused_data.clone() };
    unsafe { bytes_from_slice(&unused_data) }
}

unsafe extern "C" fn decompressor_unconsumed_tail(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"unconsumed_tail() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    let tail = unsafe { (*decompressor).pending_input.clone() };
    unsafe { bytes_from_slice(&tail) }
}

unsafe extern "C" fn decompressor_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"flush() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(decompressor) = (unsafe {
        read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE)
    }) else {
        return ptr::null_mut();
    };
    if unsafe { (*decompressor).finished } {
        set_value_error(c"inconsistent stream state");
        return ptr::null_mut();
    }
    let length = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if length == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if length < 1 {
        set_value_error(c"length must be greater than zero");
        return ptr::null_mut();
    }
    match decompress_bytes(unsafe { &mut *decompressor }, &[], 0) {
        Ok(output) => {
            unsafe { (*decompressor).finished = (*decompressor).eof };
            unsafe { bytes_from_slice(&output) }
        }
        Err(()) => {
            set_value_error(c"invalid DEFLATE stream");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn compress_once(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"compress() takes exactly three arguments");
        return ptr::null_mut();
    }
    let Some(input) = (unsafe { read_buffer(*args) }) else {
        return ptr::null_mut();
    };
    let level = unsafe { PyLong_AsLong(*args.add(1)) };
    if level == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if !(-1..=9).contains(&level) {
        set_value_error(c"compression level must be between -1 and 9");
        return ptr::null_mut();
    }
    let wbits = unsafe { PyLong_AsLong(*args.add(2)) };
    if wbits == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if wbits != 15 && wbits != -15 {
        set_value_error(c"unsupported DEFLATE window size");
        return ptr::null_mut();
    }
    let mut compressor = Compressor {
        inner: Compress::new(
            if level == -1 {
                Compression::default()
            } else {
                Compression::new(level as u32)
            },
            wbits > 0,
        ),
        finished: false,
    };
    match compress_bytes(&mut compressor, &input, FlushCompress::Finish) {
        Ok(output) => unsafe { bytes_from_slice(&output) },
        Err(()) => {
            set_value_error(c"could not compress the input");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn decompress_once(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"decompress() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(input) = (unsafe { read_buffer(*args) }) else {
        return ptr::null_mut();
    };
    let wbits = unsafe { PyLong_AsLong(*args.add(1)) };
    if wbits == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if wbits != 15 && wbits != -15 {
        set_value_error(c"unsupported DEFLATE window size");
        return ptr::null_mut();
    }
    let mut decompressor = Decompressor {
        inner: Decompress::new(wbits > 0),
        pending_input: Vec::new(),
        pending_output: Vec::new(),
        unused_data: Vec::new(),
        stream_end: false,
        eof: false,
        needs_input: true,
        finished: false,
    };
    match decompress_bytes(&mut decompressor, &input, 0) {
        Ok(output) if decompressor.eof => unsafe { bytes_from_slice(&output) },
        _ => {
            set_value_error(c"incomplete or invalid DEFLATE stream");
            ptr::null_mut()
        }
    }
}

pub extern "C" fn _zlib_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _zlib_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _ZLIB_RS_MODULE_METHODS: [PyMethodDef; 13] = [
    PyMethodDef {
        ml_name: c"compress_once".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compress_once },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compress one zlib or raw-DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompress_once".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompress_once },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decompress one zlib or raw-DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"compressor".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a zlib or raw-DEFLATE compressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"compress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_compress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compress one input block.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"flush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_flush },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Flush a raw-DEFLATE compressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompressor".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a zlib or raw-DEFLATE decompressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_decompress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decompress one input block.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"eof".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_eof },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return whether the DEFLATE stream ended.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"needs_input".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_needs_input },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return whether more compressed input is needed.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unused_data".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_unused_data },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return bytes following the DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unconsumed_tail".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_unconsumed_tail },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return compressed input not yet consumed.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompressor_flush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_flush },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Finish a decompressor object.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

// These are the generated slot IDs in the pinned CPython 3.16 fork.
const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

// Each codec state is owned by a capsule, and the module definition has no mutable state.
static _ZLIB_RS_MODULE_SLOTS: ModuleSlots = ModuleSlots([
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

pub static _ZLIB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_zlib_rs".as_ptr() as *mut _,
        m_doc: c"Rust DEFLATE codecs for zlib.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_ZLIB_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: _ZLIB_RS_MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(_zlib_rs_clear),
        m_free: Some(_zlib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub unsafe extern "C" fn PyInit__zlib_rs() -> *mut PyObject {
    _ZLIB_RS_MODULE.init_multi_phase()
}
