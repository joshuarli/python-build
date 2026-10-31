use core::cell::UnsafeCell;
use core::ffi::{CStr, c_int};
use core::ptr;

use crate::ffi::{
    METH_FASTCALL, METH_NOARGS, METH_O, PyCFunction, PyCFunctionFast, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_Base, PyModuleDef_Init, PyModuleDef_Slot,
    PyObject, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED, Py_mod_multiple_interpreters,
    STATIC_IMMORTAL_REFCNT,
};

pub const fn fastcall(
    name: &'static CStr,
    function: PyCFunctionFast,
    doc: &'static CStr,
) -> PyMethodDef {
    method(
        name,
        PyMethodDefFuncPointer {
            PyCFunctionFast: function,
        },
        METH_FASTCALL,
        doc,
    )
}

pub const fn single_argument(
    name: &'static CStr,
    function: PyCFunction,
    doc: &'static CStr,
) -> PyMethodDef {
    method(
        name,
        PyMethodDefFuncPointer {
            PyCFunction: function,
        },
        METH_O,
        doc,
    )
}

pub const fn noargs(name: &'static CStr, function: PyCFunction, doc: &'static CStr) -> PyMethodDef {
    method(
        name,
        PyMethodDefFuncPointer {
            PyCFunction: function,
        },
        METH_NOARGS,
        doc,
    )
}

const fn method(
    name: &'static CStr,
    function: PyMethodDefFuncPointer,
    flags: c_int,
    doc: &'static CStr,
) -> PyMethodDef {
    PyMethodDef {
        ml_name: name.as_ptr(),
        ml_meth: function,
        ml_flags: flags,
        ml_doc: doc.as_ptr(),
    }
}

/// The sentinel that ends a method table.
pub const fn method_table_end() -> PyMethodDef {
    PyMethodDef {
        ml_name: ptr::null(),
        ml_meth: PyMethodDefFuncPointer {
            void: ptr::null_mut(),
        },
        ml_flags: 0,
        ml_doc: ptr::null(),
    }
}

/// Slots that declare support for subinterpreters with their own GIL.
pub static PER_INTERPRETER_GIL: [PyModuleDef_Slot; 2] = [
    PyModuleDef_Slot {
        slot: Py_mod_multiple_interpreters,
        value: Py_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
];

/// A statically allocated multi-phase module definition.
pub struct Module(UnsafeCell<PyModuleDef>);

unsafe impl Sync for Module {}

impl Module {
    /// `methods` ends with [`method_table_end`].
    pub const fn new(
        name: &'static CStr,
        doc: &'static CStr,
        methods: &'static [PyMethodDef],
    ) -> Self {
        Self(UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_Base {
                ob_base: PyObject {
                    ob_refcnt: STATIC_IMMORTAL_REFCNT,
                    ob_type: ptr::null_mut(),
                },
                m_init: None,
                m_index: 0,
                m_copy: ptr::null_mut(),
            },
            m_name: name.as_ptr(),
            m_doc: doc.as_ptr(),
            m_size: 0,
            m_methods: methods.as_ptr().cast_mut(),
            m_slots: ptr::null_mut(),
            m_traverse: None,
            m_clear: None,
            m_free: None,
        }))
    }

    /// `slots` ends with a zero slot.
    pub const fn with_slots(self, slots: &'static [PyModuleDef_Slot]) -> Self {
        let mut definition = self.0.into_inner();
        definition.m_slots = slots.as_ptr().cast_mut();
        Self(UnsafeCell::new(definition))
    }

    pub fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}
