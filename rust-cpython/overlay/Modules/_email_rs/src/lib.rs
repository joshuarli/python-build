use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::Py_NewRef;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_buffer;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;
use mail_parser::MessageParser;

const PYBUF_SIMPLE: c_int = 0;

fn valid_header_block(raw: &[u8]) -> Option<usize> {
    let mut position = 0;
    let mut fields = 0;
    let mut have_field = false;

    while position < raw.len() {
        let line_end = raw[position..]
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(raw.len(), |offset| position + offset + 1);
        let mut content_end = line_end;
        if line_end > position && raw[line_end - 1] == b'\n' {
            content_end -= 1;
            if content_end > position && raw[content_end - 1] == b'\r' {
                content_end -= 1;
            }
        }
        let line = &raw[position..content_end];
        if line.is_empty() || line.iter().any(|byte| *byte == b'\r') {
            return None;
        }

        if line[0] == b' ' || line[0] == b'\t' {
            if !have_field {
                return None;
            }
        } else {
            let colon = line.iter().position(|byte| *byte == b':')?;
            let name = &line[..colon];
            if name.is_empty()
                || !name
                    .iter()
                    .all(|byte| matches!(*byte, b'!'..=b'9' | b';'..=b'~'))
            {
                return None;
            }
            fields += 1;
            have_field = true;
        }

        if line
            .iter()
            .any(|byte| *byte == 0 || (*byte < b' ' && *byte != b'\t') || *byte == 0x7f)
        {
            return None;
        }
        position = line_end;
    }

    Some(fields)
}

fn parse_header_fields(raw: &[u8]) -> Option<Vec<&[u8]>> {
    if raw.is_empty() {
        return Some(Vec::new());
    }
    if raw.len() > u32::MAX as usize {
        return None;
    }
    let field_count = valid_header_block(raw)?;
    let message = MessageParser::default().parse_headers(raw)?;
    let part = message.parts.first()?;
    if part.headers.len() != field_count {
        return None;
    }

    let mut fields = Vec::with_capacity(field_count);
    let mut previous_end = 0;
    for header in &part.headers {
        let start = header.offset_field as usize;
        let end = header.offset_end as usize;
        if start != previous_end || end < start || end > raw.len() {
            return None;
        }
        fields.push(&raw[start..end]);
        previous_end = end;
    }
    (previous_end == raw.len()).then_some(fields)
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
            &[]
        } else {
            unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
        }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) };
    }
}

unsafe fn none_result() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe fn python_fields(fields: &[&[u8]]) -> *mut PyObject {
    let result = unsafe { PyList_New(fields.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }

    for (index, field) in fields.iter().enumerate() {
        if field.len() > isize::MAX as usize {
            unsafe {
                Py_DecRef(result);
                PyErr_NoMemory();
            }
            return ptr::null_mut();
        }
        let item = unsafe {
            PyBytes_FromStringAndSize(field.as_ptr().cast::<c_char>(), field.len() as Py_ssize_t)
        };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyList_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

/// Return original RFC header fields when the block uses strict field syntax.
///
/// # Safety
/// `args` is a valid CPython fast-call argument array.
unsafe extern "C" fn parse_fields(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"parse_header_fields() takes exactly one argument".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let buffer = match unsafe { BorrowedBuffer::from_object(*args) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    match parse_header_fields(buffer.bytes()) {
        Some(fields) => unsafe { python_fields(&fields) },
        None => unsafe { none_result() },
    }
}

pub extern "C" fn email_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn email_rs_free(_module: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static EMAIL_RS_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"parse_header_fields".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_fields,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a strict RFC message header block".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static EMAIL_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_email_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust RFC email header parsing".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: EMAIL_RS_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(email_rs_clear),
        m_free: Some(email_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__email_rs() -> *mut PyObject {
    EMAIL_RS_MODULE.init_multi_phase()
}
