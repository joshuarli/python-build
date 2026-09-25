use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_ExceptionMatches;
use cpython_sys::PyErr_Fetch;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_Restore;
use cpython_sys::PyErr_SetNone;
use cpython_sys::PyErr_SetObject;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_FileExistsError;
use cpython_sys::PyExc_PermissionError;
use cpython_sys::PyExc_StopIteration;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyLong_FromLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyNumber_Add;
use cpython_sys::PyObject;
use cpython_sys::PyObject_Call;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_RichCompareBool;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_FromString;
use cpython_sys::Py_ssize_t;
use cpython_sys::Py_IncRef;

struct PyRef(*mut PyObject);

impl PyRef {
    unsafe fn from_owned(object: *mut PyObject) -> Option<Self> {
        (!object.is_null()).then_some(Self(object))
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }

    fn into_raw(mut self) -> *mut PyObject {
        let object = self.0;
        self.0 = ptr::null_mut();
        object
    }
}

impl Drop for PyRef {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

unsafe fn get_attr(object: *mut PyObject, name: &'static [u8]) -> Option<PyRef> {
    let attr = unsafe { PyObject_GetAttrString(object, name.as_ptr().cast()) };
    unsafe { PyRef::from_owned(attr) }
}

unsafe fn tuple_from_borrowed(items: &[*mut PyObject]) -> Option<PyRef> {
    let tuple = unsafe { PyRef::from_owned(PyTuple_New(items.len() as Py_ssize_t)) }?;
    for (index, item) in items.iter().enumerate() {
        unsafe { Py_IncRef(*item) };
        if unsafe { PyTuple_SetItem(tuple.as_ptr(), index as Py_ssize_t, *item) } != 0 {
            return None;
        }
    }
    Some(tuple)
}

unsafe fn call(callable: *mut PyObject, items: &[*mut PyObject]) -> Option<PyRef> {
    let args = unsafe { tuple_from_borrowed(items) }?;
    let result = unsafe { PyObject_Call(callable, args.as_ptr(), ptr::null_mut()) };
    unsafe { PyRef::from_owned(result) }
}

unsafe fn call_next(next: *mut PyObject, names: *mut PyObject) -> Option<PyRef> {
    match unsafe { call(next, &[names]) } {
        Some(value) => Some(value),
        None => {
            if unsafe { PyErr_Occurred() }.is_null() {
                unsafe { PyErr_SetNone(PyExc_StopIteration) };
            }
            None
        }
    }
}

unsafe fn concatenate(
    prefix: *mut PyObject,
    name: *mut PyObject,
    suffix: *mut PyObject,
) -> Option<PyRef> {
    let first = unsafe { PyRef::from_owned(PyNumber_Add(prefix, name)) }?;
    unsafe { PyRef::from_owned(PyNumber_Add(first.as_ptr(), suffix)) }
}

unsafe fn joined_path(
    os_module: *mut PyObject,
    dir: *mut PyObject,
    name: *mut PyObject,
) -> Option<PyRef> {
    let path = unsafe { get_attr(os_module, b"path\0") }?;
    let join = unsafe { get_attr(path.as_ptr(), b"join\0") }?;
    unsafe { call(join.as_ptr(), &[dir, name]) }
}

unsafe fn audit_path(
    sys_module: *mut PyObject,
    event_name: &'static [u8],
    path: *mut PyObject,
) -> bool {
    let event = unsafe { PyRef::from_owned(PyUnicode_FromString(event_name.as_ptr().cast())) };
    let Some(event) = event else {
        return false;
    };
    let Some(audit) = (unsafe { get_attr(sys_module, b"audit\0") }) else {
        return false;
    };
    unsafe { call(audit.as_ptr(), &[event.as_ptr(), path]) }.is_some()
}

struct SavedException {
    kind: *mut PyObject,
    value: *mut PyObject,
    traceback: *mut PyObject,
}

unsafe fn fetch_exception() -> SavedException {
    let mut exception = SavedException {
        kind: ptr::null_mut(),
        value: ptr::null_mut(),
        traceback: ptr::null_mut(),
    };
    unsafe {
        PyErr_Fetch(
            &mut exception.kind,
            &mut exception.value,
            &mut exception.traceback,
        );
    }
    exception
}

unsafe fn discard_exception(exception: SavedException) {
    for object in [exception.kind, exception.value, exception.traceback] {
        if !object.is_null() {
            unsafe { Py_DecRef(object) };
        }
    }
}

unsafe fn restore_exception(exception: SavedException) {
    unsafe { PyErr_Restore(exception.kind, exception.value, exception.traceback) };
}

unsafe fn permission_error_can_retry(
    os_module: *mut PyObject,
    dir: *mut PyObject,
    sequence: i64,
    attempts: i64,
) -> bool {
    let original = unsafe { fetch_exception() };
    let Some(os_name) = (unsafe { get_attr(os_module, b"name\0") }) else {
        unsafe { discard_exception(original) };
        return false;
    };
    let Some(windows_name) = (unsafe { PyRef::from_owned(PyUnicode_FromString(c"nt".as_ptr())) })
    else {
        unsafe { discard_exception(original) };
        return false;
    };
    let is_windows = unsafe { PyObject_RichCompareBool(os_name.as_ptr(), windows_name.as_ptr(), 2) };
    if is_windows < 0 {
        unsafe { discard_exception(original) };
        return false;
    }
    if is_windows == 0 {
        unsafe { restore_exception(original) };
        return false;
    }

    let Some(path) = (unsafe { get_attr(os_module, b"path\0") }) else {
        unsafe { discard_exception(original) };
        return false;
    };
    let Some(isdir) = (unsafe { get_attr(path.as_ptr(), b"isdir\0") }) else {
        unsafe { discard_exception(original) };
        return false;
    };
    let Some(is_directory) = (unsafe { call(isdir.as_ptr(), &[dir]) }) else {
        unsafe { discard_exception(original) };
        return false;
    };
    let is_directory = unsafe { PyObject_IsTrue(is_directory.as_ptr()) };
    if is_directory < 0 {
        unsafe { discard_exception(original) };
        return false;
    }
    if is_directory == 1 && sequence < attempts - 1 {
        unsafe { discard_exception(original) };
        true
    } else {
        unsafe { restore_exception(original) };
        false
    }
}

unsafe fn raise_exhausted(eexist: *mut PyObject, message: &'static [u8]) {
    let Some(message) = (unsafe { PyRef::from_owned(PyUnicode_FromString(message.as_ptr().cast())) })
    else {
        return;
    };
    let Some(args) = (unsafe { tuple_from_borrowed(&[eexist, message.as_ptr()]) }) else {
        return;
    };
    let exception = unsafe { PyObject_Call(PyExc_FileExistsError, args.as_ptr(), ptr::null_mut()) };
    if !exception.is_null() {
        unsafe {
            PyErr_SetObject(PyExc_FileExistsError, exception);
            Py_DecRef(exception);
        }
    }
}

unsafe fn attempts_count(value: *mut PyObject) -> Option<i64> {
    let attempts = unsafe { PyLong_AsLongLong(value) };
    if attempts == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        None
    } else {
        Some(attempts.max(0))
    }
}

unsafe extern "C" fn mkstemp_inner(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 10 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"mkstemp_inner expects 10 arguments".as_ptr());
        }
        return ptr::null_mut();
    }

    let dir = unsafe { argument(args, 0) };
    let prefix = unsafe { argument(args, 1) };
    let suffix = unsafe { argument(args, 2) };
    let flags = unsafe { argument(args, 3) };
    let names = unsafe { argument(args, 4) };
    let os_module = unsafe { argument(args, 5) };
    let sys_module = unsafe { argument(args, 6) };
    let attempts_arg = unsafe { argument(args, 7) };
    let eexist = unsafe { argument(args, 8) };
    let next = unsafe { argument(args, 9) };
    let Some(attempts) = (unsafe { attempts_count(attempts_arg) }) else {
        return ptr::null_mut();
    };
    let Some(mode) = (unsafe { PyRef::from_owned(PyLong_FromLong(0o600)) }) else {
        return ptr::null_mut();
    };

    for sequence in 0..attempts {
        let Some(name) = (unsafe { call_next(next, names) }) else {
            return ptr::null_mut();
        };
        let Some(candidate) = (unsafe { concatenate(prefix, name.as_ptr(), suffix) }) else {
            return ptr::null_mut();
        };
        let Some(path) = (unsafe { joined_path(os_module, dir, candidate.as_ptr()) }) else {
            return ptr::null_mut();
        };
        if !unsafe { audit_path(sys_module, b"tempfile.mkstemp\0", path.as_ptr()) } {
            return ptr::null_mut();
        }

        let Some(open) = (unsafe { get_attr(os_module, b"open\0") }) else {
            return ptr::null_mut();
        };
        let fd_result =
            unsafe { call(open.as_ptr(), &[path.as_ptr(), flags, mode.as_ptr()]) };
        drop(open);
        let Some(fd) = fd_result else {
            if unsafe { PyErr_ExceptionMatches(PyExc_FileExistsError) } != 0 {
                unsafe { PyErr_Clear() };
                continue;
            }
            if unsafe { PyErr_ExceptionMatches(PyExc_PermissionError) } != 0 {
                if unsafe { permission_error_can_retry(os_module, dir, sequence, attempts) } {
                    continue;
                }
            }
            return ptr::null_mut();
        };

        let Some(result) = (unsafe { tuple_from_borrowed(&[fd.as_ptr(), path.as_ptr()]) }) else {
            return ptr::null_mut();
        };
        return result.into_raw();
    }

    unsafe { raise_exhausted(eexist, b"No usable temporary file name found\0") };
    ptr::null_mut()
}

unsafe extern "C" fn mkdtemp(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 9 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"mkdtemp expects 9 arguments".as_ptr());
        }
        return ptr::null_mut();
    }

    let dir = unsafe { argument(args, 0) };
    let prefix = unsafe { argument(args, 1) };
    let suffix = unsafe { argument(args, 2) };
    let names = unsafe { argument(args, 3) };
    let os_module = unsafe { argument(args, 4) };
    let sys_module = unsafe { argument(args, 5) };
    let attempts_arg = unsafe { argument(args, 6) };
    let eexist = unsafe { argument(args, 7) };
    let next = unsafe { argument(args, 8) };
    let Some(attempts) = (unsafe { attempts_count(attempts_arg) }) else {
        return ptr::null_mut();
    };
    let Some(mode) = (unsafe { PyRef::from_owned(PyLong_FromLong(0o700)) }) else {
        return ptr::null_mut();
    };

    for sequence in 0..attempts {
        let Some(name) = (unsafe { call_next(next, names) }) else {
            return ptr::null_mut();
        };
        let Some(candidate) = (unsafe { concatenate(prefix, name.as_ptr(), suffix) }) else {
            return ptr::null_mut();
        };
        let Some(path) = (unsafe { joined_path(os_module, dir, candidate.as_ptr()) }) else {
            return ptr::null_mut();
        };
        if !unsafe { audit_path(sys_module, b"tempfile.mkdtemp\0", path.as_ptr()) } {
            return ptr::null_mut();
        }

        let Some(mkdir) = (unsafe { get_attr(os_module, b"mkdir\0") }) else {
            return ptr::null_mut();
        };
        let created = unsafe { call(mkdir.as_ptr(), &[path.as_ptr(), mode.as_ptr()]) };
        drop(mkdir);
        let Some(created) = created else {
            if unsafe { PyErr_ExceptionMatches(PyExc_FileExistsError) } != 0 {
                unsafe { PyErr_Clear() };
                continue;
            }
            if unsafe { PyErr_ExceptionMatches(PyExc_PermissionError) } != 0 {
                if unsafe { permission_error_can_retry(os_module, dir, sequence, attempts) } {
                    continue;
                }
            }
            return ptr::null_mut();
        };
        drop(created);

        let Some(path_module) = (unsafe { get_attr(os_module, b"path\0") }) else {
            return ptr::null_mut();
        };
        let Some(abspath) = (unsafe { get_attr(path_module.as_ptr(), b"abspath\0") }) else {
            return ptr::null_mut();
        };
        let Some(result) = (unsafe { call(abspath.as_ptr(), &[path.as_ptr()]) }) else {
            return ptr::null_mut();
        };
        return result.into_raw();
    }

    unsafe { raise_exhausted(eexist, b"No usable temporary directory name found\0") };
    ptr::null_mut()
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"mkstemp_inner".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: mkstemp_inner },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a temporary file with exclusive creation.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"mkdtemp".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: mkdtemp },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a temporary directory with exclusive creation.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

struct ModuleSlots([PyModuleDef_Slot; 3]);

unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: 85,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 86,
        value: 2 as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_tempfile_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust temporary file and directory creation loops.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub unsafe extern "C" fn PyInit__tempfile_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
