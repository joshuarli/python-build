use std::cell::UnsafeCell;
use std::ffi::c_char;
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyDict_New, PyDict_SetItemString, PyErr_Clear,
    PyErr_ExceptionMatches, PyErr_Occurred, PyErr_SetNone, PyErr_SetObject, PyErr_SetString,
    PyExc_AttributeError, PyExc_StopIteration, PyExc_TypeError, Py_IncRef,
    Py_EnterRecursiveCall, Py_LeaveRecursiveCall, PyIter_Next, PyList_Append, PyList_New,
    PyMethodDef, PyMethodDefFuncPointer,
    PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject,
    PyObject_Call, PyObject_CallOneArg, PyObject_GetAttrString, PyObject_GetIter,
    PyObject_RichCompareBool, PyTuple_GetItem, PyTuple_New, PyTuple_SetItem,
    PyTuple_Size, PyUnicode_FromString, Py_ssize_t,
};

struct OwnedPyObject(*mut PyObject);

impl OwnedPyObject {
    unsafe fn from_new_reference(object: *mut PyObject) -> Option<Self> {
        if object.is_null() {
            None
        } else {
            Some(Self(object))
        }
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }
}

impl Drop for OwnedPyObject {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) };
    }
}

// Keep path conversion lazy: Python only converts later descendants when the
// Traversable algorithm consumes them or builds its missing-target error.
struct SegmentIter {
    path_names: *mut PyObject,
    path_count: Py_ssize_t,
    path_index: Py_ssize_t,
    resources_abc: *mut PyObject,
    pure_posix_path: Option<OwnedPyObject>,
    parts: Option<OwnedPyObject>,
}

impl SegmentIter {
    unsafe fn new(
        path_names: *mut PyObject,
        resources_abc: *mut PyObject,
    ) -> Option<Self> {
        let path_count = unsafe { PyTuple_Size(path_names) };
        if path_count < 0 {
            return None;
        }
        let pure_posix_path = if path_count == 0 {
            None
        } else {
            let pathlib = unsafe { PyObject_GetAttrString(resources_abc, c"pathlib".as_ptr()) };
            let pathlib = unsafe { OwnedPyObject::from_new_reference(pathlib) }?;
            let constructor = unsafe { PyObject_GetAttrString(pathlib.as_ptr(), c"PurePosixPath".as_ptr()) };
            unsafe { OwnedPyObject::from_new_reference(constructor) }
        };
        if path_count != 0 && pure_posix_path.is_none() {
            return None;
        }
        Some(Self {
            path_names,
            path_count,
            path_index: 0,
            resources_abc,
            pure_posix_path,
            parts: None,
        })
    }

    unsafe fn next(&mut self) -> Option<Option<OwnedPyObject>> {
        loop {
            if let Some(parts) = self.parts.as_ref() {
                let part = unsafe { PyIter_Next(parts.as_ptr()) };
                if !part.is_null() {
                    return unsafe { OwnedPyObject::from_new_reference(part) }.map(Some);
                }
                if !unsafe { PyErr_Occurred() }.is_null() {
                    return None;
                }
                self.parts = None;
            }

            if self.path_index >= self.path_count {
                return Some(None);
            }

            let descendant = unsafe { PyTuple_GetItem(self.path_names, self.path_index) };
            if descendant.is_null() {
                return None;
            }
            self.path_index += 1;
            let Some(constructor) = self.pure_posix_path.as_ref() else {
                return None;
            };
            let path = unsafe { PyObject_CallOneArg(constructor.as_ptr(), descendant) };
            let path = unsafe { OwnedPyObject::from_new_reference(path) }?;
            let path_parts = unsafe { PyObject_GetAttrString(path.as_ptr(), c"parts".as_ptr()) };
            let path_parts = unsafe { OwnedPyObject::from_new_reference(path_parts) }?;
            let iterator = unsafe { PyObject_GetIter(path_parts.as_ptr()) };
            self.parts = unsafe { OwnedPyObject::from_new_reference(iterator) };
            self.parts.as_ref()?;
        }
    }
}

enum ChildSearch {
    Error,
    Missing,
    Found(OwnedPyObject),
}

unsafe fn is_default_joinpath(
    method: *mut PyObject,
    default_joinpath: *mut PyObject,
) -> Option<bool> {
    let function = unsafe { PyObject_GetAttrString(method, c"__func__".as_ptr()) };
    if function.is_null() {
        if unsafe { PyErr_ExceptionMatches(PyExc_AttributeError) } != 0 {
            unsafe { PyErr_Clear() };
            return Some(false);
        }
        return None;
    }
    let function = unsafe { OwnedPyObject::from_new_reference(function) }?;
    let result = unsafe { PyObject_RichCompareBool(function.as_ptr(), default_joinpath, 2) };
    if result < 0 { None } else { Some(result != 0) }
}

unsafe fn bound_joinpath(
    traversable: *mut PyObject,
    default_joinpath: *mut PyObject,
) -> Option<(bool, OwnedPyObject)> {
    let method = unsafe { PyObject_GetAttrString(traversable, c"joinpath".as_ptr()) };
    let method = unsafe { OwnedPyObject::from_new_reference(method) }?;
    let is_default = unsafe { is_default_joinpath(method.as_ptr(), default_joinpath) }?;
    Some((is_default, method))
}

unsafe fn find_child(
    traversable: *mut PyObject,
    target: *mut PyObject,
) -> ChildSearch {
    let arguments = unsafe { PyTuple_New(0) };
    let Some(arguments) = (unsafe { OwnedPyObject::from_new_reference(arguments) }) else {
        return ChildSearch::Error;
    };
    let children = unsafe { call_method(traversable, c"iterdir", arguments.as_ptr(), ptr::null_mut()) };
    let Some(children) = (unsafe { OwnedPyObject::from_new_reference(children) }) else {
        return ChildSearch::Error;
    };
    let iterator = unsafe { PyObject_GetIter(children.as_ptr()) };
    let Some(iterator) = (unsafe { OwnedPyObject::from_new_reference(iterator) }) else {
        return ChildSearch::Error;
    };
    loop {
        let child = unsafe { PyIter_Next(iterator.as_ptr()) };
        if child.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                return ChildSearch::Missing;
            }
            return ChildSearch::Error;
        }
        let Some(child) = (unsafe { OwnedPyObject::from_new_reference(child) }) else {
            return ChildSearch::Error;
        };
        let name = unsafe { PyObject_GetAttrString(child.as_ptr(), c"name".as_ptr()) };
        let Some(name) = (unsafe { OwnedPyObject::from_new_reference(name) }) else {
            return ChildSearch::Error;
        };
        let matches = unsafe { PyObject_RichCompareBool(name.as_ptr(), target, 2) };
        if matches < 0 {
            return ChildSearch::Error;
        }
        if matches != 0 {
            return ChildSearch::Found(child);
        }
    }
}

unsafe fn remaining_segments(names: &mut SegmentIter) -> Option<Vec<OwnedPyObject>> {
    let mut remaining = Vec::new();
    loop {
        match unsafe { names.next() }? {
            Some(segment) => remaining.push(segment),
            None => return Some(remaining),
        }
    }
}

unsafe fn tuple_from_segments(segments: &[OwnedPyObject]) -> Option<OwnedPyObject> {
    let tuple = unsafe { PyTuple_New(segments.len() as Py_ssize_t) };
    let tuple = unsafe { OwnedPyObject::from_new_reference(tuple) }?;
    for (index, segment) in segments.iter().enumerate() {
        unsafe { Py_IncRef(segment.as_ptr()) };
        if unsafe { PyTuple_SetItem(tuple.as_ptr(), index as Py_ssize_t, segment.as_ptr()) } != 0 {
            return None;
        }
    }
    Some(tuple)
}

unsafe fn set_traversal_error(
    exception_type: *mut PyObject,
    target: *mut PyObject,
    remaining: &[OwnedPyObject],
) -> *mut PyObject {
    let message = unsafe { PyUnicode_FromString(c"Target not found during traversal.".as_ptr()) };
    let Some(message) = (unsafe { OwnedPyObject::from_new_reference(message) }) else {
        return ptr::null_mut();
    };
    let remaining_list = unsafe { PyList_New(0) };
    let Some(remaining_list) = (unsafe { OwnedPyObject::from_new_reference(remaining_list) }) else {
        return ptr::null_mut();
    };
    for segment in remaining {
        if unsafe { PyList_Append(remaining_list.as_ptr(), segment.as_ptr()) } != 0 {
            return ptr::null_mut();
        }
    }
    let arguments = unsafe { PyTuple_New(3) };
    let Some(arguments) = (unsafe { OwnedPyObject::from_new_reference(arguments) }) else {
        return ptr::null_mut();
    };
    let values = [message.as_ptr(), target, remaining_list.as_ptr()];
    for (index, value) in values.into_iter().enumerate() {
        unsafe { Py_IncRef(value) };
        if unsafe { PyTuple_SetItem(arguments.as_ptr(), index as Py_ssize_t, value) } != 0 {
            return ptr::null_mut();
        }
    }
    let error = unsafe { PyObject_Call(exception_type, arguments.as_ptr(), ptr::null_mut()) };
    let Some(error) = (unsafe { OwnedPyObject::from_new_reference(error) }) else {
        return ptr::null_mut();
    };
    unsafe { PyErr_SetObject(exception_type, error.as_ptr()) };
    ptr::null_mut()
}

unsafe fn walk_default_joinpath(
    traversable: *mut PyObject,
    names: &mut SegmentIter,
    default_joinpath: *mut PyObject,
    traversal_error: *mut PyObject,
    root: bool,
) -> *mut PyObject {
    let target = match unsafe { names.next() } {
        Some(Some(target)) => target,
        Some(None) if root && names.path_count != 0 => {
            unsafe { PyErr_SetNone(PyExc_StopIteration) };
            return ptr::null_mut();
        }
        Some(None) => {
            unsafe { Py_IncRef(traversable) };
            return traversable;
        }
        None => return ptr::null_mut(),
    };

    let child = match unsafe { find_child(traversable, target.as_ptr()) } {
        ChildSearch::Error => return ptr::null_mut(),
        ChildSearch::Missing => {
            let Some(remaining) = (unsafe { remaining_segments(names) }) else {
                return ptr::null_mut();
            };
            return unsafe {
                set_traversal_error(traversal_error, target.as_ptr(), &remaining)
            };
        }
        ChildSearch::Found(child) => child,
    };

    let Some((child_uses_default, child_joinpath)) =
        (unsafe { bound_joinpath(child.as_ptr(), default_joinpath) })
    else {
        return ptr::null_mut();
    };
    // Star expansion completes before a matched child's joinpath method runs.
    let Some(remaining) = (unsafe { remaining_segments(names) }) else {
        return ptr::null_mut();
    };
    let Some(arguments) = (unsafe { tuple_from_segments(&remaining) }) else {
        return ptr::null_mut();
    };
    if child_uses_default {
        if unsafe { Py_EnterRecursiveCall(c"".as_ptr()) } != 0 {
            return ptr::null_mut();
        }
        let Some(mut child_names) =
            (unsafe { SegmentIter::new(arguments.as_ptr(), names.resources_abc) })
        else {
            unsafe { Py_LeaveRecursiveCall() };
            return ptr::null_mut();
        };
        let result = unsafe {
            walk_default_joinpath(
                child.as_ptr(),
                &mut child_names,
                default_joinpath,
                traversal_error,
                false,
            )
        };
        unsafe { Py_LeaveRecursiveCall() };
        result
    } else {
        unsafe { PyObject_Call(child_joinpath.as_ptr(), arguments.as_ptr(), ptr::null_mut()) }
    }
}

unsafe fn call_method(
    target: *mut PyObject,
    method_name: &'static std::ffi::CStr,
    arguments: *mut PyObject,
    keywords: *mut PyObject,
) -> *mut PyObject {
    let method = unsafe { PyObject_GetAttrString(target, method_name.as_ptr()) };
    if method.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_Call(method, arguments, keywords) };
    unsafe { Py_DecRef(method) };
    result
}

unsafe fn empty_tuple() -> *mut PyObject {
    unsafe { PyTuple_New(0) }
}

unsafe fn text_keywords(
    encoding: *mut PyObject,
    errors: *mut PyObject,
) -> *mut PyObject {
    let keywords = unsafe { PyDict_New() };
    if keywords.is_null() {
        return ptr::null_mut();
    }
    if unsafe { PyDict_SetItemString(keywords, c"encoding".as_ptr(), encoding) } != 0
        || unsafe { PyDict_SetItemString(keywords, c"errors".as_ptr(), errors) } != 0
    {
        unsafe { Py_DecRef(keywords) };
        return ptr::null_mut();
    }
    keywords
}

unsafe fn call_text_method(
    target: *mut PyObject,
    method_name: &'static std::ffi::CStr,
    encoding: *mut PyObject,
    errors: *mut PyObject,
) -> *mut PyObject {
    let arguments = unsafe { empty_tuple() };
    if arguments.is_null() {
        return ptr::null_mut();
    }
    let keywords = unsafe { text_keywords(encoding, errors) };
    if keywords.is_null() {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    let result = unsafe { call_method(target, method_name, arguments, keywords) };
    unsafe {
        Py_DecRef(keywords);
        Py_DecRef(arguments);
    }
    result
}

unsafe fn call_open_text(
    target: *mut PyObject,
    encoding: *mut PyObject,
    errors: *mut PyObject,
) -> *mut PyObject {
    let arguments = unsafe { PyTuple_New(1) };
    if arguments.is_null() {
        return ptr::null_mut();
    }
    let mode = unsafe { PyUnicode_FromString(c"r".as_ptr()) };
    if mode.is_null() {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(arguments, 0, mode) } != 0 {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    let keywords = unsafe { text_keywords(encoding, errors) };
    if keywords.is_null() {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    let result = unsafe { call_method(target, c"open", arguments, keywords) };
    unsafe {
        Py_DecRef(keywords);
        Py_DecRef(arguments);
    }
    result
}

unsafe fn require_args(nargs: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if nargs == expected {
        return true;
    }
    unsafe {
        PyErr_SetString(
            PyExc_TypeError,
            c"invalid number of arguments".as_ptr(),
        );
    }
    false
}

unsafe extern "C" fn joinpath(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { require_args(nargs, 5) } {
        return ptr::null_mut();
    }
    let traversable = unsafe { *args };
    let path_names = unsafe { *args.add(1) };
    let resources_abc = unsafe { *args.add(2) };
    let default_joinpath = unsafe { *args.add(3) };
    let traversal_error = unsafe { *args.add(4) };
    let Some((uses_default, method)) =
        (unsafe { bound_joinpath(traversable, default_joinpath) })
    else {
        return ptr::null_mut();
    };
    // Loader-provided methods own their own path rules and callback ordering.
    if !uses_default {
        return unsafe { PyObject_Call(method.as_ptr(), path_names, ptr::null_mut()) };
    }
    if unsafe { Py_EnterRecursiveCall(c"".as_ptr()) } != 0 {
        return ptr::null_mut();
    }
    let Some(mut names) = (unsafe { SegmentIter::new(path_names, resources_abc) }) else {
        unsafe { Py_LeaveRecursiveCall() };
        return ptr::null_mut();
    };
    let result = unsafe {
        walk_default_joinpath(
            traversable,
            &mut names,
            default_joinpath,
            traversal_error,
            true,
        )
    };
    unsafe { Py_LeaveRecursiveCall() };
    result
}

unsafe extern "C" fn read_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { require_args(nargs, 1) } {
        return ptr::null_mut();
    }
    let traversable = unsafe { *args };
    let arguments = unsafe { empty_tuple() };
    if arguments.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { call_method(traversable, c"read_bytes", arguments, ptr::null_mut()) };
    unsafe { Py_DecRef(arguments) };
    result
}

unsafe extern "C" fn read_text(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { require_args(nargs, 3) } {
        return ptr::null_mut();
    }
    let traversable = unsafe { *args };
    let encoding = unsafe { *args.add(1) };
    let errors = unsafe { *args.add(2) };
    unsafe { call_text_method(traversable, c"read_text", encoding, errors) }
}

unsafe extern "C" fn open_binary(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { require_args(nargs, 1) } {
        return ptr::null_mut();
    }
    let traversable = unsafe { *args };
    let arguments = unsafe { PyTuple_New(1) };
    if arguments.is_null() {
        return ptr::null_mut();
    }
    let mode = unsafe { PyUnicode_FromString(c"rb".as_ptr()) };
    if mode.is_null() {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(arguments, 0, mode) } != 0 {
        unsafe { Py_DecRef(arguments) };
        return ptr::null_mut();
    }
    let result = unsafe { call_method(traversable, c"open", arguments, ptr::null_mut()) };
    unsafe { Py_DecRef(arguments) };
    result
}

unsafe extern "C" fn open_text(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { require_args(nargs, 3) } {
        return ptr::null_mut();
    }
    let traversable = unsafe { *args };
    let encoding = unsafe { *args.add(1) };
    let errors = unsafe { *args.add(2) };
    unsafe { call_open_text(traversable, encoding, errors) }
}

struct ModuleDef(UnsafeCell<PyModuleDef>);

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 6] = [
    PyMethodDef {
        ml_name: c"joinpath".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: joinpath },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Resolve default Traversable paths with Rust child lookup.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"read_bytes".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: read_bytes },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Read bytes through a Traversable callback.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"read_text".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: read_text },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Read text through a Traversable callback.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"open_binary".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: open_binary },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Open binary resources through a Traversable callback.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"open_text".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: open_text },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Open text resources through a Traversable callback.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_importlib_resources_rs".as_ptr() as *mut c_char,
    m_doc: c"Rust dispatch for importlib.resources Traversable operations.".as_ptr()
        as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: None,
    m_free: None,
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__importlib_resources_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.0.get()) }
}
