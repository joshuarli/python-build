use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use configparser::ini::{Ini, WriteOptions};
use cpython_sys::METH_FASTCALL;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::Py_NewRef;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

fn python_string(value: *mut PyObject) -> Option<String> {
    let mut size = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(value, &mut size) };
    if data.is_null() || size < 0 {
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    Some(String::from_utf8(bytes.to_vec()).expect("CPython UTF-8 is valid"))
}

fn normalize(
    source: &str,
    default_section: &str,
    space_around_delimiters: bool,
    trailing_blank_line: bool,
) -> Option<String> {
    let mut ini = Ini::new_cs();
    ini.set_default_section(default_section);
    // CPython treats comment markers inside option values as literal text.
    ini.set_inline_comment_symbols(Some(&[]));
    ini.read(source.to_owned()).ok()?;

    let has_defaults = ini
        .get_map_ref()
        .get(default_section)
        .is_some_and(|options| !options.is_empty());
    let options = WriteOptions::new_with_params(space_around_delimiters, 4, 1);
    let mut output = ini.pretty_writes(&options);

    if has_defaults {
        output.insert_str(0, &format!("[{default_section}]\n"));
    }
    if trailing_blank_line && !output.is_empty() {
        output.push('\n');
    }
    Some(output)
}

unsafe fn unicode_result(value: &str) -> *mut PyObject {
    unsafe {
        PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t)
    }
}

unsafe fn none_result() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn parse_ini(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"parse_ini() takes exactly two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = match python_string(unsafe { *args }) {
        Some(value) => value,
        None => return ptr::null_mut(),
    };
    let default_section = match python_string(unsafe { *args.add(1) }) {
        Some(value) => value,
        None => return ptr::null_mut(),
    };

    match normalize(&source, &default_section, false, false) {
        Some(output) => unsafe { unicode_result(&output) },
        None => unsafe { none_result() },
    }
}

unsafe extern "C" fn write_ini(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"write_ini() takes exactly three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = match python_string(unsafe { *args }) {
        Some(value) => value,
        None => return ptr::null_mut(),
    };
    let default_section = match python_string(unsafe { *args.add(1) }) {
        Some(value) => value,
        None => return ptr::null_mut(),
    };
    let spaced = unsafe { PyObject_IsTrue(*args.add(2)) };
    if spaced < 0 {
        return ptr::null_mut();
    }

    match normalize(&source, &default_section, spaced != 0, true) {
        Some(output) => unsafe { unicode_result(&output) },
        None => unsafe { none_result() },
    }
}

pub extern "C" fn _configparser_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _configparser_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _CONFIGPARSER_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"parse_ini".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_ini,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse and normalize a supported INI document".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"write_ini".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: write_ini,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a supported INI document".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _CONFIGPARSER_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_configparser_rs".as_ptr() as *mut _,
        m_doc: c"Rust INI parsing and serialization".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_CONFIGPARSER_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_configparser_rs_clear),
        m_free: Some(_configparser_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__configparser_rs() -> *mut PyObject {
    _CONFIGPARSER_RS_MODULE.init_multi_phase()
}
