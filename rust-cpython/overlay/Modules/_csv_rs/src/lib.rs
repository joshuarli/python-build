use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;
use std::str;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyLong_FromLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PySequence_Tuple;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_ssize_t;

fn parse(input: &str) -> Option<Vec<String>> {
    if matches!(input, "" | "\n" | "\r\n") {
        return Some(Vec::new());
    }

    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .from_reader(input.as_bytes());
    let mut record = csv::StringRecord::new();
    match reader.read_record(&mut record) {
        Ok(true) => {}
        Ok(false) => return Some(Vec::new()),
        Err(_) => return None,
    }

    let mut extra = csv::StringRecord::new();
    match reader.read_record(&mut extra) {
        Ok(false) => Some(record.iter().map(str::to_owned).collect()),
        Ok(true) | Err(_) => None,
    }
}

fn serialize(fields: &[String]) -> Option<String> {
    let mut writer = csv::WriterBuilder::new()
        .has_headers(false)
        .terminator(csv::Terminator::CRLF)
        .from_writer(Vec::new());
    writer
        .write_record(fields.iter().map(String::as_str))
        .ok()?;
    String::from_utf8(writer.into_inner().ok()?).ok()
}

unsafe fn unicode_text(value: *mut PyObject) -> Result<String, ()> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(value, &mut length) };
    if data.is_null() {
        return Err(());
    }
    if length < 0 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"CSV text has a negative length".as_ptr(),
            );
        }
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let text = str::from_utf8(bytes).map_err(|_| ())?;
    Ok(text.to_owned())
}

unsafe fn python_text(text: &str) -> *mut PyObject {
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
}

unsafe fn python_fields(fields: &[String]) -> *mut PyObject {
    let result = unsafe { PyList_New(fields.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }

    for (index, field) in fields.iter().enumerate() {
        let value = unsafe { python_text(field) };
        if value.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        let status = unsafe { PyList_SetItem(result, index as Py_ssize_t, value) };
        if status != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

/// Parse one default Excel-dialect record, returning an integer when the row
/// needs CPython's parser to preserve its broader input semantics.
///
/// # Safety
/// `args` is a valid CPython fast-call argument array.
unsafe extern "C" fn parse_record(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"parse_record() takes exactly one argument".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let input = match unsafe { unicode_text(*args) } {
        Ok(input) => input,
        Err(()) => return ptr::null_mut(),
    };
    match parse(&input) {
        Some(fields) => unsafe { python_fields(&fields) },
        None => unsafe { PyLong_FromLong(0) },
    }
}

/// Serialize one row of strings in the default Excel dialect.
///
/// # Safety
/// `args` is a valid CPython fast-call argument array.
unsafe extern "C" fn write_record(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"write_record() takes exactly one argument".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let tuple = unsafe { PySequence_Tuple(*args) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    let size = unsafe { PyTuple_Size(tuple) };
    if size < 0 {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }

    let mut fields = Vec::with_capacity(size as usize);
    for index in 0..size {
        let item = unsafe { PyTuple_GetItem(tuple, index) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        match unsafe { unicode_text(item) } {
            Ok(field) => fields.push(field),
            Err(()) => {
                unsafe { Py_DecRef(tuple) };
                return ptr::null_mut();
            }
        }
    }
    unsafe { Py_DecRef(tuple) };

    match serialize(&fields) {
        Some(text) => unsafe { python_text(&text) },
        None => ptr::null_mut(),
    }
}

pub extern "C" fn csv_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn csv_rs_free(_module: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static CSV_RS_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"parse_record".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_record,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse one supported CSV record.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"write_record".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: write_record,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize one row of strings in the Excel dialect.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static CSV_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_csv_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust CSV record operations.".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: CSV_RS_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(csv_rs_clear),
        m_free: Some(csv_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__csv_rs() -> *mut PyObject {
    CSV_RS_MODULE.init_multi_phase()
}
