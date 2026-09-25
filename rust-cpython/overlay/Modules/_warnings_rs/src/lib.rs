use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyErr_Clear, PyErr_SetString, PyExc_TypeError, PyExc_ValueError,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    PyObject, PyObject_CallOneArg, PyObject_GetAttrString, PyObject_IsTrue, Py_ssize_t,
    Py_DecRef, Py_IncRef, PyLong_FromLong,
};

unsafe extern "C" {
    fn PyErr_ExceptionMatches(exception: *mut PyObject) -> c_int;
    fn PyObject_CallFunctionObjArgs(callable: *mut PyObject, ...) -> *mut PyObject;
    fn PyObject_Format(value: *mut PyObject, format_spec: *mut PyObject) -> *mut PyObject;
    fn PySequence_Contains(sequence: *mut PyObject, value: *mut PyObject) -> c_int;
    fn PyUnicode_Concat(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    fn PyUnicode_FromString(value: *const c_char) -> *mut PyObject;
}

struct Owned(*mut PyObject);

impl Owned {
    unsafe fn from_new_reference(object: *mut PyObject) -> Option<Self> {
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

impl Drop for Owned {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

fn argument(args: *mut *mut PyObject, nargs: Py_ssize_t, index: Py_ssize_t) -> *mut PyObject {
    if index < nargs {
        unsafe { *args.offset(index) }
    } else {
        ptr::null_mut()
    }
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

unsafe fn call_method_one(
    object: *mut PyObject,
    method_name: &'static std::ffi::CStr,
    argument: *mut PyObject,
) -> *mut PyObject {
    let method = unsafe { PyObject_GetAttrString(object, method_name.as_ptr()) };
    let Some(method) = (unsafe { Owned::from_new_reference(method) }) else {
        return ptr::null_mut();
    };
    unsafe { PyObject_CallOneArg(method.as_ptr(), argument) }
}

unsafe fn add_filter(
    filters: *mut PyObject,
    item: *mut PyObject,
    append: bool,
) -> *mut PyObject {
    if append {
        let contains = unsafe { PySequence_Contains(filters, item) };
        if contains < 0 {
            return ptr::null_mut();
        }
        if contains == 0 {
            let result = unsafe { call_method_one(filters, c"append", item) };
            if result.is_null() {
                return ptr::null_mut();
            }
            unsafe { Py_DecRef(result) };
        }
    } else {
        let removed = unsafe { call_method_one(filters, c"remove", item) };
        if removed.is_null() {
            if unsafe { PyErr_ExceptionMatches(PyExc_ValueError) } != 1 {
                return ptr::null_mut();
            }
            unsafe { PyErr_Clear() };
        } else {
            unsafe { Py_DecRef(removed) };
        }

        let insert = unsafe { PyObject_GetAttrString(filters, c"insert".as_ptr()) };
        let Some(insert) = (unsafe { Owned::from_new_reference(insert) }) else {
            return ptr::null_mut();
        };
        let index = unsafe { PyLong_FromLong(0) };
        let Some(index) = (unsafe { Owned::from_new_reference(index) }) else {
            return ptr::null_mut();
        };
        let inserted = unsafe {
            PyObject_CallFunctionObjArgs(
                insert.as_ptr(),
                index.as_ptr(),
                item,
                ptr::null_mut::<PyObject>(),
            )
        };
        if inserted.is_null() {
            return ptr::null_mut();
        }
        unsafe { Py_DecRef(inserted) };
    }

    let none = ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct);
    unsafe { Py_IncRef(none) };
    none
}

unsafe extern "C" fn add_filter_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        return type_error(c"add_filter() takes exactly 3 arguments");
    }
    let filters = argument(args, nargs, 0);
    let item = argument(args, nargs, 1);
    let append = argument(args, nargs, 2);
    let append = unsafe { PyObject_IsTrue(append) };
    if append < 0 {
        return ptr::null_mut();
    }
    unsafe { add_filter(filters, item, append != 0) }
}

unsafe fn format_field(value: *mut PyObject) -> Option<Owned> {
    let empty = unsafe { PyUnicode_FromString(c"".as_ptr()) };
    let empty = unsafe { Owned::from_new_reference(empty) }?;
    let formatted = unsafe { PyObject_Format(value, empty.as_ptr()) };
    unsafe { Owned::from_new_reference(formatted) }
}

unsafe fn format_piece(value: &'static std::ffi::CStr) -> Option<Owned> {
    let text = unsafe { PyUnicode_FromString(value.as_ptr()) };
    unsafe { Owned::from_new_reference(text) }
}

unsafe fn concatenate(left: Owned, right: Owned) -> Option<Owned> {
    let result = unsafe { PyUnicode_Concat(left.as_ptr(), right.as_ptr()) };
    unsafe { Owned::from_new_reference(result) }
}

unsafe fn append_literal(current: Owned, literal: &'static std::ffi::CStr) -> Option<Owned> {
    let piece = unsafe { format_piece(literal) }?;
    unsafe { concatenate(current, piece) }
}

unsafe fn append_formatted(current: Owned, value: *mut PyObject) -> Option<Owned> {
    let piece = unsafe { format_field(value) }?;
    unsafe { concatenate(current, piece) }
}

unsafe fn append_attribute(
    current: Owned,
    object: *mut PyObject,
    name: &'static std::ffi::CStr,
) -> Option<Owned> {
    let value = unsafe { PyObject_GetAttrString(object, name.as_ptr()) };
    let value = unsafe { Owned::from_new_reference(value) }?;
    unsafe { append_formatted(current, value.as_ptr()) }
}

unsafe extern "C" fn format_message_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"format_message() takes exactly 2 arguments");
    }

    let warning_message = argument(args, nargs, 0);
    let category = argument(args, nargs, 1);

    let filename = unsafe { PyObject_GetAttrString(warning_message, c"filename".as_ptr()) };
    let Some(filename) = (unsafe { Owned::from_new_reference(filename) }) else {
        return ptr::null_mut();
    };
    let Some(formatted_filename) = (unsafe { format_field(filename.as_ptr()) }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_literal(formatted_filename, c":") }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_attribute(current, warning_message, c"lineno") }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_literal(current, c": ") }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_formatted(current, category) }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_literal(current, c": ") }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_attribute(current, warning_message, c"message") }) else {
        return ptr::null_mut();
    };
    let Some(current) = (unsafe { append_literal(current, c"\n") }) else {
        return ptr::null_mut();
    };
    current.into_raw()
}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn module_clear(_module: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn module_free(_module: *mut c_void) {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"add_filter".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: add_filter_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Apply the warnings filter list insertion semantics.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"format_message".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: format_message_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Format the first line of a warning message.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

#[repr(C)]
struct ModuleSlot {
    slot: c_int,
    value: *mut c_void,
}

unsafe impl Sync for ModuleSlot {}

struct ModuleSlots([ModuleSlot; 3]);

unsafe impl Sync for ModuleSlots {}

const PY_MOD_EXEC: c_int = 85;
const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2 as *mut c_void;

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    ModuleSlot {
        slot: PY_MOD_EXEC,
        value: module_exec as *const () as *mut c_void,
    },
    ModuleSlot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    ModuleSlot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_warnings_rs".as_ptr() as *mut _,
        m_doc: c"Rust support for Python warning filtering and display.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut _,
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__warnings_rs() -> *mut PyObject {
    MODULE.init()
}
