use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_O;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyLong_FromLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::Py_NewRef;
use cpython_sys::PyObject;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

const NAME: i64 = 0;
const NUMBER: i64 = 1;
const OP: i64 = 2;
const NEWLINE: i64 = 3;

#[derive(Clone, Copy)]
struct TokenSpan {
    kind: i64,
    start: usize,
    end: usize,
}

fn is_identifier_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

fn is_identifier_continue(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn scan_line(line: &str) -> Option<Vec<TokenSpan>> {
    if !line.is_ascii() || !line.ends_with('\n') || line.contains('\r') {
        return None;
    }

    let bytes = line.as_bytes();
    let content_end = bytes.len() - 1;
    if content_end == 0 || bytes[0] == b' ' || bytes[0] == b'\t' {
        return None;
    }

    let mut spans = Vec::new();
    let mut offset = 0;
    while offset < content_end {
        if bytes[offset] == b' ' {
            offset += 1;
            continue;
        }

        let start = offset;
        let (kind, end) = if is_identifier_start(bytes[offset]) {
            offset += 1;
            while offset < content_end && is_identifier_continue(bytes[offset]) {
                offset += 1;
            }
            if &bytes[start..offset] == b"async" || &bytes[start..offset] == b"await" {
                return None;
            }
            (NAME, offset)
        } else if bytes[offset].is_ascii_digit() {
            offset += 1;
            while offset < content_end && bytes[offset].is_ascii_digit() {
                offset += 1;
            }
            let digits = &bytes[start..offset];
            if (digits.len() > 1 && digits[0] == b'0')
                || (offset < content_end
                    && (is_identifier_continue(bytes[offset]) || bytes[offset] == b'.'))
            {
                return None;
            }
            (NUMBER, offset)
        } else {
            let remaining = &line[offset..content_end];
            let operator = [
                "**=", "//=", "<<=", ">>=", "==", "!=", "<=", ">=", "**", "//", "<<",
                ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "->", ":=", "+",
                "-", "*", "/", "%", "<", ">", "=", "&", "|", "^", "~", ",",
            ];
            let Some(operator) = operator.iter().find(|operator| remaining.starts_with(**operator))
            else {
                return None;
            };
            offset += operator.len();
            (OP, offset)
        };

        spans.push(TokenSpan { kind, start, end });
    }

    if spans.is_empty() {
        return None;
    }
    spans.push(TokenSpan {
        kind: NEWLINE,
        start: content_end,
        end: content_end + 1,
    });
    Some(spans)
}

unsafe fn line_argument(object: *mut PyObject) -> Option<String> {
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if data.is_null() || size < 0 {
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    let value = unsafe { std::str::from_utf8_unchecked(bytes) };
    Some(value.to_owned())
}

fn none_object() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe fn scan_line_object(line: &str) -> *mut PyObject {
    let Some(spans) = scan_line(line) else {
        return none_object();
    };
    if spans.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }

    let list = unsafe { PyList_New(spans.len() as Py_ssize_t) };
    if list.is_null() {
        return ptr::null_mut();
    }
    for (index, span) in spans.iter().enumerate() {
        let item = unsafe { PyTuple_New(3) };
        if item.is_null() {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
        for (field, value) in [span.kind, span.start as i64, span.end as i64]
            .into_iter()
            .enumerate()
        {
            let value = unsafe { PyLong_FromLongLong(value) };
            if value.is_null()
                || unsafe { PyTuple_SetItem(item, field as Py_ssize_t, value) } != 0
            {
                unsafe {
                    Py_DecRef(item);
                    Py_DecRef(list);
                }
                return ptr::null_mut();
            }
        }
        if unsafe { PyList_SetItem(list, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
    }
    list
}

unsafe extern "C" fn scan_line_method(
    _module: *mut PyObject,
    line: *mut PyObject,
) -> *mut PyObject {
    let Some(line) = (unsafe { line_argument(line) }) else {
        return ptr::null_mut();
    };
    unsafe { scan_line_object(&line) }
}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _tokenize_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _tokenize_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _TOKENIZE_RS_MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"scan_line".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunction: scan_line_method,
        },
        ml_flags: METH_O,
        ml_doc: c"Tokenize a supported simple source line.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

struct ModuleSlots([cpython_sys::PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

static _TOKENIZE_RS_MODULE_SLOTS: ModuleSlots = ModuleSlots([
    cpython_sys::PyModuleDef_Slot {
        slot: PY_MOD_EXEC,
        value: module_exec as *const () as *mut c_void,
    },
    cpython_sys::PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    cpython_sys::PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

pub static _TOKENIZE_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_tokenize_rs".as_ptr() as *mut _,
        m_doc: c"Rust simple Python source tokenizer.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_TOKENIZE_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: _TOKENIZE_RS_MODULE_SLOTS.0.as_ptr() as *mut cpython_sys::PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(_tokenize_rs_clear),
        m_free: Some(_tokenize_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__tokenize_rs() -> *mut PyObject {
    _TOKENIZE_RS_MODULE.init_multi_phase()
}
