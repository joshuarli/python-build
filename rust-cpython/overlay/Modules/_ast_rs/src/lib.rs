use std::cell::UnsafeCell;
use std::collections::VecDeque;
use std::ffi::{c_char, CString};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyErr_Clear, PyErr_ExceptionMatches, PyErr_Occurred, PyErr_SetString,
    PyExc_AttributeError, PyExc_TypeError, PyImport_ImportModule, PyIter_Next, PyList_Append,
    PyList_New, PyList_Type, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, Py_NewRef, PyObject, PyObject_CallOneArg,
    PyObject_DelAttr, PyObject_GetAttr, PyObject_GetAttrString, PyObject_GetIter,
    PyObject_IsInstance, PyObject_SetAttr, PyObject_SetItem, PySlice_New, PyTuple_New,
    PyTuple_SetItem, PyUnicode_Concat, PyUnicode_FromString, Py_ssize_t, _Py_NoneStruct,
};

struct Owned(*mut PyObject);

impl Owned {
    unsafe fn from_owned(object: *mut PyObject) -> Option<Self> {
        if object.is_null() {
            None
        } else {
            Some(Self(object))
        }
    }

    unsafe fn from_borrowed(object: *mut PyObject) -> Option<Self> {
        if object.is_null() {
            None
        } else {
            Self::from_owned(unsafe { Py_NewRef(object) })
        }
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }

}

impl Drop for Owned {
    fn drop(&mut self) {
        unsafe { cpython_sys::Py_DecRef(self.0) };
    }
}

unsafe fn ast_type() -> Option<Owned> {
    let module = unsafe { Owned::from_owned(PyImport_ImportModule(c"ast".as_ptr())) }?;
    unsafe { Owned::from_owned(PyObject_GetAttrString(module.as_ptr(), c"AST".as_ptr())) }
}

unsafe fn is_instance(object: *mut PyObject, class: *mut PyObject) -> Result<bool, ()> {
    let result = unsafe { PyObject_IsInstance(object, class) };
    if result < 0 {
        Err(())
    } else {
        Ok(result != 0)
    }
}

unsafe fn is_ast(object: *mut PyObject, class: *mut PyObject) -> Result<bool, ()> {
    unsafe { is_instance(object, class) }
}

unsafe fn is_list(object: *mut PyObject) -> Result<bool, ()> {
    unsafe { is_instance(object, ptr::addr_of_mut!(PyList_Type).cast()) }
}

unsafe fn next_field(
    node: *mut PyObject,
    fields: *mut PyObject,
) -> Result<Option<(Owned, Owned)>, ()> {
    loop {
        let field = unsafe { PyIter_Next(fields) };
        if field.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                return Ok(None);
            }
            return Err(());
        }
        let field = Owned(field);
        let value = unsafe { PyObject_GetAttr(node, field.as_ptr()) };
        if value.is_null() {
            if unsafe { PyErr_ExceptionMatches(PyExc_AttributeError) } != 0 {
                unsafe { PyErr_Clear() };
                continue;
            }
            return Err(());
        }
        return Ok(Some((field, Owned(value))));
    }
}

unsafe fn for_each_field(
    node: *mut PyObject,
    mut visit: impl FnMut(&Owned, &Owned) -> bool,
) -> Result<(), ()> {
    let fields = unsafe { Owned::from_owned(PyObject_GetAttrString(node, c"_fields".as_ptr())) }
        .ok_or(())?;
    let fields = unsafe { Owned::from_owned(PyObject_GetIter(fields.as_ptr())) }.ok_or(())?;
    while let Some((field, value)) = unsafe { next_field(node, fields.as_ptr()) }? {
        if !visit(&field, &value) {
            return Err(());
        }
    }
    Ok(())
}

unsafe fn list_iterator(list: Owned) -> *mut PyObject {
    let iterator = unsafe { PyObject_GetIter(list.as_ptr()) };
    iterator
}

unsafe fn iter_fields_impl(node: *mut PyObject) -> *mut PyObject {
    let fields = match unsafe { Owned::from_owned(PyList_New(0)) } {
        Some(fields) => fields,
        None => return ptr::null_mut(),
    };
    if unsafe {
        for_each_field(node, |field, value| {
            let tuple = match Owned::from_owned(PyTuple_New(2)) {
                Some(tuple) => tuple,
                None => return false,
            };
            let name = unsafe { Py_NewRef(field.as_ptr()) };
            if unsafe { PyTuple_SetItem(tuple.as_ptr(), 0, name) } != 0 {
                unsafe { cpython_sys::Py_DecRef(name) };
                return false;
            }
            let field_value = unsafe { Py_NewRef(value.as_ptr()) };
            if unsafe { PyTuple_SetItem(tuple.as_ptr(), 1, field_value) } != 0 {
                unsafe { cpython_sys::Py_DecRef(field_value) };
                return false;
            }
            unsafe { PyList_Append(fields.as_ptr(), tuple.as_ptr()) == 0 }
        })
    }
    .is_err()
    {
        return ptr::null_mut();
    }
    unsafe { list_iterator(fields) }
}

unsafe fn iter_child_nodes_impl(node: *mut PyObject) -> *mut PyObject {
    let ast = match unsafe { ast_type() } {
        Some(ast) => ast,
        None => return ptr::null_mut(),
    };
    let children = match unsafe { Owned::from_owned(PyList_New(0)) } {
        Some(children) => children,
        None => return ptr::null_mut(),
    };
    let result = unsafe {
        for_each_field(node, |_, value| {
            match unsafe { is_ast(value.as_ptr(), ast.as_ptr()) } {
                Ok(true) => return unsafe { PyList_Append(children.as_ptr(), value.as_ptr()) == 0 },
                Ok(false) => {}
                Err(()) => return false,
            }
            match unsafe { is_list(value.as_ptr()) } {
                Ok(false) => true,
                Err(()) => false,
                Ok(true) => {
                    let iterator = match Owned::from_owned(unsafe { PyObject_GetIter(value.as_ptr()) }) {
                        Some(iterator) => iterator,
                        None => return false,
                    };
                    loop {
                        let item = unsafe { PyIter_Next(iterator.as_ptr()) };
                        if item.is_null() {
                            return unsafe { PyErr_Occurred() }.is_null();
                        }
                        let item = Owned(item);
                        match unsafe { is_ast(item.as_ptr(), ast.as_ptr()) } {
                            Ok(true) => {
                                if unsafe { PyList_Append(children.as_ptr(), item.as_ptr()) } != 0 {
                                    return false;
                                }
                            }
                            Ok(false) => {}
                            Err(()) => return false,
                        }
                    }
                }
            }
        })
    };
    if result.is_err() {
        return ptr::null_mut();
    }
    unsafe { list_iterator(children) }
}

unsafe fn walk_impl(node: *mut PyObject) -> *mut PyObject {
    let ast = match unsafe { ast_type() } {
        Some(ast) => ast,
        None => return ptr::null_mut(),
    };
    let mut pending = VecDeque::new();
    let Some(root) = (unsafe { Owned::from_borrowed(node) }) else {
        return ptr::null_mut();
    };
    pending.push_back(root);
    let result = match unsafe { Owned::from_owned(PyList_New(0)) } {
        Some(result) => result,
        None => return ptr::null_mut(),
    };
    while let Some(current) = pending.pop_front() {
        if unsafe { PyList_Append(result.as_ptr(), current.as_ptr()) } != 0 {
            return ptr::null_mut();
        }
        let children = match unsafe {
            Owned::from_owned(iter_child_nodes_impl(current.as_ptr()))
        } {
            Some(children) => children,
            None => return ptr::null_mut(),
        };
        loop {
            let child = unsafe { PyIter_Next(children.as_ptr()) };
            if child.is_null() {
                if unsafe { PyErr_Occurred() }.is_null() {
                    break;
                }
                return ptr::null_mut();
            }
            let child = Owned(child);
            if unsafe { is_ast(child.as_ptr(), ast.as_ptr()) } != Ok(true) {
                if unsafe { PyErr_Occurred() }.is_null() {
                    continue;
                }
                return ptr::null_mut();
            }
            pending.push_back(child);
        }
    }
    unsafe { list_iterator(result) }
}

unsafe fn visit_one(visitor: *mut PyObject, node: *mut PyObject) -> Option<Owned> {
    let method = unsafe { Owned::from_owned(PyObject_GetAttrString(visitor, c"visit".as_ptr())) }?;
    unsafe { Owned::from_owned(PyObject_CallOneArg(method.as_ptr(), node)) }
}

unsafe fn visit_impl(visitor: *mut PyObject, node: *mut PyObject) -> *mut PyObject {
    let class = match unsafe { Owned::from_owned(PyObject_GetAttrString(node, c"__class__".as_ptr())) }
    {
        Some(class) => class,
        None => return ptr::null_mut(),
    };
    let class_name = match unsafe {
        Owned::from_owned(PyObject_GetAttrString(class.as_ptr(), c"__name__".as_ptr()))
    } {
        Some(name) => name,
        None => return ptr::null_mut(),
    };
    let prefix = match unsafe { Owned::from_owned(PyUnicode_FromString(c"visit_".as_ptr())) } {
        Some(prefix) => prefix,
        None => return ptr::null_mut(),
    };
    let method_name = match unsafe {
        Owned::from_owned(PyUnicode_Concat(prefix.as_ptr(), class_name.as_ptr()))
    } {
        Some(method_name) => method_name,
        None => return ptr::null_mut(),
    };
    let generic = match unsafe {
        Owned::from_owned(PyObject_GetAttrString(visitor, c"generic_visit".as_ptr()))
    } {
        Some(generic) => generic,
        None => return ptr::null_mut(),
    };
    let method = unsafe { PyObject_GetAttr(visitor, method_name.as_ptr()) };
    let method = if method.is_null() {
        if unsafe { PyErr_ExceptionMatches(PyExc_AttributeError) } == 0 {
            return ptr::null_mut();
        }
        unsafe { PyErr_Clear() };
        generic
    } else {
        Owned(method)
    };
    unsafe { PyObject_CallOneArg(method.as_ptr(), node) }
}

unsafe fn visitor_generic_visit_impl(visitor: *mut PyObject, node: *mut PyObject) -> *mut PyObject {
    let ast = match unsafe { ast_type() } {
        Some(ast) => ast,
        None => return ptr::null_mut(),
    };
    let result = unsafe {
        for_each_field(node, |_, value| {
            match unsafe { is_ast(value.as_ptr(), ast.as_ptr()) } {
                Ok(true) => return unsafe { visit_one(visitor, value.as_ptr()).is_some() },
                Ok(false) => {}
                Err(()) => return false,
            }
            match unsafe { is_list(value.as_ptr()) } {
                Ok(false) => true,
                Err(()) => false,
                Ok(true) => {
                    let iterator = match Owned::from_owned(unsafe { PyObject_GetIter(value.as_ptr()) }) {
                        Some(iterator) => iterator,
                        None => return false,
                    };
                    loop {
                        let item = unsafe { PyIter_Next(iterator.as_ptr()) };
                        if item.is_null() {
                            return unsafe { PyErr_Occurred() }.is_null();
                        }
                        let item = Owned(item);
                        match unsafe { is_ast(item.as_ptr(), ast.as_ptr()) } {
                            Ok(true) => {
                                if unsafe { visit_one(visitor, item.as_ptr()) }.is_none() {
                                    return false;
                                }
                            }
                            Ok(false) => {}
                            Err(()) => return false,
                        }
                    }
                }
            }
        })
    };
    if result.is_err() {
        return ptr::null_mut();
    }
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe fn transformer_generic_visit_impl(
    visitor: *mut PyObject,
    node: *mut PyObject,
) -> *mut PyObject {
    let ast = match unsafe { ast_type() } {
        Some(ast) => ast,
        None => return ptr::null_mut(),
    };
    let result = unsafe {
        for_each_field(node, |field, value| {
            match unsafe { is_list(value.as_ptr()) } {
                Ok(true) => {
                    let new_values = match Owned::from_owned(unsafe { PyList_New(0) }) {
                        Some(values) => values,
                        None => return false,
                    };
                    let iterator = match Owned::from_owned(unsafe { PyObject_GetIter(value.as_ptr()) }) {
                        Some(iterator) => iterator,
                        None => return false,
                    };
                    loop {
                        let item = unsafe { PyIter_Next(iterator.as_ptr()) };
                        if item.is_null() {
                            if !unsafe { PyErr_Occurred() }.is_null() {
                                return false;
                            }
                            break;
                        }
                        let item = Owned(item);
                        match unsafe { is_ast(item.as_ptr(), ast.as_ptr()) } {
                            Ok(true) => {
                                let replacement = match unsafe { visit_one(visitor, item.as_ptr()) } {
                                    Some(replacement) => replacement,
                                    None => return false,
                                };
                                if replacement.as_ptr() == ptr::addr_of_mut!(_Py_NoneStruct).cast() {
                                    continue;
                                }
                                match unsafe { is_ast(replacement.as_ptr(), ast.as_ptr()) } {
                                    Ok(true) => {
                                        if unsafe {
                                            PyList_Append(new_values.as_ptr(), replacement.as_ptr())
                                        } != 0
                                        {
                                            return false;
                                        }
                                    }
                                    Ok(false) => {
                                        let extend = match Owned::from_owned(unsafe {
                                            PyObject_GetAttrString(new_values.as_ptr(), c"extend".as_ptr())
                                        }) {
                                            Some(extend) => extend,
                                            None => return false,
                                        };
                                        if unsafe {
                                            Owned::from_owned(PyObject_CallOneArg(
                                                extend.as_ptr(),
                                                replacement.as_ptr(),
                                            ))
                                        }
                                        .is_none()
                                        {
                                            return false;
                                        }
                                    }
                                    Err(()) => return false,
                                }
                            }
                            Ok(false) => {
                                if unsafe { PyList_Append(new_values.as_ptr(), item.as_ptr()) } != 0 {
                                    return false;
                                }
                            }
                            Err(()) => return false,
                        }
                    }
                    let none = ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>();
                    let all_items = unsafe { PySlice_New(none, none, none) };
                    if all_items.is_null() {
                        return false;
                    }
                    let all_items = Owned(all_items);
                    unsafe {
                        PyObject_SetItem(value.as_ptr(), all_items.as_ptr(), new_values.as_ptr()) == 0
                    }
                }
                Ok(false) => match unsafe { is_ast(value.as_ptr(), ast.as_ptr()) } {
                    Ok(false) => true,
                    Err(()) => false,
                    Ok(true) => {
                        let replacement = match unsafe { visit_one(visitor, value.as_ptr()) } {
                            Some(replacement) => replacement,
                            None => return false,
                        };
                        if replacement.as_ptr() == ptr::addr_of_mut!(_Py_NoneStruct).cast() {
                            unsafe { PyObject_DelAttr(node, field.as_ptr()) == 0 }
                        } else {
                            unsafe {
                                PyObject_SetAttr(node, field.as_ptr(), replacement.as_ptr()) == 0
                            }
                        }
                    }
                },
                Err(()) => false,
            }
        })
    };
    if result.is_err() {
        return ptr::null_mut();
    }
    unsafe { Py_NewRef(node) }
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

unsafe fn check_arity(operation: &str, nargs: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if nargs == expected {
        return true;
    }
    let message = format!("{operation} expected {expected} arguments, got {nargs}");
    if let Ok(message) = CString::new(message) {
        unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    }
    false
}

unsafe extern "C" fn iter_fields(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("iter_fields", nargs, 1) } {
        return ptr::null_mut();
    }
    unsafe { iter_fields_impl(argument(args, 0)) }
}

unsafe extern "C" fn iter_child_nodes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("iter_child_nodes", nargs, 1) } {
        return ptr::null_mut();
    }
    unsafe { iter_child_nodes_impl(argument(args, 0)) }
}

unsafe extern "C" fn walk(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("walk", nargs, 1) } {
        return ptr::null_mut();
    }
    unsafe { walk_impl(argument(args, 0)) }
}

unsafe extern "C" fn visit(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("visit", nargs, 2) } {
        return ptr::null_mut();
    }
    unsafe { visit_impl(argument(args, 0), argument(args, 1)) }
}

unsafe extern "C" fn visitor_generic_visit(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("visitor_generic_visit", nargs, 2) } {
        return ptr::null_mut();
    }
    unsafe { visitor_generic_visit_impl(argument(args, 0), argument(args, 1)) }
}

unsafe extern "C" fn transformer_generic_visit(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity("transformer_generic_visit", nargs, 2) } {
        return ptr::null_mut();
    }
    unsafe { transformer_generic_visit_impl(argument(args, 0), argument(args, 1)) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 7] = [
    PyMethodDef {
        ml_name: c"iter_fields".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: iter_fields },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return an iterator over AST field names and values.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"iter_child_nodes".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: iter_child_nodes },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return an iterator over direct AST child nodes.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"walk".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: walk },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return an iterator over an AST in breadth-first order.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"visit".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: visit },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Dispatch an AST node to a visitor method.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"visitor_generic_visit".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: visitor_generic_visit,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Visit each AST child without modifying the tree.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"transformer_generic_visit".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: transformer_generic_visit,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Visit children and apply AST replacements and removals.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_ast_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust AST traversal and transformation helpers.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__ast_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
