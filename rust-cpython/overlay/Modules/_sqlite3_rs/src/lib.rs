use std::cell::UnsafeCell;
use std::ffi::{c_char, c_double, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBytes_FromStringAndSize, PyErr_NoMemory, PyErr_Occurred, PyErr_SetString,
    PyFloat_FromDouble, PyLong_AsLong, PyLong_FromLong, PyLong_FromLongLong,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_Slot, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, PyObject, PyUnicode_FromStringAndSize, Py_NewRef,
    Py_ssize_t, _Py_NoneStruct,
};

const SQLITE_INTEGER: c_int = 1;
const SQLITE_FLOAT: c_int = 2;
const SQLITE_TEXT: c_int = 3;
const SQLITE_BLOB: c_int = 4;
const SQLITE_NULL: c_int = 5;
const SQLITE_NOMEM: c_int = 7;

unsafe extern "C" {
    fn PyLong_AsVoidPtr(value: *mut PyObject) -> *mut c_void;
    fn PyEval_SaveThread() -> *mut c_void;
    fn PyEval_RestoreThread(thread: *mut c_void);
}

// Opaque SQLite handles retain the C extension's ownership and lifetime.
enum SqliteStatement {}
enum SqliteDatabase {}

#[repr(C)]
#[derive(Clone, Copy)]
struct ApiHeader {
    version: u32,
    size: usize,
}

#[repr(C)]
#[derive(Clone, Copy)]
struct SqliteApi {
    header: ApiHeader,
    step: Option<unsafe extern "C" fn(*mut SqliteStatement) -> c_int>,
    column_type: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> c_int>,
    column_int64: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> i64>,
    column_double: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> c_double>,
    column_text: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> *const u8>,
    column_blob: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> *const c_void>,
    column_bytes: Option<unsafe extern "C" fn(*mut SqliteStatement, c_int) -> c_int>,
    errcode: Option<unsafe extern "C" fn(*mut SqliteDatabase) -> c_int>,
}

unsafe extern "C" {
    fn PyCapsule_Import(name: *const c_char, no_block: c_int) -> *mut c_void;
    fn PyModule_GetState(module: *mut PyObject) -> *mut c_void;
}

// Module state contains only copied native pointers, never Python objects.
// A failed execution leaves its zero-initialized function fields unbound.
unsafe fn module_api(module: *mut PyObject) -> Option<SqliteApi> {
    let state = unsafe { PyModule_GetState(module) }.cast::<SqliteApi>();
    if state.is_null() {
        return None;
    }
    let api = unsafe { *state };
    if api.step.is_none() {
        unsafe { PyErr_SetString(cpython_sys::PyExc_RuntimeError,
                                 c"SQLite native API is not initialized".as_ptr()) };
        return None;
    }
    Some(api)
}

/// Step the statement with the GIL released so SQLite callbacks can re-enter Python.
///
/// # Safety
/// The C cursor supplies a live statement pointer and a valid fast-call array.
unsafe extern "C" fn step(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe { PyErr_SetString(cpython_sys::PyExc_TypeError, c"step() expects one argument".as_ptr()) };
        return ptr::null_mut();
    }
    let statement = unsafe { PyLong_AsVoidPtr(*args) };
    if statement.is_null() && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let Some(api) = (unsafe { module_api(module) }) else { return ptr::null_mut(); };
    let thread = unsafe { PyEval_SaveThread() };
    let code = unsafe { (api.step.unwrap())(statement.cast()) };
    unsafe { PyEval_RestoreThread(thread) };
    unsafe { PyLong_FromLong(code.into()) }
}

/// Convert an ordinary SQLite column while the cursor owns its current row.
/// Converter callbacks and nondefault text factories remain at the C cursor boundary.
///
/// # Safety
/// The C cursor supplies live statement/database pointers and a valid column index.
unsafe extern "C" fn column(
    module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe { PyErr_SetString(cpython_sys::PyExc_TypeError, c"column() expects three arguments".as_ptr()) };
        return ptr::null_mut();
    }
    let statement = unsafe { PyLong_AsVoidPtr(*args) };
    if statement.is_null() {
        return ptr::null_mut();
    }
    let index = unsafe { PyLong_AsLong(*args.add(1)) };
    if index < 0 || index > c_int::MAX as _ {
        return ptr::null_mut();
    }
    let database = unsafe { PyLong_AsVoidPtr(*args.add(2)) };
    if database.is_null() {
        return ptr::null_mut();
    }
    let index = index as c_int;
    let Some(api) = (unsafe { module_api(module) }) else { return ptr::null_mut(); };
    match unsafe { (api.column_type.unwrap())(statement.cast(), index) } {
        SQLITE_NULL => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
        SQLITE_INTEGER => unsafe { PyLong_FromLongLong((api.column_int64.unwrap())(statement.cast(), index)) },
        SQLITE_FLOAT => unsafe { PyFloat_FromDouble((api.column_double.unwrap())(statement.cast(), index)) },
        SQLITE_TEXT => {
            let data = unsafe { (api.column_text.unwrap())(statement.cast(), index) };
            if data.is_null() && unsafe { (api.errcode.unwrap())(database.cast()) } == SQLITE_NOMEM {
                unsafe { PyErr_NoMemory() };
                return ptr::null_mut();
            }
            let size = unsafe { (api.column_bytes.unwrap())(statement.cast(), index) };
            unsafe { PyUnicode_FromStringAndSize(data.cast::<c_char>(), size as Py_ssize_t) }
        }
        SQLITE_BLOB => {
            let data = unsafe { (api.column_blob.unwrap())(statement.cast(), index) };
            if data.is_null() && unsafe { (api.errcode.unwrap())(database.cast()) } == SQLITE_NOMEM {
                unsafe { PyErr_NoMemory() };
                return ptr::null_mut();
            }
            let size = unsafe { (api.column_bytes.unwrap())(statement.cast(), index) };
            unsafe { PyBytes_FromStringAndSize(data.cast::<c_char>(), size as Py_ssize_t) }
        }
        _ => {
            unsafe { PyErr_SetString(cpython_sys::PyExc_RuntimeError, c"unknown SQLite column type".as_ptr()) };
            ptr::null_mut()
        }
    }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);
unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);
unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(module: *mut PyObject) -> c_int {
    let pointer = unsafe { PyCapsule_Import(c"_sqlite3._RUST_API".as_ptr(), 0) };
    if pointer.is_null() {
        return -1;
    }
    let header = unsafe { *pointer.cast::<ApiHeader>() };
    if header.version != 1 || header.size != std::mem::size_of::<SqliteApi>() {
        unsafe { PyErr_SetString(cpython_sys::PyExc_ImportError,
                                 c"incompatible SQLite native API".as_ptr()) };
        return -1;
    }
    let api = unsafe { *pointer.cast::<SqliteApi>() };
    if api.step.is_none() || api.column_type.is_none() || api.column_int64.is_none()
        || api.column_double.is_none() || api.column_text.is_none()
        || api.column_blob.is_none() || api.column_bytes.is_none() || api.errcode.is_none()
    {
        unsafe { PyErr_SetString(cpython_sys::PyExc_ImportError,
                                 c"incomplete SQLite native API".as_ptr()) };
        return -1;
    }
    let state = unsafe { PyModule_GetState(module) }.cast::<SqliteApi>();
    if state.is_null() {
        return -1;
    }
    unsafe { ptr::write(state, api) };
    0
}

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

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"step".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: step },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Advance a SQLite statement.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"column".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: column },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Convert a SQLite column.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_sqlite3_rs".as_ptr() as *mut c_char,
    m_doc: c"SQLite cursor operations.".as_ptr() as *mut c_char,
    m_size: std::mem::size_of::<SqliteApi>() as Py_ssize_t,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__sqlite3_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
