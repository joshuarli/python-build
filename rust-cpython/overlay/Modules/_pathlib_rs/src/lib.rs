use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyLong_AsInt;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_ssize_t;
use typed_path::{Utf8UnixComponent, Utf8UnixPath};

struct ParsedPath {
    drive: String,
    root: String,
    parts: Vec<String>,
}

const PATH_CHECK_EXISTS: c_int = 0;
const PATH_CHECK_IS_DIR: c_int = 1;
const PATH_CHECK_IS_FILE: c_int = 2;

fn parse_unix_path(path: &str) -> ParsedPath {
    let bytes = path.as_bytes();
    let (root, relative) = if path.starts_with("//") && bytes.get(2) != Some(&b'/') {
        ("//", &path[2..])
    } else if path.starts_with('/') {
        let root_end = bytes.iter().take_while(|byte| **byte == b'/').count();
        ("/", &path[root_end..])
    } else {
        ("", path)
    };

    let parts = Utf8UnixPath::new(relative)
        .components()
        .filter_map(|component| match component {
            Utf8UnixComponent::Normal(part) => Some(part.to_owned()),
            Utf8UnixComponent::ParentDir => Some("..".to_owned()),
            Utf8UnixComponent::RootDir | Utf8UnixComponent::CurDir => None,
        })
        .collect();

    ParsedPath {
        drive: String::new(),
        root: root.to_owned(),
        parts,
    }
}

fn parse_windows_path(path: &str) -> ParsedPath {
    let normalized = path.replace('/', "\\");
    let bytes = normalized.as_bytes();
    let (drive, root, relative) = if normalized.starts_with("\\\\") {
        let unc_prefix = normalized
            .get(..8)
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case("\\\\?\\UNC\\"));
        let start = if unc_prefix { 8 } else { 2 };
        let first_separator = normalized[start..]
            .find('\\')
            .map(|offset| start + offset);
        match first_separator {
            None => (normalized.clone(), "", ""),
            Some(first_separator) => {
                let second_separator = normalized[first_separator + 1..]
                    .find('\\')
                    .map(|offset| first_separator + 1 + offset);
                match second_separator {
                    None => (normalized.clone(), "", ""),
                    Some(second_separator) => (
                        normalized[..second_separator].to_owned(),
                        "\\",
                        &normalized[second_separator + 1..],
                    ),
                }
            }
        }
    } else if normalized.starts_with('\\') {
        (String::new(), "\\", &normalized[1..])
    } else if bytes.get(1) == Some(&b':') {
        if bytes.get(2) == Some(&b'\\') {
            (normalized[..2].to_owned(), "\\", &normalized[3..])
        } else {
            (normalized[..2].to_owned(), "", &normalized[2..])
        }
    } else {
        (String::new(), "", normalized.as_str())
    };
    // Drive and root syntax has already been removed, so only separators are
    // structural in the remaining tail. A colon is part of a path component.
    let component_path = relative.replace('\\', "/");
    let parts = Utf8UnixPath::new(&component_path)
        .components()
        .filter_map(|component| match component {
            Utf8UnixComponent::Normal(part) => Some(part.to_owned()),
            Utf8UnixComponent::ParentDir => Some("..".to_owned()),
            Utf8UnixComponent::RootDir | Utf8UnixComponent::CurDir => None,
        })
        .collect();

    // A complete UNC share is an anchor even without a trailing separator.
    let mut root = root.to_owned();
    if root.is_empty() && drive.starts_with('\\') && !drive.ends_with('\\') {
        let drive_parts: Vec<_> = drive.split('\\').collect();
        if (drive_parts.len() == 4 && !matches!(drive_parts[2], "?" | "."))
            || drive_parts.len() == 6
        {
            root.push('\\');
        }
    }

    ParsedPath { drive, root, parts }
}

fn unicode_object(value: &str) -> *mut PyObject {
    if value.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t)
    }
}

fn string_list(values: &[String]) -> *mut PyObject {
    if values.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let result = unsafe { PyList_New(values.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, value) in values.iter().enumerate() {
        let item = unicode_object(value);
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

fn parsed_path_tuple(parsed: ParsedPath) -> *mut PyObject {
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let drive = unicode_object(&parsed.drive);
    if drive.is_null() || unsafe { PyTuple_SetItem(result, 0, drive) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    let root = unicode_object(&parsed.root);
    if root.is_null() || unsafe { PyTuple_SetItem(result, 1, root) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    let parts = string_list(&parsed.parts);
    if parts.is_null() || unsafe { PyTuple_SetItem(result, 2, parts) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    result
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

unsafe extern "C" fn parse_path(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"parse_path() takes exactly two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let path_object = unsafe { argument(args, 0) };
    let mut path_len = 0;
    let path_ptr = unsafe { PyUnicode_AsUTF8AndSize(path_object, &mut path_len) };
    if path_ptr.is_null() {
        return ptr::null_mut();
    }
    if path_len < 0 {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let path_bytes = unsafe { std::slice::from_raw_parts(path_ptr.cast::<u8>(), path_len as usize) };
    let path = match std::str::from_utf8(path_bytes) {
        Ok(path) => path,
        Err(_) => {
            unsafe { PyErr_SetString(PyExc_TypeError, c"path must be valid Unicode".as_ptr()) };
            return ptr::null_mut();
        }
    };

    let windows = unsafe { PyObject_IsTrue(argument(args, 1)) };
    if windows < 0 {
        return ptr::null_mut();
    }
    let parsed = if windows != 0 {
        parse_windows_path(path)
    } else {
        parse_unix_path(path)
    };
    parsed_path_tuple(parsed)
}

unsafe extern "C" fn path_check(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"path_check() takes exactly three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let path_object = unsafe { argument(args, 0) };
    let mut path_len = 0;
    let path_ptr = unsafe { PyUnicode_AsUTF8AndSize(path_object, &mut path_len) };
    if path_ptr.is_null() {
        return ptr::null_mut();
    }
    if path_len < 0 {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let path_bytes = unsafe { std::slice::from_raw_parts(path_ptr.cast::<u8>(), path_len as usize) };
    let path = match std::str::from_utf8(path_bytes) {
        Ok(path) => path,
        Err(_) => {
            unsafe { PyErr_SetString(PyExc_TypeError, c"path must be valid Unicode".as_ptr()) };
            return ptr::null_mut();
        }
    };

    let operation = unsafe { PyLong_AsInt(argument(args, 1)) };
    let error = unsafe { PyErr_Occurred() };
    if !error.is_null() {
        return ptr::null_mut();
    }
    if !matches!(operation, PATH_CHECK_EXISTS | PATH_CHECK_IS_DIR | PATH_CHECK_IS_FILE) {
        unsafe {
            PyErr_SetString(PyExc_ValueError, c"unknown path check operation".as_ptr());
        }
        return ptr::null_mut();
    }

    let follow_symlinks = unsafe { PyObject_IsTrue(argument(args, 2)) };
    if follow_symlinks < 0 {
        return ptr::null_mut();
    }
    let metadata = if follow_symlinks != 0 {
        std::fs::metadata(path)
    } else {
        std::fs::symlink_metadata(path)
    };
    let result = match metadata {
        Ok(metadata) => match operation {
            PATH_CHECK_EXISTS => true,
            PATH_CHECK_IS_DIR => metadata.is_dir(),
            PATH_CHECK_IS_FILE => metadata.is_file(),
            _ => unreachable!(),
        },
        Err(_) => false,
    };
    unsafe { PyBool_FromLong(if result { 1 } else { 0 }) }
}

extern "C" fn module_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn module_free(_module: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"parse_path".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: parse_path },
        ml_flags: METH_FASTCALL,
        ml_doc: c"parse_path($module, path, windows, /)\n--\n\nParse a pathlib lexical path.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"path_check".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: path_check },
        ml_flags: METH_FASTCALL,
        ml_doc: c"path_check($module, path, operation, follow_symlinks, /)\n--\n\nCheck whether a filesystem path exists or has a requested type.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

// Each parse call owns its state; the module shares only immutable method data.
static MODULE_SLOTS: ModuleSlots = ModuleSlots([
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

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_pathlib_rs".as_ptr() as *mut _,
        m_doc: c"Rust lexical path parsing for pathlib.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__pathlib_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
