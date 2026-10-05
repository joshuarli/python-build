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

#[link(name = "sqlite3")]
unsafe extern "C" {
    fn sqlite3_step(statement: *mut c_void) -> c_int;
    fn sqlite3_column_type(statement: *mut c_void, column: c_int) -> c_int;
    fn sqlite3_column_int64(statement: *mut c_void, column: c_int) -> i64;
    fn sqlite3_column_double(statement: *mut c_void, column: c_int) -> c_double;
    fn sqlite3_column_text(statement: *mut c_void, column: c_int) -> *const u8;
    fn sqlite3_column_blob(statement: *mut c_void, column: c_int) -> *const c_void;
    fn sqlite3_column_bytes(statement: *mut c_void, column: c_int) -> c_int;
    fn sqlite3_errcode(database: *mut c_void) -> c_int;
}

/// Step the statement with the GIL released so SQLite callbacks can re-enter Python.
///
/// # Safety
/// The C cursor supplies a live statement pointer and a valid fast-call array.
unsafe extern "C" fn step(
    _module: *mut PyObject,
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
    let thread = unsafe { PyEval_SaveThread() };
    let code = unsafe { sqlite3_step(statement) };
    unsafe { PyEval_RestoreThread(thread) };
    unsafe { PyLong_FromLong(code.into()) }
}

/// Convert an ordinary SQLite column while the cursor owns its current row.
/// Converter callbacks and nondefault text factories remain at the C cursor boundary.
///
/// # Safety
/// The C cursor supplies live statement/database pointers and a valid column index.
unsafe extern "C" fn column(
    _module: *mut PyObject,
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
    match unsafe { sqlite3_column_type(statement, index) } {
        SQLITE_NULL => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
        SQLITE_INTEGER => unsafe { PyLong_FromLongLong(sqlite3_column_int64(statement, index)) },
        SQLITE_FLOAT => unsafe { PyFloat_FromDouble(sqlite3_column_double(statement, index)) },
        SQLITE_TEXT => {
            let data = unsafe { sqlite3_column_text(statement, index) };
            if data.is_null() && unsafe { sqlite3_errcode(database) } == SQLITE_NOMEM {
                unsafe { PyErr_NoMemory() };
                return ptr::null_mut();
            }
            let size = unsafe { sqlite3_column_bytes(statement, index) };
            unsafe { PyUnicode_FromStringAndSize(data.cast::<c_char>(), size as Py_ssize_t) }
        }
        SQLITE_BLOB => {
            let data = unsafe { sqlite3_column_blob(statement, index) };
            if data.is_null() && unsafe { sqlite3_errcode(database) } == SQLITE_NOMEM {
                unsafe { PyErr_NoMemory() };
                return ptr::null_mut();
            }
            let size = unsafe { sqlite3_column_bytes(statement, index) };
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

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
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
    m_size: 0,
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
