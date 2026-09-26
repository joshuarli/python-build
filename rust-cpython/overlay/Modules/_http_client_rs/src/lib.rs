use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_O;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_NewRef;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

unsafe extern "C" {
    fn PyBytes_Size(object: *mut PyObject) -> Py_ssize_t;
    fn PyLong_FromLong(value: c_long) -> *mut PyObject;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
}

unsafe fn bytes_argument<'a>(object: *mut PyObject) -> Result<&'a [u8], ()> {
    let size = unsafe { PyBytes_Size(object) };
    if size < 0 {
        return Err(());
    }
    let pointer = unsafe { PyBytes_AsString(object) };
    if pointer.is_null() {
        return Err(());
    }
    Ok(unsafe { slice::from_raw_parts(pointer.cast::<u8>(), size as usize) })
}

unsafe fn bytes_object(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(bytes.as_ptr().cast(), bytes.len() as Py_ssize_t)
    }
}

fn no_parse() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

fn parse_status_line(line: &[u8]) -> Option<(Vec<u8>, c_long, Vec<u8>)> {
    let (line_end, ending) = if let Some(prefix) = line.strip_suffix(b"\r\n") {
        (prefix.len(), b"\r\n".as_slice())
    } else if line.iter().any(|byte| matches!(*byte, b'\r' | b'\n')) {
        return None;
    } else {
        (line.len(), b"".as_slice())
    };
    let status_line = &line[..line_end];

    // Keep unusual but historically accepted status lines on CPython's path.
    if status_line.len() < 12
        || !status_line.starts_with(b"HTTP/1.")
        || !status_line[7].is_ascii_digit()
        || status_line[8] != b' '
        || !status_line[9..12].iter().all(u8::is_ascii_digit)
    {
        return None;
    }
    let code = std::str::from_utf8(&status_line[9..12]).ok()?.parse::<u16>().ok()?;
    if !(100..=999).contains(&code) {
        return None;
    }
    let reason_start = match status_line.get(12) {
        None => status_line.len(),
        Some(b' ') => {
            let mut start = 13;
            while start < status_line.len() && matches!(status_line[start], b' ' | b'\t') {
                start += 1;
            }
            start
        }
        _ => return None,
    };

    // httparse checks the complete HTTP/1 response-line grammar before the
    // status code and reason are exposed to the public Python response object.
    let mut framed = Vec::with_capacity(status_line.len() + 4);
    framed.extend_from_slice(status_line);
    framed.extend_from_slice(b"\r\n\r\n");
    let mut headers = [httparse::EMPTY_HEADER; 1];
    let mut response = httparse::Response::new(&mut headers);
    let httparse::Status::Complete(consumed) = response.parse(&framed).ok()? else {
        return None;
    };
    if consumed != framed.len()
        || response.code != Some(code)
        || response.version != Some(status_line[7] - b'0')
    {
        return None;
    }

    let mut reason = status_line[reason_start..].to_vec();
    if reason_start < status_line.len() {
        reason.extend_from_slice(ending);
    }
    Some((status_line[..8].to_vec(), code as c_long, reason))
}

fn encode_request_line(line: &[u8]) -> Option<Vec<u8>> {
    if line.iter().any(|byte| matches!(*byte, b'\r' | b'\n')) {
        return None;
    }
    let mut framed = Vec::with_capacity(line.len() + 4);
    framed.extend_from_slice(line);
    framed.extend_from_slice(b"\r\n\r\n");
    let mut headers = [httparse::EMPTY_HEADER; 1];
    let mut request = httparse::Request::new(&mut headers);
    let httparse::Status::Complete(consumed) = request.parse(&framed).ok()? else {
        return None;
    };
    if consumed != framed.len() {
        return None;
    }
    let method = request.method?.as_bytes();
    let path = request.path?.as_bytes();
    let version = request.version?;
    if version > 9 {
        return None;
    }
    let mut protocol = *b"HTTP/1.0";
    protocol[7] = b'0' + version;
    if !line.ends_with(&protocol) {
        return None;
    }

    let mut encoded = Vec::with_capacity(method.len() + path.len() + 11);
    encoded.extend_from_slice(method);
    encoded.push(b' ');
    encoded.extend_from_slice(path);
    encoded.extend_from_slice(b" HTTP/1.");
    encoded.push(b'0' + version);
    Some(encoded)
}

unsafe extern "C" fn parse_status_line_method(
    _module: *mut PyObject,
    argument: *mut PyObject,
) -> *mut PyObject {
    let line = match unsafe { bytes_argument(argument) } {
        Ok(line) => line,
        Err(()) => return ptr::null_mut(),
    };
    let Some((version, status, reason)) = parse_status_line(line) else {
        return no_parse();
    };

    let tuple = unsafe { PyTuple_New(3) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    let version_object = unsafe { bytes_object(&version) };
    if version_object.is_null() {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    let status_object = unsafe { PyLong_FromLong(status) };
    if status_object.is_null() {
        unsafe { Py_DecRef(version_object) };
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    let reason_object = unsafe { bytes_object(&reason) };
    if reason_object.is_null() {
        unsafe {
            Py_DecRef(status_object);
            Py_DecRef(version_object);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }

    if unsafe { PyTuple_SetItem(tuple, 0, version_object) } != 0 {
        unsafe {
            Py_DecRef(status_object);
            Py_DecRef(reason_object);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 1, status_object) } != 0 {
        unsafe {
            Py_DecRef(reason_object);
            Py_DecRef(tuple);
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 2, reason_object) } != 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

unsafe extern "C" fn encode_request_line_method(
    _module: *mut PyObject,
    argument: *mut PyObject,
) -> *mut PyObject {
    let line = match unsafe { bytes_argument(argument) } {
        Ok(line) => line,
        Err(()) => return ptr::null_mut(),
    };
    match encode_request_line(line) {
        Some(encoded) => unsafe { bytes_object(&encoded) },
        None => no_parse(),
    }
}

extern "C" fn _http_client_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn _http_client_rs_free(_module: *mut std::ffi::c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

struct ModuleSlots {
    ffi: UnsafeCell<[PyModuleDef_Slot; 2]>,
}

impl ModuleSlots {
    const fn as_mut_ptr(&self) -> *mut PyModuleDef_Slot {
        self.ffi.get().cast::<PyModuleDef_Slot>()
    }
}

// The parser keeps no mutable state or Python objects across calls.
unsafe impl Sync for ModuleSlots {}

static MODULE_SLOTS: ModuleSlots = ModuleSlots {
    ffi: UnsafeCell::new([
        PyModuleDef_Slot {
            slot: PY_MOD_MULTIPLE_INTERPRETERS,
            value: 2usize as *mut c_void,
        },
        PyModuleDef_Slot {
            slot: 0,
            value: ptr::null_mut(),
        },
    ]),
};

static MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"parse_status_line".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunction: parse_status_line_method,
        },
        ml_flags: METH_O,
        ml_doc: c"Parse a standard HTTP/1 response status line".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"encode_request_line".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunction: encode_request_line_method,
        },
        ml_flags: METH_O,
        ml_doc: c"Parse and serialize an HTTP/1 request line".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_http_client_rs".as_ptr() as *mut _,
        m_doc: c"HTTP/1 message-line parsing for http.client".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut _,
        m_slots: MODULE_SLOTS.as_mut_ptr(),
        m_traverse: None,
        m_clear: Some(_http_client_rs_clear),
        m_free: Some(_http_client_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__http_client_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
