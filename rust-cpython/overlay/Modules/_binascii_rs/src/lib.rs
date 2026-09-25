use std::cell::UnsafeCell;
use std::ffi::{CStr, c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, METH_KEYWORDS, Py_DecRef, Py_buffer, PyBytes_FromStringAndSize,
    PyBuffer_Release, PyErr_NoMemory, PyErr_SetString, PyExc_TypeError, PyExc_ValueError,
    PyImport_AddModule, PyLong_AsSsize_t, PyLong_AsUnsignedLongMask, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_Slot, PyModuleDef_HEAD_INIT, PyModuleDef_Init,
    PyObject, PyObject_GetAttrString, PyObject_GetBuffer, PyObject_IsInstance,
    PyObject_Length, PyTuple_GetItem, PyTuple_Size,
    PyUnicode_AsUTF8AndSize, PyUnicode_ReadChar, PyBytes_Type, PyUnicode_Type, Py_ssize_t,
};

use crc32fast::Hasher;

const PYBUF_SIMPLE: c_int = 0;
const HEX: &[u8; 16] = b"0123456789abcdef";

struct Buffer {
    view: Py_buffer,
}

impl Buffer {
    unsafe fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return Err(());
        }
        Ok(Self {
            view: unsafe { view.assume_init() },
        })
    }

    fn as_slice(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for Buffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

struct AsciiBuffer {
    buffer: Buffer,
    owner: *mut PyObject,
}

impl AsciiBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let is_unicode = unsafe {
            PyObject_IsInstance(
                object,
                ptr::addr_of_mut!(PyUnicode_Type).cast::<PyObject>(),
            )
        };
        if is_unicode < 0 {
            return Err(());
        }
        if is_unicode != 0 {
            let mut length = 0;
            let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
            if data.is_null() || length < 0 {
                return Err(());
            }
            let text = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
            if !text.is_ascii() {
                unsafe { set_value_error("string argument should contain only ASCII characters") };
                return Err(());
            }
            let owner = unsafe {
                PyBytes_FromStringAndSize(
                    if text.is_empty() { c"".as_ptr() } else { text.as_ptr().cast() },
                    length,
                )
            };
            if owner.is_null() {
                return Err(());
            }
            match unsafe { Buffer::from_object(owner) } {
                Ok(buffer) => Ok(Self { buffer, owner }),
                Err(()) => {
                    unsafe { Py_DecRef(owner) };
                    Err(())
                }
            }
        } else {
            Ok(Self {
                buffer: unsafe { Buffer::from_object(object)? },
                owner: ptr::null_mut(),
            })
        }
    }
}

impl Drop for AsciiBuffer {
    fn drop(&mut self) {
        if !self.owner.is_null() {
            unsafe { Py_DecRef(self.owner) }
        }
    }
}

unsafe fn set_error(exception: *mut PyObject, message: &str) {
    let message = message.replace('\0', "\\x00");
    let message = std::ffi::CString::new(message).expect("escaped Python error contains no NUL");
    unsafe { PyErr_SetString(exception, message.as_ptr()) };
}

unsafe fn set_type_error(message: &str) {
    unsafe { set_error(PyExc_TypeError, message) }
}

unsafe fn set_value_error(message: &str) {
    unsafe { set_error(PyExc_ValueError, message) }
}

unsafe fn set_binascii_error(message: &CStr) {
    let module = unsafe { PyImport_AddModule(c"binascii".as_ptr()) };
    if module.is_null() {
        return;
    }
    let exception = unsafe { PyObject_GetAttrString(module, c"Error".as_ptr()) };
    if exception.is_null() {
        return;
    }
    unsafe { PyErr_SetString(exception, message.as_ptr()) };
    unsafe { Py_DecRef(exception) };
}

unsafe fn bytes_from_slice(data: &[u8]) -> *mut PyObject {
    if data.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let source = if data.is_empty() {
        c"".as_ptr()
    } else {
        data.as_ptr().cast::<c_char>()
    };
    unsafe { PyBytes_FromStringAndSize(source, data.len() as Py_ssize_t) }
}

unsafe fn call_arguments(
    function: &str,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
    names: &[&[u8]],
    positional_only: usize,
    required: usize,
    max_positional: usize,
) -> Result<Vec<*mut PyObject>, ()> {
    let keyword_count = if kwnames.is_null() {
        0
    } else {
        let count = unsafe { PyTuple_Size(kwnames) };
        if count < 0 {
            return Err(());
        }
        count
    };
    if nargs < 0
        || nargs as usize > max_positional
        || keyword_count as usize > names.len()
    {
        unsafe {
            set_type_error(&format!(
                "{}() takes at most {} positional arguments ({} given)",
                function,
                max_positional,
                nargs
            ));
        }
        return Err(());
    }

    let mut values = vec![ptr::null_mut(); names.len()];
    for index in 0..nargs as usize {
        values[index] = unsafe { *args.add(index) };
    }
    for keyword_index in 0..keyword_count as usize {
        let key = unsafe { PyTuple_GetItem(kwnames, keyword_index as Py_ssize_t) };
        if key.is_null() {
            return Err(());
        }
        let mut key_len = 0;
        let key_data = unsafe { PyUnicode_AsUTF8AndSize(key, &mut key_len) };
        if key_data.is_null() || key_len < 0 {
            return Err(());
        }
        let key_bytes = unsafe { slice::from_raw_parts(key_data.cast::<u8>(), key_len as usize) };
        let Some(index) = names.iter().position(|name| *name == key_bytes) else {
            unsafe {
                set_type_error(&format!(
                    "{}() got an unexpected keyword argument '{}'",
                    function,
                    String::from_utf8_lossy(key_bytes)
                ));
            }
            return Err(());
        };
        if index < positional_only {
            unsafe {
                set_type_error(&format!(
                    "{}() got some positional-only arguments passed as keyword arguments: '{}'",
                    function,
                    String::from_utf8_lossy(key_bytes)
                ));
            }
            return Err(());
        }
        if index < nargs as usize || !values[index].is_null() {
            unsafe {
                set_type_error(&format!(
                    "{}() got multiple values for argument '{}'",
                    function,
                    String::from_utf8_lossy(key_bytes)
                ));
            }
            return Err(());
        }
        values[index] = unsafe { *args.add(nargs as usize + keyword_index) };
    }

    for index in 0..required {
        if values[index].is_null() {
            let position = if index < positional_only {
                format!("pos {}", index + 1)
            } else {
                format!("keyword-only argument '{}'", String::from_utf8_lossy(names[index]))
            };
            unsafe {
                set_type_error(&format!(
                    "{}() missing required argument '{}' ({})",
                    function,
                    String::from_utf8_lossy(names[index]),
                    position
                ));
            }
            return Err(());
        }
    }
    Ok(values)
}

unsafe fn optional_bytes_per_sep(value: *mut PyObject) -> Result<isize, ()> {
    if value.is_null() {
        return Ok(1);
    }
    let result = unsafe { PyLong_AsSsize_t(value) };
    if result == -1 && !unsafe { cpython_sys::PyErr_Occurred() }.is_null() {
        return Err(());
    }
    Ok(result as isize)
}

unsafe fn separator(value: *mut PyObject) -> Result<Option<u8>, ()> {
    if value.is_null() || value == ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct) {
        return Ok(None);
    }

    let is_unicode = unsafe {
        PyObject_IsInstance(value, ptr::addr_of_mut!(PyUnicode_Type).cast::<PyObject>())
    };
    if is_unicode < 0 {
        return Err(());
    }
    if is_unicode != 0 {
        let length = unsafe { cpython_sys::PyUnicode_GetLength(value) };
        if length < 0 {
            return Err(());
        }
        if length != 1 {
            unsafe { set_value_error("sep must be length 1.") };
            return Err(());
        }
        let character = unsafe { PyUnicode_ReadChar(value, 0) };
        if character == u32::MAX {
            return Err(());
        }
        if character > u8::MAX as u32 {
            unsafe { set_value_error("sep must be ASCII.") };
            return Err(());
        }
        return Ok(Some(character as u8));
    }

    let is_bytes = unsafe {
        PyObject_IsInstance(value, ptr::addr_of_mut!(PyBytes_Type).cast::<PyObject>())
    };
    if is_bytes < 0 {
        return Err(());
    }
    if is_bytes != 0 {
        let buffer = unsafe { Buffer::from_object(value)? };
        if buffer.view.len != 1 {
            unsafe { set_value_error("sep must be length 1.") };
            return Err(());
        }
        return Ok(Some(buffer.as_slice()[0]));
    }

    let length = unsafe { PyObject_Length(value) };
    if length < 0 {
        return Err(());
    }
    if length != 1 {
        unsafe { set_value_error("sep must be length 1.") };
    } else {
        unsafe { set_type_error("sep must be str or bytes.") };
    }
    Err(())
}

unsafe fn encode_hex(
    function: &'static CStr,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    let function_name = function.to_str().unwrap_or("hexlify");
    let parsed = match unsafe {
        call_arguments(
            function_name,
            args,
            nargs,
            kwnames,
            &[b"data", b"sep", b"bytes_per_sep"],
            1,
            1,
            3,
        )
    } {
        Ok(values) => values,
        Err(()) => return ptr::null_mut(),
    };
    let source = match unsafe { Buffer::from_object(parsed[0]) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let input = source.as_slice();
    let sep = match unsafe { separator(parsed[1]) } {
        Ok(sep) => sep,
        Err(()) => return ptr::null_mut(),
    };
    let bytes_per_sep = match unsafe { optional_bytes_per_sep(parsed[2]) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };

    let group = bytes_per_sep.unsigned_abs();
    let mut first_separator = if bytes_per_sep > 0 && group != 0 {
        let remainder = input.len() % group;
        if remainder == 0 { group } else { remainder }
    } else {
        group
    };
    let separated = sep.is_some() && group != 0 && group < input.len();
    let separator_count = if separated && first_separator < input.len() {
        1 + (input.len() - 1 - first_separator) / group
    } else {
        0
    };
    let Some(output_len) = input
        .len()
        .checked_mul(2)
        .and_then(|length| length.checked_add(separator_count))
    else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    let mut output = Vec::new();
    if output.try_reserve_exact(output_len).is_err() {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    for (index, byte) in input.iter().copied().enumerate() {
        if separated && index == first_separator {
            output.push(sep.unwrap());
            first_separator = first_separator.saturating_add(group);
        }
        output.push(HEX[(byte >> 4) as usize]);
        output.push(HEX[(byte & 0x0f) as usize]);
    }
    unsafe { bytes_from_slice(&output) }
}

unsafe fn decode_hex(
    function: &'static CStr,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    let function_name = function.to_str().unwrap_or("unhexlify");
    let parsed = match unsafe {
        call_arguments(
            function_name,
            args,
            nargs,
            kwnames,
            &[b"hexstr", b"ignorechars"],
            1,
            1,
            1,
        )
    } {
        Ok(values) => values,
        Err(()) => return ptr::null_mut(),
    };
    let source = match unsafe { AsciiBuffer::from_object(parsed[0]) } {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let ignorechars = if parsed[1].is_null() {
        None
    } else {
        match unsafe { Buffer::from_object(parsed[1]) } {
            Ok(buffer) => Some(buffer),
            Err(()) => return ptr::null_mut(),
        }
    };
    let ignored = ignorechars.as_ref().map_or(&[][..], Buffer::as_slice);
    let mut output = Vec::new();
    if output.try_reserve_exact(source.buffer.as_slice().len() / 2).is_err() {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let mut high_nibble = None;
    for byte in source.buffer.as_slice().iter().copied() {
        let digit = match byte {
            b'0'..=b'9' => Some(byte - b'0'),
            b'a'..=b'f' => Some(byte - b'a' + 10),
            b'A'..=b'F' => Some(byte - b'A' + 10),
            _ => None,
        };
        let Some(digit) = digit else {
            if ignored.contains(&byte) {
                continue;
            }
            unsafe { set_binascii_error(c"Non-hexadecimal digit found") };
            return ptr::null_mut();
        };
        if let Some(high) = high_nibble.take() {
            output.push((high << 4) | digit);
        } else {
            high_nibble = Some(digit);
        }
    }
    if high_nibble.is_some() {
        unsafe { set_binascii_error(c"Odd number of hexadecimal digits") };
        return ptr::null_mut();
    }
    unsafe { bytes_from_slice(&output) }
}

unsafe fn checksum_args(
    function: &'static CStr,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
    names: &[&[u8]],
    required: usize,
) -> Result<(Buffer, u32), ()> {
    let parsed = unsafe {
        call_arguments(
            function.to_str().unwrap_or("crc32"),
            args,
            nargs,
            kwnames,
            names,
            names.len(),
            required,
            names.len(),
        )
    }?;
    let data = unsafe { Buffer::from_object(parsed[0]) }?;
    let crc = if parsed.len() > 1 && !parsed[1].is_null() {
        let crc = unsafe { PyLong_AsUnsignedLongMask(parsed[1]) };
        if crc == u64::MAX && !unsafe { cpython_sys::PyErr_Occurred() }.is_null() {
            return Err(());
        }
        crc as u32
    } else {
        0
    };
    Ok((data, crc))
}

unsafe fn crc32_impl(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    let (data, crc) = match unsafe {
        checksum_args(c"crc32", args, nargs, kwnames, &[b"data", b"crc"], 1)
    } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let mut hasher = Hasher::new_with_initial(crc);
    hasher.update(data.as_slice());
    unsafe { cpython_sys::PyLong_FromUnsignedLong(hasher.finalize() as _) }
}

unsafe fn crc_hqx_impl(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    let (data, mut crc) = match unsafe {
        checksum_args(c"crc_hqx", args, nargs, kwnames, &[b"data", b"crc"], 2)
    } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    crc &= 0xffff;
    for byte in data.as_slice() {
        crc ^= (*byte as u32) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 {
                ((crc << 1) & 0xffff) ^ 0x1021
            } else {
                (crc << 1) & 0xffff
            };
        }
    }
    unsafe { cpython_sys::PyLong_FromUnsignedLong(crc as _) }
}

unsafe extern "C" fn b2a_hex(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { encode_hex(c"b2a_hex", args, nargs, kwnames) }
}

unsafe extern "C" fn hexlify(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { encode_hex(c"hexlify", args, nargs, kwnames) }
}

unsafe extern "C" fn a2b_hex(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { decode_hex(c"a2b_hex", args, nargs, kwnames) }
}

unsafe extern "C" fn unhexlify(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { decode_hex(c"unhexlify", args, nargs, kwnames) }
}

unsafe extern "C" fn crc32(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { crc32_impl(args, nargs, kwnames) }
}

unsafe extern "C" fn crc_hqx(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    kwnames: *mut PyObject,
) -> *mut PyObject {
    unsafe { crc_hqx_impl(args, nargs, kwnames) }
}

macro_rules! module_method {
    ($name:expr, $function:ident, $doc:expr) => {
        PyMethodDef {
            ml_name: $name.as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer {
                PyCFunctionFastWithKeywords: $function,
            },
            ml_flags: METH_FASTCALL | METH_KEYWORDS,
            ml_doc: $doc.as_ptr() as *mut c_char,
        }
    };
}

static METHODS: [PyMethodDef; 7] = [
    module_method!(c"b2a_hex", b2a_hex, c"b2a_hex($module, data, /, sep=None, bytes_per_sep=1)\n--\n\nHexadecimal representation of binary data."),
    module_method!(c"hexlify", hexlify, c"hexlify($module, data, /, sep=None, bytes_per_sep=1)\n--\n\nHexadecimal representation of binary data."),
    module_method!(c"a2b_hex", a2b_hex, c"a2b_hex($module, hexstr, /, *, ignorechars=b'')\n--\n\nBinary data of hexadecimal representation."),
    module_method!(c"unhexlify", unhexlify, c"unhexlify($module, hexstr, /, *, ignorechars=b'')\n--\n\nBinary data of hexadecimal representation."),
    module_method!(c"crc32", crc32, c"crc32($module, data, crc=0, /)\n--\n\nCompute CRC-32 incrementally."),
    module_method!(c"crc_hqx", crc_hqx, c"crc_hqx($module, data, crc, /)\n--\n\nCompute CRC-CCITT incrementally."),
    PyMethodDef::zeroed(),
];

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

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_binascii_rs".as_ptr() as *mut _,
        m_doc: c"Rust binary-to-ASCII conversions and checksums".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
        m_traverse: None,
        m_clear: None,
        m_free: None,
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__binascii_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
