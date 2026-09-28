use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void, CString};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyDict_Copy, PyDict_Pop,
    PyDict_New, PyDict_Next, PyDict_SetItem, PyDict_Size,
    PyErr_Clear, PyErr_ExceptionMatches, PyErr_NoMemory, PyErr_Occurred, PyErr_SetString,
    PyExc_AttributeError, PyExc_KeyError, PyExc_TypeError, Py_GetConstant, Py_IncRef,
    PyList_Append, PyList_GetItemRef, PyList_New, PyList_Size, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    PyObject, PyObject_GetAttrString, PyObject_GetItem, PyObject_IsTrue, PyObject_Type,
    PyObject_Vectorcall, PySet_Add, PySet_Contains, PySet_New, PyTuple_GetItem,
    PyTuple_New, PyTuple_SetItem, PyTuple_Size, PyTuple_Type, PyDict_Type,
    PySequence_Contains,
    PyTypeObject, PyLong_AsLong, PyUnicode_AsUTF8AndSize, Py_ssize_t,
};

struct Owned(*mut PyObject);

impl Owned {
    fn from_raw(object: *mut PyObject) -> Option<Self> {
        if object.is_null() {
            None
        } else {
            Some(Self(object))
        }
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

struct Parameter {
    name: Owned,
    kind: i64,
    has_default: bool,
}

unsafe fn exact_type(object: *mut PyObject, expected: *mut PyTypeObject) -> Result<bool, ()> {
    let actual = Owned::from_raw(unsafe { PyObject_Type(object) }).ok_or(())?;
    Ok(actual.as_ptr() == expected.cast::<PyObject>())
}

unsafe fn exact_type_object(object: *mut PyObject, expected: *mut PyObject) -> Result<bool, ()> {
    let actual = Owned::from_raw(unsafe { PyObject_Type(object) }).ok_or(())?;
    Ok(actual.as_ptr() == expected)
}

unsafe fn tuple_size(object: *mut PyObject) -> Result<usize, ()> {
    let size = unsafe { PyTuple_Size(object) };
    if size < 0 {
        Err(())
    } else {
        Ok(size as usize)
    }
}

unsafe fn tuple_item(object: *mut PyObject, index: usize) -> Result<*mut PyObject, ()> {
    if index > Py_ssize_t::MAX as usize {
        return Err(());
    }
    let item = unsafe { PyTuple_GetItem(object, index as Py_ssize_t) };
    if item.is_null() {
        Err(())
    } else {
        Ok(item)
    }
}

unsafe fn list_size(object: *mut PyObject) -> Result<usize, ()> {
    let size = unsafe { PyList_Size(object) };
    if size < 0 {
        Err(())
    } else {
        Ok(size as usize)
    }
}

unsafe fn list_item(object: *mut PyObject, index: usize) -> Result<Owned, ()> {
    if index > Py_ssize_t::MAX as usize {
        return Err(());
    }
    Owned::from_raw(unsafe { PyList_GetItemRef(object, index as Py_ssize_t) }).ok_or(())
}

unsafe fn set_type_error(message: &str) {
    let message = CString::new(message)
        .unwrap_or_else(|_| CString::new("invalid argument binding").unwrap());
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

unsafe fn object_repr(object: *mut PyObject) -> Result<String, ()> {
    let repr = Owned::from_raw(unsafe { cpython_sys::PyObject_Repr(object) }).ok_or(())?;
    let mut size = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(repr.as_ptr(), &mut size) };
    if bytes.is_null() || size < 0 {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), size as usize) };
    std::str::from_utf8(bytes)
        .map(str::to_owned)
        .map_err(|_| ())
}

unsafe fn unicode_value(object: *mut PyObject) -> Result<String, ()> {
    let mut size = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if bytes.is_null() || size < 0 {
        return Err(());
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), size as usize) };
    std::str::from_utf8(bytes)
        .map(str::to_owned)
        .map_err(|_| ())
}

unsafe fn dict_contains(dict: *mut PyObject, key: *mut PyObject) -> Result<bool, ()> {
    let result = unsafe { cpython_sys::PyDict_Contains(dict, key) };
    if result < 0 {
        Err(())
    } else {
        Ok(result != 0)
    }
}

unsafe fn dict_set(
    dict: *mut PyObject,
    key: *mut PyObject,
    value: *mut PyObject,
) -> Result<(), ()> {
    if unsafe { PyDict_SetItem(dict, key, value) } == 0 {
        Ok(())
    } else {
        Err(())
    }
}

unsafe fn dict_take(
    dict: *mut PyObject,
    key: *mut PyObject,
) -> Result<Option<Owned>, ()> {
    let mut value = ptr::null_mut();
    let result = unsafe { PyDict_Pop(dict, key, &mut value) };
    if result < 0 {
        if unsafe { PyErr_ExceptionMatches(PyExc_KeyError) } != 0 {
            unsafe { PyErr_Clear() };
            return Ok(None);
        }
        return Err(());
    }
    if result == 0 {
        return Ok(None);
    }
    Owned::from_raw(value).map(Some).ok_or(())
}

unsafe fn read_parameter(
    object: *mut PyObject,
    expected_type: *mut PyObject,
    empty: *mut PyObject,
) -> Result<Option<Parameter>, ()> {
    if !unsafe { exact_type_object(object, expected_type) }? {
        return Ok(None);
    }

    let name = Owned::from_raw(unsafe { PyObject_GetAttrString(object, c"name".as_ptr()) })
        .ok_or(())?;
    let kind = Owned::from_raw(unsafe { PyObject_GetAttrString(object, c"kind".as_ptr()) })
        .ok_or(())?;
    let default = Owned::from_raw(unsafe {
        PyObject_GetAttrString(object, c"default".as_ptr())
    })
    .ok_or(())?;

    let kind = unsafe { PyLong_AsLong(kind.as_ptr()) };
    if kind == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return Err(());
    }

    Ok(Some(Parameter {
        name,
        kind,
        has_default: default.as_ptr() != empty,
    }))
}

unsafe fn tuple_slice(
    tuple: *mut PyObject,
    start: usize,
    end: usize,
) -> Result<Owned, ()> {
    let length = end.checked_sub(start).ok_or(())?;
    if length > Py_ssize_t::MAX as usize {
        return Err(());
    }
    let result = Owned::from_raw(unsafe { PyTuple_New(length as Py_ssize_t) }).ok_or(())?;
    for target_index in 0..length {
        let item = unsafe { tuple_item(tuple, start + target_index) }?;
        unsafe { Py_IncRef(item) };
        if unsafe {
            PyTuple_SetItem(result.as_ptr(), target_index as Py_ssize_t, item)
        } != 0
        {
            unsafe { Py_DecRef(item) };
            return Err(());
        }
    }
    Ok(result)
}

unsafe fn bind_impl(
    parameters: *mut PyObject,
    args: *mut PyObject,
    kwargs: *mut PyObject,
    partial: *mut PyObject,
    parameter_type: *mut PyObject,
    empty: *mut PyObject,
) -> Result<Option<Owned>, ()> {
    if !unsafe { exact_type(parameters, ptr::addr_of_mut!(PyTuple_Type)) }? {
        return Ok(None);
    }
    if !unsafe { exact_type(args, ptr::addr_of_mut!(PyTuple_Type)) }? {
        return Ok(None);
    }
    if !unsafe { exact_type(kwargs, ptr::addr_of_mut!(PyDict_Type)) }? {
        return Ok(None);
    }

    let parameter_count = unsafe { tuple_size(parameters) }?;
    let mut parsed = Vec::new();
    if parsed.try_reserve_exact(parameter_count).is_err() {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    for index in 0..parameter_count {
        let object = unsafe { tuple_item(parameters, index) }?;
        let Some(parameter) = (unsafe { read_parameter(object, parameter_type, empty) })? else {
            return Ok(None);
        };
        parsed.push(parameter);
    }

    let partial = unsafe { PyObject_IsTrue(partial) };
    if partial < 0 {
        return Err(());
    }
    let args_count = unsafe { tuple_size(args) }?;
    let kwargs_copy = Owned::from_raw(unsafe { PyDict_Copy(kwargs) }).ok_or(())?;
    let arguments = Owned::from_raw(unsafe { PyDict_New() }).ok_or(())?;

    let mut arg_index = 0;
    let mut param_index = 0;
    let mut consumed_varargs = false;

    while arg_index < args_count {
        if param_index == parsed.len() {
            unsafe { set_type_error("too many positional arguments") };
            return Err(());
        }
        let parameter = &parsed[param_index];
        if parameter.kind == 3 || parameter.kind == 4 {
            unsafe { set_type_error("too many positional arguments") };
            return Err(());
        }
        if parameter.kind == 2 {
            let values = unsafe { tuple_slice(args, arg_index, args_count) }?;
            unsafe { dict_set(arguments.as_ptr(), parameter.name.as_ptr(), values.as_ptr()) }?;
            param_index += 1;
            consumed_varargs = true;
            break;
        }
        if parameter.kind != 0
            && unsafe { dict_contains(kwargs_copy.as_ptr(), parameter.name.as_ptr()) }?
        {
            let name = unsafe { object_repr(parameter.name.as_ptr()) }?;
            unsafe { set_type_error(&format!("multiple values for argument {name}")) };
            return Err(());
        }
        let value = unsafe { tuple_item(args, arg_index) }?;
        unsafe { dict_set(arguments.as_ptr(), parameter.name.as_ptr(), value) }?;
        arg_index += 1;
        param_index += 1;
    }

    let mut positional_only_in_kwargs = Vec::new();
    if positional_only_in_kwargs.try_reserve_exact(parameter_count).is_err() {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    if arg_index == args_count && !consumed_varargs {
        while param_index < parsed.len() {
            let parameter = &parsed[param_index];
            if parameter.kind == 2 {
                break;
            }
            if unsafe { dict_contains(kwargs_copy.as_ptr(), parameter.name.as_ptr()) }? {
                if parameter.kind == 0 {
                    if !parameter.has_default {
                        let name = unsafe { object_repr(parameter.name.as_ptr()) }?;
                        unsafe {
                            set_type_error(&format!(
                                "missing a required positional-only argument: {name}"
                            ))
                        };
                        return Err(());
                    }
                    positional_only_in_kwargs.push(parameter.name.as_ptr());
                    param_index += 1;
                    continue;
                }
                break;
            }
            if parameter.kind == 4 || parameter.has_default || partial != 0 {
                break;
            }
            let name = unsafe { object_repr(parameter.name.as_ptr()) }?;
            let argument_kind = if parameter.kind == 3 {
                " keyword-only"
            } else {
                ""
            };
            unsafe {
                set_type_error(&format!(
                    "missing a required{argument_kind} argument: {name}"
                ))
            };
            return Err(());
        }
    }

    let mut kwargs_parameter = None;
    for parameter in parsed.iter().skip(param_index) {
        if parameter.kind == 4 {
            kwargs_parameter = Some(parameter);
            continue;
        }
        if parameter.kind == 2 {
            continue;
        }

        if let Some(value) =
            unsafe { dict_take(kwargs_copy.as_ptr(), parameter.name.as_ptr()) }?
        {
            unsafe {
                dict_set(
                    arguments.as_ptr(),
                    parameter.name.as_ptr(),
                    value.as_ptr(),
                )
            }?;
        } else if partial == 0 && !parameter.has_default {
            let name = unsafe { object_repr(parameter.name.as_ptr()) }?;
            unsafe { set_type_error(&format!("missing a required argument: {name}")) };
            return Err(());
        }
    }

    let remaining_keywords = unsafe { PyDict_Size(kwargs_copy.as_ptr()) };
    if remaining_keywords < 0 {
        return Err(());
    }
    if remaining_keywords > 0 {
        if let Some(parameter) = kwargs_parameter {
            unsafe {
                dict_set(
                    arguments.as_ptr(),
                    parameter.name.as_ptr(),
                    kwargs_copy.as_ptr(),
                )
            }?;
        } else if !positional_only_in_kwargs.is_empty() {
            let names = positional_only_in_kwargs
                .iter()
                .map(|name| unsafe { unicode_value(*name) })
                .collect::<Result<Vec<_>, _>>()?
                .join(", ");
            unsafe {
                set_type_error(&format!(
                    "got some positional-only arguments passed as keyword arguments: '{names}'"
                ))
            };
            return Err(());
        } else {
            let mut position = 0;
            let mut key = ptr::null_mut();
            let mut value = ptr::null_mut();
            if unsafe {
                PyDict_Next(
                    kwargs_copy.as_ptr(),
                    &mut position,
                    &mut key,
                    &mut value,
                )
            } == 0
            {
                return Err(());
            }
            let name = unsafe { object_repr(key) }?;
            unsafe { set_type_error(&format!("got an unexpected keyword argument {name}")) };
            return Err(());
        }
    }

    Ok(Some(arguments))
}

unsafe extern "C" fn bind(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 6 {
        unsafe { set_type_error("bind() takes exactly six arguments") };
        return ptr::null_mut();
    }
    let result = unsafe {
        bind_impl(
            *args,
            *args.add(1),
            *args.add(2),
            *args.add(3),
            *args.add(4),
            *args.add(5),
        )
    };
    match result {
        Ok(Some(value)) => value.into_raw(),
        Ok(None) => unsafe { Py_GetConstant(0) },
        Err(()) => ptr::null_mut(),
    }
}

unsafe fn call_two_args(
    callable: *mut PyObject,
    first: *mut PyObject,
    second: *mut PyObject,
) -> *mut PyObject {
    let args = [first, second];
    unsafe { PyObject_Vectorcall(callable, args.as_ptr(), 2, ptr::null_mut()) }
}

unsafe fn fallback_member(
    mro: *mut PyObject,
    key: *mut PyObject,
) -> Result<Option<Owned>, ()> {
    let count = unsafe { tuple_size(mro) }?;
    for index in 0..count {
        let base = unsafe { tuple_item(mro, index) }?;
        let dict = Owned::from_raw(unsafe {
            PyObject_GetAttrString(base, c"__dict__".as_ptr())
        })
        .ok_or(())?;
        let contains = unsafe { PySequence_Contains(dict.as_ptr(), key) };
        if contains < 0 {
            return Err(());
        }
        if contains == 0 {
            continue;
        }
        let value = Owned::from_raw(unsafe { PyObject_GetItem(dict.as_ptr(), key) }).ok_or(())?;
        return Ok(Some(value));
    }
    Ok(None)
}

unsafe fn members_impl(
    object: *mut PyObject,
    predicate: *mut PyObject,
    getter: *mut PyObject,
    names: *mut PyObject,
    mro: *mut PyObject,
) -> Result<Owned, ()> {
    let processed = Owned::from_raw(unsafe { PySet_New(ptr::null_mut()) }).ok_or(())?;
    let results = Owned::from_raw(unsafe { PyList_New(0) }).ok_or(())?;

    let mut index = 0;
    loop {
        let names_count = unsafe { list_size(names) }?;
        if index >= names_count {
            break;
        }
        let key = unsafe { list_item(names, index) }?;
        let key_ptr = key.as_ptr();
        let mut value = Owned::from_raw(unsafe { call_two_args(getter, object, key_ptr) });
        let mut use_fallback = value.is_none();
        if use_fallback && !unsafe { PyErr_Occurred() }.is_null() {
            if unsafe { PyErr_ExceptionMatches(PyExc_AttributeError) } == 0 {
                return Err(());
            }
            unsafe { PyErr_Clear() };
        }

        if !use_fallback {
            let duplicate = unsafe { PySet_Contains(processed.as_ptr(), key_ptr) };
            if duplicate < 0 {
                if unsafe { PyErr_ExceptionMatches(PyExc_AttributeError) } == 0 {
                    return Err(());
                }
                unsafe { PyErr_Clear() };
                use_fallback = true;
            } else if duplicate != 0 {
                drop(value.take());
                use_fallback = true;
            }
        }

        if use_fallback {
            value = unsafe { fallback_member(mro, key_ptr) }?;
        }
        if let Some(value) = value {
            let predicate_enabled = unsafe { PyObject_IsTrue(predicate) };
            if predicate_enabled < 0 {
                return Err(());
            }
            let include = if predicate_enabled == 0 {
                true
            } else {
                let result = Owned::from_raw(unsafe {
                    PyObject_Vectorcall(
                        predicate,
                        [value.as_ptr()].as_ptr(),
                        1,
                        ptr::null_mut(),
                    )
                })
                .ok_or(())?;
                let truth = unsafe { PyObject_IsTrue(result.as_ptr()) };
                if truth < 0 {
                    return Err(());
                }
                truth != 0
            };

            if include {
                let pair = Owned::from_raw(unsafe { PyTuple_New(2) }).ok_or(())?;
                unsafe { Py_IncRef(key_ptr) };
                if unsafe { PyTuple_SetItem(pair.as_ptr(), 0, key_ptr) } != 0 {
                    unsafe { Py_DecRef(key_ptr) };
                    return Err(());
                }
                if unsafe { PyTuple_SetItem(pair.as_ptr(), 1, value.into_raw()) } != 0 {
                    return Err(());
                }
                if unsafe { PyList_Append(results.as_ptr(), pair.as_ptr()) } != 0 {
                    return Err(());
                }
            }
            if unsafe { PySet_Add(processed.as_ptr(), key_ptr) } != 0 {
                return Err(());
            }
        }
        index += 1;
    }

    Ok(results)
}

unsafe extern "C" fn getmembers(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 5 {
        unsafe { set_type_error("getmembers() takes exactly five arguments") };
        return ptr::null_mut();
    }
    match unsafe {
        members_impl(
            *args,
            *args.add(1),
            *args.add(2),
            *args.add(3),
            *args.add(4),
        )
    } {
        Ok(value) => value.into_raw(),
        Err(()) => ptr::null_mut(),
    }
}

pub extern "C" fn _inspect_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _inspect_rs_free(_object: *mut c_void) {}

struct ModuleDef(UnsafeCell<PyModuleDef>);

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"bind".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: bind,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Bind arguments to a sequence of inspect parameters.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"getmembers".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: getmembers,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Collect named object members.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_inspect_rs".as_ptr() as *mut _,
    m_doc: c"Rust helpers for signature binding and object inspection.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: &METHODS as *const PyMethodDef as *mut _,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: Some(_inspect_rs_clear),
    m_free: Some(_inspect_rs_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__inspect_rs() -> *mut PyObject {
    MODULE.init()
}
