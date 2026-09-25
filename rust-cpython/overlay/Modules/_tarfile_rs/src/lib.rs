use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize, Py_DecRef,
    PyErr_Clear, PyErr_Occurred, PyLong_AsUnsignedLongLong, PyLong_FromUnsignedLongLong,
    PyMethodDef, PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT,
    PyModuleDef_Init, Py_NewRef, PyObject, PyTuple_New, PyTuple_SetItem, Py_ssize_t,
    _Py_NoneStruct,
};
use tar::{EntryType, Header};

unsafe fn bytes_argument(object: *mut PyObject) -> Option<Vec<u8>> {
    let mut data = ptr::null_mut();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(bytes.to_vec())
}

unsafe fn unsigned_argument(object: *mut PyObject) -> Option<u64> {
    let value = unsafe { PyLong_AsUnsignedLongLong(object) };
    if value == u64::MAX && !unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return None;
    }
    Some(value)
}

unsafe fn py_bytes(bytes: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

unsafe fn py_uint(value: u64) -> *mut PyObject {
    unsafe { PyLong_FromUnsignedLongLong(value) }
}

unsafe fn py_none() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe fn tuple_from_fields(fields: Vec<*mut PyObject>) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(fields.len() as Py_ssize_t) };
    if tuple.is_null() {
        for field in fields {
            if !field.is_null() {
                unsafe { Py_DecRef(field) };
            }
        }
        return ptr::null_mut();
    }
    for (index, field) in fields.into_iter().enumerate() {
        if field.is_null()
            || unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, field) } != 0
        {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
    }
    tuple
}

fn number_field(field: &[u8], parsed: Result<u64, impl std::fmt::Debug>) -> Option<u64> {
    if field.iter().all(|byte| *byte == 0 || *byte == b' ') {
        return Some(0);
    }
    parsed.ok()
}

fn optional_number_field(
    field: &[u8],
    parsed: Result<Option<u32>, impl std::fmt::Debug>,
) -> Option<u64> {
    if field.iter().all(|byte| *byte == 0 || *byte == b' ') {
        return Some(0);
    }
    parsed.ok()?.map(u64::from)
}

unsafe extern "C" fn create_ustar_header(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 13 {
        return unsafe { py_none() };
    }
    let Some(name) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    let Some(prefix) = (unsafe { bytes_argument(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    let Some(linkname) = (unsafe { bytes_argument(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    let Some(uname) = (unsafe { bytes_argument(*args.add(3)) }) else {
        return ptr::null_mut();
    };
    let Some(gname) = (unsafe { bytes_argument(*args.add(4)) }) else {
        return ptr::null_mut();
    };
    let Some(mode) = (unsafe { unsigned_argument(*args.add(5)) }) else {
        return unsafe { py_none() };
    };
    let Some(uid) = (unsafe { unsigned_argument(*args.add(6)) }) else {
        return unsafe { py_none() };
    };
    let Some(gid) = (unsafe { unsigned_argument(*args.add(7)) }) else {
        return unsafe { py_none() };
    };
    let Some(size) = (unsafe { unsigned_argument(*args.add(8)) }) else {
        return unsafe { py_none() };
    };
    let Some(mtime) = (unsafe { unsigned_argument(*args.add(9)) }) else {
        return unsafe { py_none() };
    };
    let Some(filetype) = (unsafe { bytes_argument(*args.add(10)) }) else {
        return ptr::null_mut();
    };
    let Some(devmajor) = (unsafe { unsigned_argument(*args.add(11)) }) else {
        return unsafe { py_none() };
    };
    let Some(devminor) = (unsafe { unsigned_argument(*args.add(12)) }) else {
        return unsafe { py_none() };
    };

    if name.len() > 100 || prefix.len() > 155 || linkname.len() > 100
        || filetype.len() != 1 || uname.len() > 32 || gname.len() > 32
        || mode > 0o7777 || uid >= 8u64.pow(7) || gid >= 8u64.pow(7)
        || size >= 8u64.pow(11) || mtime >= 8u64.pow(11)
    {
        return unsafe { py_none() };
    }
    let is_device = matches!(filetype[0], b'3' | b'4');
    if is_device && (devmajor >= 8u64.pow(7) || devminor >= 8u64.pow(7)) {
        return unsafe { py_none() };
    }

    let mut header = Header::new_ustar();
    let Some(ustar) = header.as_ustar_mut() else {
        return unsafe { py_none() };
    };
    copy_field(&mut ustar.name, &name);
    copy_field(&mut ustar.prefix, &prefix);
    copy_field(&mut ustar.linkname, &linkname);
    copy_field(&mut ustar.uname, &uname);
    copy_field(&mut ustar.gname, &gname);
    header.set_mode(mode as u32);
    header.set_uid(uid);
    header.set_gid(gid);
    header.set_size(size);
    header.set_mtime(mtime);
    header.set_entry_type(EntryType::new(filetype[0]));
    if is_device {
        if header.set_device_major(devmajor as u32).is_err()
            || header.set_device_minor(devminor as u32).is_err()
        {
            return unsafe { py_none() };
        }
    }
    header.set_cksum();
    let Some(checksum) = header.cksum().ok() else {
        return unsafe { py_none() };
    };
    let checksum = format!("{checksum:06o}\0 ");
    header.as_mut_bytes()[148..156].copy_from_slice(checksum.as_bytes());
    unsafe { py_bytes(header.as_bytes()) }
}

fn copy_field<const N: usize>(field: &mut [u8; N], value: &[u8]) {
    field[..value.len()].copy_from_slice(value);
}

fn has_nonstandard_numeric_encoding(bytes: &[u8]) -> bool {
    bytes[0] & 0x80 != 0
        && (bytes[0] != 0x80
            || (bytes.len() == 12 && bytes[1..4].iter().any(|byte| *byte != 0)))
}

unsafe extern "C" fn parse_ustar_header(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return unsafe { py_none() };
    }
    let Some(bytes) = (unsafe { bytes_argument(*args) }) else {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { py_none() };
    };
    if bytes.len() != 512 {
        return unsafe { py_none() };
    }

    let header = Header::from_byte_slice(&bytes);
    if header.as_ustar().is_none() {
        return unsafe { py_none() };
    }
    let raw = header.as_bytes();
    let filetype = raw[156];
    if matches!(filetype, b'L' | b'K' | b'S') {
        return unsafe { py_none() };
    }

    let raw_mode = &raw[100..108];
    let raw_uid = &raw[108..116];
    let raw_gid = &raw[116..124];
    let raw_size = &raw[124..136];
    let raw_mtime = &raw[136..148];
    let raw_chksum = &raw[148..156];
    let raw_devmajor = &raw[329..337];
    let raw_devminor = &raw[337..345];
    if [raw_mode, raw_uid, raw_gid, raw_size, raw_mtime, raw_chksum,
        raw_devmajor, raw_devminor]
        .iter()
        .any(|field| has_nonstandard_numeric_encoding(field))
    {
        return unsafe { py_none() };
    }

    let mode = number_field(raw_mode, header.mode().map(u64::from));
    let uid = number_field(raw_uid, header.uid());
    let gid = number_field(raw_gid, header.gid());
    let size = number_field(raw_size, header.entry_size());
    let mtime = number_field(raw_mtime, header.mtime());
    let checksum = number_field(raw_chksum, header.cksum().map(u64::from));
    let devmajor = optional_number_field(raw_devmajor, header.device_major());
    let devminor = optional_number_field(raw_devminor, header.device_minor());
    let (Some(mode), Some(uid), Some(gid), Some(size), Some(mtime), Some(checksum),
        Some(devmajor), Some(devminor)) =
        (mode, uid, gid, size, mtime, checksum, devmajor, devminor)
    else {
        return unsafe { py_none() };
    };

    let fields = vec![
        unsafe { py_bytes(&raw[0..100]) },
        unsafe { py_uint(mode) },
        unsafe { py_uint(uid) },
        unsafe { py_uint(gid) },
        unsafe { py_uint(size) },
        unsafe { py_uint(mtime) },
        unsafe { py_uint(checksum) },
        unsafe { py_bytes(&[filetype]) },
        unsafe { py_bytes(&raw[157..257]) },
        unsafe { py_bytes(&raw[265..297]) },
        unsafe { py_bytes(&raw[297..329]) },
        unsafe { py_uint(devmajor) },
        unsafe { py_uint(devminor) },
        unsafe { py_bytes(&raw[345..500]) },
    ];
    unsafe { tuple_from_fields(fields) }
}

pub extern "C" fn tarfile_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn tarfile_rs_free(_object: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"create_ustar_header".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: create_ustar_header,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a USTAR header using tar-rs.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_ustar_header".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_ustar_header,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a standard USTAR header using tar-rs.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_tarfile_rs".as_ptr() as *mut _,
        m_doc: c"Rust USTAR header support for tarfile.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(tarfile_rs_clear),
        m_free: Some(tarfile_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__tarfile_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
