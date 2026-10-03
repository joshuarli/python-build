use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyDict_SetItem;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::Py_IncRef;
use cpython_sys::PyIter_Next;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_GetIter;
use cpython_sys::Py_ssize_t;

struct OwnedPyObject(*mut PyObject);

impl Drop for OwnedPyObject {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

unsafe fn insert_field(destination: *mut PyObject, field: *mut PyObject) -> bool {
    let name = OwnedPyObject(unsafe {
        PyObject_GetAttrString(field, c"name".as_ptr() as *const c_char)
    });
    if name.0.is_null() {
        return false;
    }
    unsafe { PyDict_SetItem(destination, name.0, field) == 0 }
}

unsafe fn return_destination(destination: *mut PyObject) -> *mut PyObject {
    unsafe { Py_IncRef(destination) };
    destination
}

unsafe fn raise_arity_error(name: &'static std::ffi::CStr) {
    let message = match name.to_bytes() {
        b"merge_fields" => c"merge_fields() takes exactly 2 arguments",
        _ => c"set_field() takes exactly 2 arguments",
    };
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

unsafe extern "C" fn merge_fields(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { raise_arity_error(c"merge_fields") };
        return ptr::null_mut();
    }

    let destination = unsafe { *args };
    let inherited_values = unsafe { *args.add(1) };
    let iterator = OwnedPyObject(unsafe { PyObject_GetIter(inherited_values) });
    if iterator.0.is_null() {
        return ptr::null_mut();
    }

    loop {
        let field = OwnedPyObject(unsafe { PyIter_Next(iterator.0) });
        if field.0.is_null() {
            if unsafe { !PyErr_Occurred().is_null() } {
                return ptr::null_mut();
            }
            break;
        }
        if !unsafe { insert_field(destination, field.0) } {
            return ptr::null_mut();
        }
    }

    unsafe { return_destination(destination) }
}

unsafe extern "C" fn set_field(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { raise_arity_error(c"set_field") };
        return ptr::null_mut();
    }

    let destination = unsafe { *args };
    let field = unsafe { *args.add(1) };
    if !unsafe { insert_field(destination, field) } {
        return ptr::null_mut();
    }
    unsafe { return_destination(destination) }
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
        ml_name: c"merge_fields".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: merge_fields,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Merge inherited dataclass fields in iteration order".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"set_field".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: set_field,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Insert one dataclass field into the ordered field map".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_dataclasses_rs".as_ptr() as *mut _,
        m_doc: c"Rust support for ordered dataclass field processing".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__dataclasses_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
