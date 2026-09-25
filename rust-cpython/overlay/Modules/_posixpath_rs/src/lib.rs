use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::METH_O;
use cpython_sys::PyBytes_AsStringAndSize;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::PyUnicode_New;
use cpython_sys::PyUnicode_ReadChar;
use cpython_sys::PyUnicode_WriteChar;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_ssize_t;

unsafe extern "C" {
    fn PyOS_FSPath(object: *mut PyObject) -> *mut PyObject;
}

enum Path {
    Text(Vec<u32>),
    Bytes(Vec<u8>),
}

unsafe fn path_from_fspath(object: *mut PyObject) -> Result<Path, ()> {
    let value = unsafe { PyOS_FSPath(object) };
    if value.is_null() {
        return Err(());
    }
    let path = unsafe { Path::from_object(value) };
    unsafe { Py_DecRef(value) };
    path
}

impl Path {
    unsafe fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let length = unsafe { PyUnicode_GetLength(object) };
        if length >= 0 {
            let mut value = Vec::with_capacity(length as usize);
            for index in 0..length {
                let character = unsafe { PyUnicode_ReadChar(object, index) };
                if character > 0x10ffff {
                    return Err(());
                }
                value.push(character);
            }
            return Ok(Self::Text(value));
        }

        unsafe { PyErr_Clear() };
        let mut data = ptr::null_mut::<c_char>();
        let mut length = 0;
        if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 {
            return Err(());
        }
        if length < 0 {
            return Err(());
        }
        let value = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
        Ok(Self::Bytes(value.to_vec()))
    }

    fn into_object(self) -> *mut PyObject {
        match self {
            Self::Text(value) => text_object(&value),
            Self::Bytes(value) => bytes_object(&value),
        }
    }

    fn normpath(self) -> Self {
        match self {
            Self::Text(value) => Self::Text(normpath_units(&value, b'/' as u32, b'.' as u32)),
            Self::Bytes(value) => Self::Bytes(normpath_units(&value, b'/', b'.')),
        }
    }

    fn split(self) -> (Self, Self) {
        match self {
            Self::Text(value) => {
                let (head, tail) = split_units(&value, b'/' as u32);
                (Self::Text(head), Self::Text(tail))
            }
            Self::Bytes(value) => {
                let (head, tail) = split_units(&value, b'/');
                (Self::Bytes(head), Self::Bytes(tail))
            }
        }
    }

    fn splitroot(self) -> (Self, Self, Self) {
        match self {
            Self::Text(value) => {
                let (drive, root, tail) = splitroot_units(&value, b'/' as u32);
                (Self::Text(drive), Self::Text(root), Self::Text(tail))
            }
            Self::Bytes(value) => {
                let (drive, root, tail) = splitroot_units(&value, b'/');
                (Self::Bytes(drive), Self::Bytes(root), Self::Bytes(tail))
            }
        }
    }

    fn splitext(self) -> (Self, Self) {
        match self {
            Self::Text(value) => {
                let (root, ext) = splitext_units(&value, b'/' as u32, b'.' as u32);
                (Self::Text(root), Self::Text(ext))
            }
            Self::Bytes(value) => {
                let (root, ext) = splitext_units(&value, b'/', b'.');
                (Self::Bytes(root), Self::Bytes(ext))
            }
        }
    }
}

fn text_object(value: &[u32]) -> *mut PyObject {
    let max_character = value.iter().copied().max().unwrap_or(0);
    let result = unsafe { PyUnicode_New(value.len() as Py_ssize_t, max_character) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, character) in value.iter().copied().enumerate() {
        if unsafe { PyUnicode_WriteChar(result, index as Py_ssize_t, character) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

fn bytes_object(value: &[u8]) -> *mut PyObject {
    let data = if value.is_empty() {
        ptr::null()
    } else {
        value.as_ptr().cast::<c_char>()
    };
    unsafe { PyBytes_FromStringAndSize(data, value.len() as Py_ssize_t) }
}

fn return_paths(paths: Vec<Path>) -> *mut PyObject {
    let result = unsafe { PyTuple_New(paths.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, path) in paths.into_iter().enumerate() {
        let item = path.into_object();
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

fn normpath_units<T: Copy + PartialEq>(path: &[T], separator: T, dot: T) -> Vec<T> {
    if path.is_empty() {
        return vec![dot];
    }

    let root_length = root_length(path, separator);
    let root = &path[..root_length];
    let mut components = Vec::<Vec<T>>::new();
    let mut start = root_length;
    for index in root_length..=path.len() {
        if index != path.len() && path[index] != separator {
            continue;
        }
        let component = &path[start..index];
        start = index + 1;
        if component.is_empty() || (component.len() == 1 && component[0] == dot) {
            continue;
        }
        if component.len() == 2 && component[0] == dot && component[1] == dot {
            let relative_leading_parent = root.is_empty() && components.is_empty();
            let repeated_parent = components.last().is_some_and(|last| {
                last.len() == 2 && last[0] == dot && last[1] == dot
            });
            if relative_leading_parent || repeated_parent {
                components.push(component.to_vec());
            } else {
                components.pop();
            }
        } else {
            components.push(component.to_vec());
        }
    }

    let component_length = components.iter().map(Vec::len).sum::<usize>();
    let separator_count = components.len().saturating_sub(1);
    let mut result = Vec::with_capacity(root.len() + component_length + separator_count);
    result.extend_from_slice(root);
    for (index, component) in components.iter().enumerate() {
        if index != 0 {
            result.push(separator);
        }
        result.extend_from_slice(component);
    }
    if result.is_empty() {
        vec![dot]
    } else {
        result
    }
}

fn root_length<T: Copy + PartialEq>(path: &[T], separator: T) -> usize {
    if path.first() != Some(&separator) {
        return 0;
    }
    // Preserve a root of exactly two slashes; collapse longer runs to one.
    if path.get(1) == Some(&separator)
        && (path.len() == 2 || path.get(2) != Some(&separator))
    {
        2
    } else {
        1
    }
}

fn split_units<T: Copy + PartialEq>(path: &[T], separator: T) -> (Vec<T>, Vec<T>) {
    let split_at = path
        .iter()
        .rposition(|character| *character == separator)
        .map_or(0, |index| index + 1);
    let mut head = path[..split_at].to_vec();
    if !head.is_empty() && !head.iter().all(|character| *character == separator) {
        while head.last() == Some(&separator) {
            head.pop();
        }
    }
    (head, path[split_at..].to_vec())
}

fn splitroot_units<T: Copy + PartialEq>(path: &[T], separator: T) -> (Vec<T>, Vec<T>, Vec<T>) {
    let root_length = root_length(path, separator);
    if root_length == 0 {
        return (Vec::new(), Vec::new(), path.to_vec());
    }
    (
        Vec::new(),
        path[..root_length].to_vec(),
        path[root_length..].to_vec(),
    )
}

fn splitext_units<T: Copy + PartialEq>(path: &[T], separator: T, dot: T) -> (Vec<T>, Vec<T>) {
    let separator_index = path
        .iter()
        .rposition(|character| *character == separator);
    let dot_index = path.iter().rposition(|character| *character == dot);
    if let Some(dot_index) = dot_index {
        if separator_index.is_none_or(|index| dot_index > index) {
            let filename_start = separator_index.map_or(0, |index| index + 1);
            if path[filename_start..dot_index]
                .iter()
                .any(|character| *character != dot)
            {
                return (path[..dot_index].to_vec(), path[dot_index..].to_vec());
            }
        }
    }
    (path.to_vec(), Vec::new())
}

fn join_units<T: Copy + PartialEq>(left: &[T], right: &[T], separator: T) -> Vec<T> {
    if right.first() == Some(&separator) || left.is_empty() {
        return right.to_vec();
    }
    let mut result = Vec::with_capacity(left.len() + right.len() + 1);
    result.extend_from_slice(left);
    if left.last() != Some(&separator) {
        result.push(separator);
    }
    result.extend_from_slice(right);
    result
}

fn join_pair(left: Path, right: Path) -> Result<Path, ()> {
    match (left, right) {
        (Path::Text(left), Path::Text(right)) => {
            Ok(Path::Text(join_units(&left, &right, b'/' as u32)))
        }
        (Path::Bytes(left), Path::Bytes(right)) => Ok(Path::Bytes(join_units(&left, &right, b'/'))),
        _ => Err(()),
    }
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { cpython_sys::PyErr_SetString(cpython_sys::PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

unsafe extern "C" fn normpath(
    _module: *mut PyObject,
    object: *mut PyObject,
) -> *mut PyObject {
    match unsafe { path_from_fspath(object) } {
        Ok(path) => path.normpath().into_object(),
        Err(()) => ptr::null_mut(),
    }
}

unsafe extern "C" fn join_pair_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"join_pair() takes exactly two arguments");
    }
    let left = match unsafe { path_from_fspath(argument(args, 0)) } {
        Ok(path) => path,
        Err(()) => return ptr::null_mut(),
    };
    let right = match unsafe { path_from_fspath(argument(args, 1)) } {
        Ok(path) => path,
        Err(()) => return ptr::null_mut(),
    };
    match join_pair(left, right) {
        Ok(path) => path.into_object(),
        Err(()) => type_error(c"path components must have the same type"),
    }
}

unsafe extern "C" fn split(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"split() takes exactly one argument");
    }
    match unsafe { path_from_fspath(argument(args, 0)) } {
        Ok(path) => {
            let (head, tail) = path.split();
            return_paths(vec![head, tail])
        }
        Err(()) => ptr::null_mut(),
    }
}

unsafe extern "C" fn splitroot(
    _module: *mut PyObject,
    object: *mut PyObject,
) -> *mut PyObject {
    match unsafe { path_from_fspath(object) } {
        Ok(path) => {
            let (drive, root, tail) = path.splitroot();
            return_paths(vec![drive, root, tail])
        }
        Err(()) => ptr::null_mut(),
    }
}

unsafe extern "C" fn splitext(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"splitext() takes exactly one argument");
    }
    match unsafe { path_from_fspath(argument(args, 0)) } {
        Ok(path) => {
            let (root, ext) = path.splitext();
            return_paths(vec![root, ext])
        }
        Err(()) => ptr::null_mut(),
    }
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

static MODULE_METHODS: [PyMethodDef; 6] = [
    PyMethodDef {
        ml_name: c"_path_normpath".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: normpath },
        ml_flags: METH_O,
        ml_doc: c"_path_normpath($module, /, path)\n--\n\nNormalize path, eliminating double slashes, etc.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"join_pair".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: join_pair_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Join one POSIX path component.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"split".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: split },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split a POSIX path into head and tail.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_path_splitroot_ex".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: splitroot },
        ml_flags: METH_O,
        ml_doc: c"_path_splitroot_ex($module, /, p)\n--\n\nSplit a pathname into drive, root and tail.\n\nThe tail contains anything after the root.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"splitext".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: splitext },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split a POSIX path extension.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_posixpath_rs".as_ptr() as *mut _,
        m_doc: c"Rust POSIX path lexical operations.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__posixpath_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
