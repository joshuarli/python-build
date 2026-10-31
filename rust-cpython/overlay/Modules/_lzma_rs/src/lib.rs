use std::ffi::{c_char, c_void};
use std::io::{Read, Write};
use std::ptr;
use std::slice;

use cpython_binding::ffi::{
    PyBool_FromLong, PyBytes_AsString, PyBytes_FromStringAndSize, PyErr_Clear, PyErr_NoMemory,
    PyErr_Occurred, PyMethodDef, PyObject, Py_DecRef, Py_ssize_t,
};
use cpython_binding::ffi_ext::{
    PyCapsule_GetPointer, PyCapsule_New, PyLong_AsLong, _PyBytes_Resize,
};
use cpython_binding::{Borrowed, Buffer, Module, fastcall, method_table_end};
use lzma_rust2::{DICT_SIZE_MIN, XzOptions, XzReader, XzWriter};

const XZ_MAGIC: &[u8; 6] = b"\xfd7zXZ\0";
const COMPRESSOR_CAPSULE_NAME: &std::ffi::CStr = c"_lzma_rs.Compressor";

/// The compressor defers creating the XZ writer until the input size is known
/// (at flush) or as large as the preset dictionary, so small inputs do not
/// allocate and touch tables sized for the full preset dictionary.
struct CompressionState {
    preset: u32,
    dict_size: u32,
    pending: Vec<u8>,
    writer: Option<XzWriter<Vec<u8>>>,
    finished: bool,
}

impl CompressionState {
    fn start_writer(&mut self, dict_size: u32) -> Result<(), ()> {
        let mut options = XzOptions::with_preset(self.preset);
        options.lzma_options.dict_size = dict_size;
        let mut writer = XzWriter::new(Vec::new(), options).map_err(|_| ())?;
        let pending = std::mem::take(&mut self.pending);
        writer.write_all(&pending).map_err(|_| ())?;
        self.writer = Some(writer);
        Ok(())
    }
}

fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t)
    }
}

fn declined() -> *mut PyObject {
    unsafe { PyBool_FromLong(0) }
}

unsafe fn compressor_state(capsule: *mut PyObject) -> Option<&'static mut CompressionState> {
    let pointer = unsafe {
        PyCapsule_GetPointer(capsule, COMPRESSOR_CAPSULE_NAME.as_ptr())
    };
    if pointer.is_null() {
        return None;
    }
    Some(unsafe { &mut *pointer.cast::<CompressionState>() })
}

unsafe extern "C" fn compressor_capsule_free(capsule: *mut PyObject) {
    let pointer = unsafe {
        PyCapsule_GetPointer(capsule, COMPRESSOR_CAPSULE_NAME.as_ptr())
    };
    if pointer.is_null() {
        unsafe { PyErr_Clear() };
        return;
    }
    unsafe { drop(Box::from_raw(pointer.cast::<CompressionState>())) };
}

unsafe extern "C" fn compressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return declined();
    }
    let preset = unsafe { PyLong_AsLong(*args) };
    if unsafe { !PyErr_Occurred().is_null() } {
        unsafe { PyErr_Clear() };
        return declined();
    }
    let Ok(preset) = u32::try_from(preset) else {
        return declined();
    };
    if preset > 9 {
        return declined();
    }

    let state = Box::new(CompressionState {
        preset,
        dict_size: XzOptions::with_preset(preset).lzma_options.dict_size,
        pending: Vec::new(),
        writer: None,
        finished: false,
    });
    let pointer = Box::into_raw(state).cast::<c_void>();
    let capsule = unsafe {
        PyCapsule_New(
            pointer,
            COMPRESSOR_CAPSULE_NAME.as_ptr(),
            Some(compressor_capsule_free),
        )
    };
    if capsule.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<CompressionState>())) };
    }
    capsule
}

unsafe extern "C" fn compressor_compress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return declined();
    }
    let Ok(buffer) = Buffer::acquire(unsafe { Borrowed::from_raw(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    let input = buffer.as_bytes();
    let Some(state) = (unsafe { compressor_state(*args) }) else {
        return ptr::null_mut();
    };
    if state.finished {
        return declined();
    }
    let Some(writer) = state.writer.as_mut() else {
        state.pending.extend_from_slice(input);
        if state.pending.len() >= state.dict_size as usize {
            let dict_size = state.dict_size;
            if state.start_writer(dict_size).is_err() {
                unsafe { PyErr_NoMemory() };
                return ptr::null_mut();
            }
            let writer = state.writer.as_mut().expect("writer started");
            return bytes_from_slice(&std::mem::take(writer.inner_mut()));
        }
        return bytes_from_slice(&[]);
    };
    if writer.write_all(input).is_err() {
        return declined();
    }
    let output = std::mem::take(writer.inner_mut());
    bytes_from_slice(&output)
}

unsafe extern "C" fn compressor_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return declined();
    }
    let Some(state) = (unsafe { compressor_state(*args) }) else {
        return ptr::null_mut();
    };
    if state.finished {
        return declined();
    }
    state.finished = true;
    if state.writer.is_none() {
        let dict_size = (state.pending.len().min(state.dict_size as usize) as u32).max(DICT_SIZE_MIN);
        if state.start_writer(dict_size).is_err() {
            unsafe { PyErr_NoMemory() };
            return ptr::null_mut();
        }
    }
    let Some(writer) = state.writer.take() else {
        return declined();
    };
    match writer.finish() {
        Ok(output) => bytes_from_slice(&output),
        Err(_) => declined(),
    }
}

unsafe extern "C" fn decompress_xz(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return declined();
    }
    let buffer = match Buffer::acquire(unsafe { Borrowed::from_raw(*args) }) {
        Ok(buffer) => buffer,
        Err(_) => {
            unsafe { PyErr_Clear() };
            return declined();
        }
    };
    let input = buffer.as_bytes();
    if !input.starts_with(XZ_MAGIC) {
        return declined();
    }

    let mut reader = XzReader::new(input, true);
    // Decode straight into a bytes object and shrink it, rather than growing
    // a Vec by doubling and copying it into the result.
    let mut capacity = input.len().saturating_mul(3).clamp(4096, 1 << 26);
    let mut result = unsafe { PyBytes_FromStringAndSize(ptr::null(), capacity as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let mut length = 0usize;
    loop {
        if length == capacity {
            capacity = capacity.saturating_mul(2);
            if capacity > Py_ssize_t::MAX as usize {
                unsafe {
                    Py_DecRef(result);
                    PyErr_NoMemory();
                }
                return ptr::null_mut();
            }
            if unsafe { _PyBytes_Resize(&mut result, capacity as Py_ssize_t) } != 0 {
                return ptr::null_mut();
            }
        }
        let destination = unsafe {
            slice::from_raw_parts_mut(
                PyBytes_AsString(result).cast::<u8>().add(length),
                capacity - length,
            )
        };
        match reader.read(destination) {
            Ok(0) => break,
            Ok(count) => length += count,
            Err(_) => {
                unsafe { Py_DecRef(result) };
                return declined();
            }
        }
    }
    if length != capacity && unsafe { _PyBytes_Resize(&mut result, length as Py_ssize_t) } != 0 {
        return ptr::null_mut();
    }
    result
}

static METHODS: [PyMethodDef; 5] = [
    fastcall(c"compressor_new", compressor_new, c"Create a stateful XZ compressor."),
    fastcall(
        c"compressor_compress",
        compressor_compress,
        c"Write input to an XZ compressor and return ready output.",
    ),
    fastcall(
        c"compressor_flush",
        compressor_flush,
        c"Finish an XZ compressor and return its final output.",
    ),
    fastcall(c"decompress_xz", decompress_xz, c"Decompress concatenated XZ streams."),
    method_table_end(),
];

static MODULE: Module = Module::new(c"_lzma_rs", c"Rust XZ compression and decompression.", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__lzma_rs() -> *mut PyObject {
    MODULE.init()
}
