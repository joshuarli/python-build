use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_SetString, PyExc_TypeError, PyList_New, PyList_SetItem,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    PyModuleDef_Slot, PyObject, PyObject_GetAttrString, PyObject_IsInstance, PyTuple_GetItem,
    PyTuple_New, PyTuple_SetItem, PyTuple_Size, Py_NewRef, Py_ssize_t, _Py_NoneStruct,
};

struct Owned(*mut PyObject);

impl Owned {
    fn from_raw(object: *mut PyObject) -> Option<Self> {
        (!object.is_null()).then_some(Self(object))
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }

    fn into_raw(self) -> *mut PyObject {
        let object = self.0;
        std::mem::forget(self);
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

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

unsafe fn get_attr(object: *mut PyObject, name: &'static std::ffi::CStr) -> Result<Owned, ()> {
    Owned::from_raw(unsafe { PyObject_GetAttrString(object, name.as_ptr()) }).ok_or(())
}

unsafe fn is_instance(object: *mut PyObject, classinfo: *mut PyObject) -> Result<bool, ()> {
    match unsafe { PyObject_IsInstance(object, classinfo) } {
        -1 => Err(()),
        0 => Ok(false),
        _ => Ok(true),
    }
}

unsafe fn tuple_size(tuple: *mut PyObject) -> Result<usize, ()> {
    let length = unsafe { PyTuple_Size(tuple) };
    if length < 0 {
        Err(())
    } else {
        Ok(length as usize)
    }
}

unsafe fn tuple_item(tuple: *mut PyObject, index: usize) -> Result<*mut PyObject, ()> {
    if index > isize::MAX as usize {
        return Err(());
    }
    let item = unsafe { PyTuple_GetItem(tuple, index as Py_ssize_t) };
    if item.is_null() {
        Err(())
    } else {
        Ok(item)
    }
}

unsafe fn new_tuple(length: usize) -> Result<Owned, ()> {
    if length > isize::MAX as usize {
        return Err(());
    }
    Owned::from_raw(unsafe { PyTuple_New(length as Py_ssize_t) }).ok_or(())
}

unsafe fn set_tuple_item(
    tuple: *mut PyObject,
    index: usize,
    item: Owned,
) -> Result<(), ()> {
    if index > isize::MAX as usize {
        return Err(());
    }
    let item = item.into_raw();
    if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
        Err(())
    } else {
        Ok(())
    }
}

unsafe fn set_list_item(
    list: *mut PyObject,
    index: usize,
    item: Owned,
) -> Result<(), ()> {
    if index > isize::MAX as usize {
        return Err(());
    }
    let item = item.into_raw();
    if unsafe { PyList_SetItem(list, index as Py_ssize_t, item) } != 0 {
        Err(())
    } else {
        Ok(())
    }
}

unsafe fn tuple_with_first(
    first: Owned,
    rest: *mut PyObject,
) -> Result<Owned, ()> {
    let rest_size = unsafe { tuple_size(rest) }?;
    let result = unsafe { new_tuple(rest_size.checked_add(1).ok_or(())?) }?;
    unsafe { set_tuple_item(result.as_ptr(), 0, first) }?;
    for index in 0..rest_size {
        let item = unsafe { tuple_item(rest, index) }?;
        unsafe { Py_NewRef(item) };
        unsafe { set_tuple_item(result.as_ptr(), index + 1, Owned(item)) }?;
    }
    Ok(result)
}

unsafe fn get_origin(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 6 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"get_origin requires six arguments".as_ptr());
        }
        return ptr::null_mut();
    }

    let (tp, annotated_alias, alias_types, generic, union_type, annotated) = unsafe {
        (
            argument(args, 0),
            argument(args, 1),
            argument(args, 2),
            argument(args, 3),
            argument(args, 4),
            argument(args, 5),
        )
    };

    let annotated_match = match unsafe { is_instance(tp, annotated_alias) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if annotated_match {
        return unsafe { Py_NewRef(annotated) };
    }

    let alias_match = match unsafe { is_instance(tp, alias_types) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if alias_match {
        return match unsafe { get_attr(tp, c"__origin__") } {
            Ok(origin) => origin.into_raw(),
            Err(()) => ptr::null_mut(),
        };
    }

    if tp == generic {
        return unsafe { Py_NewRef(generic) };
    }

    let union_match = match unsafe { is_instance(tp, union_type) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if union_match {
        return unsafe { Py_NewRef(union_type) };
    }

    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct).cast()) }
}

unsafe fn is_param_expr(
    argument: *mut PyObject,
    param_expr_types: *mut PyObject,
    ellipsis: *mut PyObject,
) -> Result<bool, ()> {
    if argument == ellipsis {
        return Ok(true);
    }
    unsafe { is_instance(argument, param_expr_types) }
}

unsafe fn unflatten_callable_args(
    args: *mut PyObject,
    param_expr_types: *mut PyObject,
    ellipsis: *mut PyObject,
) -> Result<Option<Owned>, ()> {
    let length = unsafe { tuple_size(args) }?;
    if length == 0 {
        return Ok(None);
    }
    if length == 2 {
        let first = unsafe { tuple_item(args, 0) }?;
        if unsafe { is_param_expr(first, param_expr_types, ellipsis) }? {
            return Ok(Some(unsafe { Owned::from_raw(Py_NewRef(args)) }.ok_or(())?));
        }
    }

    let list = Owned::from_raw(unsafe { PyList_New((length - 1) as Py_ssize_t) }).ok_or(())?;
    for index in 0..length - 1 {
        let item = unsafe { tuple_item(args, index) }?;
        unsafe { Py_NewRef(item) };
        unsafe { set_list_item(list.as_ptr(), index, Owned(item)) }?;
    }

    let result = unsafe { new_tuple(2) }?;
    unsafe { set_tuple_item(result.as_ptr(), 0, list) }?;
    let last = unsafe { tuple_item(args, length - 1) }?;
    unsafe { Py_NewRef(last) };
    unsafe { set_tuple_item(result.as_ptr(), 1, Owned(last)) }?;

    Ok(Some(result))
}

unsafe fn get_args(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 7 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"get_args requires seven arguments".as_ptr());
        }
        return ptr::null_mut();
    }

    let (tp, annotated_alias, generic_alias_types, union_type, callable_origin,
         param_expr_types, ellipsis) = unsafe {
        (
            argument(args, 0),
            argument(args, 1),
            argument(args, 2),
            argument(args, 3),
            argument(args, 4),
            argument(args, 5),
            argument(args, 6),
        )
    };

    let annotated_match = match unsafe { is_instance(tp, annotated_alias) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if annotated_match {
        let origin = match unsafe { get_attr(tp, c"__origin__") } {
            Ok(origin) => origin,
            Err(()) => return ptr::null_mut(),
        };
        let metadata = match unsafe { get_attr(tp, c"__metadata__") } {
            Ok(metadata) => metadata,
            Err(()) => return ptr::null_mut(),
        };
        return match unsafe { tuple_with_first(origin, metadata.as_ptr()) } {
            Ok(result) => result.into_raw(),
            Err(()) => ptr::null_mut(),
        };
    }

    let generic_alias_match = match unsafe { is_instance(tp, generic_alias_types) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if generic_alias_match {
        let type_args = match unsafe { get_attr(tp, c"__args__") } {
            Ok(type_args) => type_args,
            Err(()) => return ptr::null_mut(),
        };
        let origin = match unsafe { get_attr(tp, c"__origin__") } {
            Ok(origin) => origin,
            Err(()) => return ptr::null_mut(),
        };
        if origin.as_ptr() == callable_origin {
            match unsafe {
                unflatten_callable_args(
                    type_args.as_ptr(),
                    param_expr_types,
                    ellipsis,
                )
            } {
                Ok(Some(result)) => return result.into_raw(),
                Ok(None) => return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct).cast()) },
                Err(()) => return ptr::null_mut(),
            }
        }
        return type_args.into_raw();
    }

    let union_match = match unsafe { is_instance(tp, union_type) } {
        Ok(matches) => matches,
        Err(()) => return ptr::null_mut(),
    };
    if union_match {
        return match unsafe { get_attr(tp, c"__args__") } {
            Ok(type_args) => type_args.into_raw(),
            Err(()) => ptr::null_mut(),
        };
    }

    match unsafe { new_tuple(0) } {
        Ok(empty) => empty.into_raw(),
        Err(()) => ptr::null_mut(),
    }
}

unsafe extern "C" fn get_origin_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { get_origin(args, nargs) }
}

unsafe extern "C" fn get_args_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { get_args(args, nargs) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"get_origin".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: get_origin_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Get the runtime origin of a typing alias.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"get_args".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: get_args_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Get the runtime type arguments of a typing alias.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

struct ModuleSlots(UnsafeCell<[PyModuleDef_Slot; 2]>);

impl ModuleSlots {
    const fn as_mut_ptr(&self) -> *mut PyModuleDef_Slot {
        self.0.get().cast::<PyModuleDef_Slot>()
    }
}

unsafe impl Sync for ModuleSlots {}

static MODULE_SLOTS: ModuleSlots = ModuleSlots(UnsafeCell::new([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: 2usize as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]));

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_typing_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust runtime operations for typing aliases.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: MODULE_SLOTS.as_mut_ptr(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__typing_rs() -> *mut PyObject {
    MODULE.init()
}
