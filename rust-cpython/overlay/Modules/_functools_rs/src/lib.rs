use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_SetString, PyExc_TypeError, PyLong_FromLong,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, Py_NewRef, PyObject, Py_ssize_t,
};

unsafe extern "C" {
    fn PyObject_CallObject(callable: *mut PyObject, args: *mut PyObject) -> *mut PyObject;
    fn PyObject_RichCompare(left: *mut PyObject, right: *mut PyObject, op: c_int)
        -> *mut PyObject;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
}

unsafe fn compare(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    operation: c_int,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"comparison requires a comparator and two values".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let comparator = unsafe { *args };
    let left = unsafe { *args.add(1) };
    let right = unsafe { *args.add(2) };
    let call_args = unsafe { PyTuple_New(2) };
    if call_args.is_null() {
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(call_args, 0, Py_NewRef(left)) } < 0
        || unsafe { PyTuple_SetItem(call_args, 1, Py_NewRef(right)) } < 0
    {
        unsafe { Py_DecRef(call_args) };
        return ptr::null_mut();
    }

    let result = unsafe { PyObject_CallObject(comparator, call_args) };
    unsafe { Py_DecRef(call_args) };
    if result.is_null() {
        return ptr::null_mut();
    }

    let zero = unsafe { PyLong_FromLong(0) };
    if zero.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    let comparison = unsafe { PyObject_RichCompare(result, zero, operation) };
    unsafe {
        Py_DecRef(result);
        Py_DecRef(zero);
    }
    comparison
}

macro_rules! comparison_method {
    ($name:ident, $operation:expr) => {
        unsafe extern "C" fn $name(
            _module: *mut PyObject,
            args: *mut *mut PyObject,
            nargs: Py_ssize_t,
        ) -> *mut PyObject {
            unsafe { compare(args, nargs, $operation) }
        }
    };
}

comparison_method!(less_than, 0);
comparison_method!(less_equal, 1);
comparison_method!(equal, 2);
comparison_method!(not_equal, 3);
comparison_method!(greater_than, 4);
comparison_method!(greater_equal, 5);

static METHODS: [PyMethodDef; 7] = [
    PyMethodDef {
        ml_name: c"less_than".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: less_than,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply less-than to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"less_equal".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: less_equal,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply less-equal to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"equal".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: equal },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply equality to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"not_equal".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: not_equal,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply inequality to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"greater_than".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: greater_than,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply greater-than to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"greater_equal".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: greater_equal,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Call a three-way comparator and apply greater-equal to its result.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_functools_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust comparison operations for functools ordering helpers.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__functools_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
