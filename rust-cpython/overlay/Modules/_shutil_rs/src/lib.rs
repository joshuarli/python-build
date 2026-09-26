use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::fs;
use std::path::{Path, PathBuf};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyObject;
use cpython_sys::PyObject_CallOneArg;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyObject_CallObject;
use cpython_sys::Py_NewRef;
use cpython_sys::PyList_GetItem;
use cpython_sys::PyList_Size;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;

unsafe fn copyfileobj_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"copyfileobj() takes exactly three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = unsafe { *args };
    let destination = unsafe { *args.add(1) };
    let length = unsafe { *args.add(2) };
    let read = unsafe { PyObject_GetAttrString(source, c"read".as_ptr()) };
    if read.is_null() {
        return ptr::null_mut();
    }
    let write = unsafe { PyObject_GetAttrString(destination, c"write".as_ptr()) };
    if write.is_null() {
        unsafe { Py_DecRef(read) };
        return ptr::null_mut();
    }

    loop {
        let buffer = unsafe { PyObject_CallOneArg(read, length) };
        if buffer.is_null() {
            unsafe {
                Py_DecRef(write);
                Py_DecRef(read);
            }
            return ptr::null_mut();
        }

        let has_data = unsafe { PyObject_IsTrue(buffer) };
        if has_data < 0 {
            unsafe {
                Py_DecRef(buffer);
                Py_DecRef(write);
                Py_DecRef(read);
            }
            return ptr::null_mut();
        }
        if has_data == 0 {
            unsafe { Py_DecRef(buffer) };
            break;
        }

        let result = unsafe { PyObject_CallOneArg(write, buffer) };
        unsafe { Py_DecRef(buffer) };
        if result.is_null() {
            unsafe {
                Py_DecRef(write);
                Py_DecRef(read);
            }
            return ptr::null_mut();
        }
        unsafe { Py_DecRef(result) };
    }

    unsafe {
        Py_DecRef(write);
        Py_DecRef(read);
        Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct))
    }
}

unsafe extern "C" fn copyfileobj(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { copyfileobj_impl(args, nargs) }
}

struct PathPair {
    source: PathBuf,
    destination: PathBuf,
    entry: *mut PyObject,
}

#[derive(Default)]
struct CopyPlan {
    directories: Vec<PathPair>,
    files: Vec<PathPair>,
}

fn python_string(object: *mut PyObject) -> Option<String> {
    let mut length = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let value = unsafe { std::slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    let path = unsafe { std::str::from_utf8_unchecked(value) };
    Some(path.to_owned())
}

unsafe fn collect_copy_plan(
    source: &Path,
    destination: &Path,
    entries: *mut PyObject,
) -> Option<CopyPlan> {
    let count = unsafe { PyList_Size(entries) };
    if count < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let mut plan = CopyPlan::default();
    plan.directories.push(PathPair {
        source: source.to_owned(),
        destination: destination.to_owned(),
        entry: ptr::null_mut(),
    });
    for index in 0..count {
        let entry = unsafe { PyList_GetItem(entries, index) };
        if entry.is_null() {
            unsafe { PyErr_Clear() };
            return None;
        }
        let source_object = unsafe { PyObject_GetAttrString(entry, c"path".as_ptr()) };
        if source_object.is_null() {
            unsafe { PyErr_Clear() };
            return None;
        }
        let name_object = unsafe { PyObject_GetAttrString(entry, c"name".as_ptr()) };
        if name_object.is_null() {
            unsafe { Py_DecRef(source_object) };
            unsafe { PyErr_Clear() };
            return None;
        }
        let source_path = python_string(source_object).map(PathBuf::from);
        let name = python_string(name_object);
        unsafe {
            Py_DecRef(name_object);
            Py_DecRef(source_object);
        }
        let (Some(source_path), Some(name)) = (source_path, name) else {
            return None;
        };
        let Ok(metadata) = fs::symlink_metadata(&source_path) else {
            return None;
        };
        if !metadata.file_type().is_file() {
            return None;
        }
        plan.files.push(PathPair {
            source: source_path,
            destination: destination.join(name),
            entry,
        });
    }
    Some(plan)
}

unsafe fn unicode_path(path: &Path) -> Option<*mut PyObject> {
    let value = path.to_str()?;
    if value.len() > Py_ssize_t::MAX as usize {
        return None;
    }
    let object = unsafe {
        PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t)
    };
    (!object.is_null()).then_some(object)
}

unsafe fn call_two(
    callable: *mut PyObject,
    first: *mut PyObject,
    second: *mut PyObject,
) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, Py_NewRef(first)) } != 0
        || unsafe { PyTuple_SetItem(tuple, 1, Py_NewRef(second)) } != 0
    {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_CallObject(callable, tuple) };
    unsafe { Py_DecRef(tuple) };
    result
}

unsafe fn call_three(
    callable: *mut PyObject,
    first: *mut PyObject,
    second: *mut PyObject,
    third: *mut PyObject,
) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(3) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, Py_NewRef(first)) } != 0
        || unsafe { PyTuple_SetItem(tuple, 1, Py_NewRef(second)) } != 0
        || unsafe { PyTuple_SetItem(tuple, 2, Py_NewRef(third)) } != 0
    {
        unsafe { Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_CallObject(callable, tuple) };
    unsafe { Py_DecRef(tuple) };
    result
}

unsafe fn copytree_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 6 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"copytree() takes exactly six arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source_object = unsafe { *args };
    let destination_object = unsafe { *args.add(1) };
    let copy_function = unsafe { *args.add(2) };
    let copystat_function = unsafe { *args.add(3) };
    let entries = unsafe { *args.add(4) };
    let makedirs_function = unsafe { *args.add(5) };
    let Some(source) = python_string(source_object).map(PathBuf::from) else {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    };
    let Some(destination) = python_string(destination_object).map(PathBuf::from) else {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    };

    if fs::symlink_metadata(&destination).is_ok() {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    }
    let Some(plan) = (unsafe { collect_copy_plan(&source, &destination, entries) }) else {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    };
    if plan.files.is_empty() {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    }

    let made_directory = unsafe { PyObject_CallOneArg(makedirs_function, destination_object) };
    if made_directory.is_null() {
        return ptr::null_mut();
    }
    unsafe { Py_DecRef(made_directory) };

    for file in &plan.files {
        let Some(source_path) = (unsafe { unicode_path(&file.source) }) else {
            return ptr::null_mut();
        };
        let Some(destination_path) = (unsafe { unicode_path(&file.destination) }) else {
            unsafe { Py_DecRef(source_path) };
            return ptr::null_mut();
        };
        let result = unsafe {
            call_three(
                copy_function,
                file.entry,
                source_path,
                destination_path,
            )
        };
        unsafe {
            Py_DecRef(source_path);
            Py_DecRef(destination_path);
        }
        if result.is_null() {
            return ptr::null_mut();
        }
        unsafe { Py_DecRef(result) };
    }

    for directory in plan.directories.iter().rev() {
        let Some(source_path) = (unsafe { unicode_path(&directory.source) }) else {
            return ptr::null_mut();
        };
        let Some(destination_path) = (unsafe { unicode_path(&directory.destination) }) else {
            unsafe { Py_DecRef(source_path) };
            return ptr::null_mut();
        };
        let result = unsafe { call_two(copystat_function, source_path, destination_path) };
        unsafe {
            Py_DecRef(source_path);
            Py_DecRef(destination_path);
        }
        if result.is_null() {
            return ptr::null_mut();
        }
        unsafe { Py_DecRef(result) };
    }

    unsafe { Py_NewRef(destination_object) }
}

unsafe extern "C" fn copytree(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { copytree_impl(args, nargs) }
}

pub extern "C" fn _shutil_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _shutil_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

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

static MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"copyfileobj".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: copyfileobj,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Copy data between file-like objects.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"copytree".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: copytree,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Copy a flat directory of regular files.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_shutil_rs".as_ptr() as *mut _,
        m_doc: c"Rust copy loop for shutil file streams.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: Some(_shutil_rs_clear),
        m_free: Some(_shutil_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__shutil_rs() -> *mut PyObject {
    MODULE.init()
}
