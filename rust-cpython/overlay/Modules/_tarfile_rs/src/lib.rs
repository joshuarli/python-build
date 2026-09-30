//! Bounded USTAR header processing without a Rust allocator or runtime.
#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;

type Py_ssize_t = isize;

#[repr(C)]
struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut PyTypeObject,
}

#[repr(C)]
struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    void: *mut c_void,
}

#[repr(C)]
struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
struct PyModuleDef {
    m_base: PyModuleDef_Base,
    m_name: *const c_char,
    m_doc: *const c_char,
    m_size: Py_ssize_t,
    m_methods: *mut PyMethodDef,
    m_slots: *mut c_void,
    m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
/// `_Py_IMMORTAL_INITIAL_REFCNT | ((_Py_STATICALLY_ALLOCATED_FLAG |
/// _Py_IMMORTAL_FLAGS) << 48)` for the 64-bit GIL-enabled build.
const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut _Py_NoneStruct: PyObject;
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyBytes_AsStringAndSize(object: *mut PyObject, data: *mut *mut c_char,
                              length: *mut Py_ssize_t) -> c_int;
    fn PyBytes_FromStringAndSize(data: *const c_char, length: Py_ssize_t) -> *mut PyObject;
    fn PyLong_AsUnsignedLongLong(object: *mut PyObject) -> u64;
    fn PyLong_FromUnsignedLongLong(value: u64) -> *mut PyObject;
    fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    fn PyErr_Clear();
    fn PyErr_Occurred() -> *mut PyObject;
    fn PyTuple_New(length: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, value: *mut PyObject) -> c_int;
    fn Py_NewRef(object: *mut PyObject) -> *mut PyObject;
    fn Py_DecRef(object: *mut PyObject);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

// FASTCALL arguments keep these immutable bytes alive for the entire call.
unsafe fn bytes_argument<'a>(object: *mut PyObject) -> Option<&'a [u8]> {
    let mut data = ptr::null_mut();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut data, &mut length) } != 0 || length < 0 {
        return None;
    }
    let bytes = unsafe { core::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(bytes)
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

unsafe fn tuple_from_fields<const N: usize>(fields: [*mut PyObject; N]) -> *mut PyObject {
    // Constructed fields remain owned here until they are handed to the tuple.
    let tuple = if fields.iter().any(|field| field.is_null()) {
        ptr::null_mut()
    } else {
        unsafe { PyTuple_New(N as Py_ssize_t) }
    };
    if tuple.is_null() {
        for field in fields {
            if !field.is_null() {
                unsafe { Py_DecRef(field) };
            }
        }
        return ptr::null_mut();
    }
    for (index, field) in fields.iter().copied().enumerate() {
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, field) } != 0 {
            for remaining in &fields[index + 1..] {
                unsafe { Py_DecRef(*remaining) };
            }
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
    }
    tuple
}

// Numeric fields are bounded by their fixed width; unsupported encodings
// return None so the caller retains its complete compatibility parser.
fn number_field(field: &[u8], binary: bool) -> Option<u64> {
    if field.iter().all(|byte| *byte == 0 || *byte == b' ') {
        return Some(0);
    }
    if field[0] & 0x80 != 0 {
        if !binary || has_nonstandard_numeric_encoding(field) {
            return None;
        }
        return Some(field[1..].iter().fold(0, |value, byte| (value << 8) | u64::from(*byte)));
    }
    let end = field.iter().position(|byte| *byte == 0).unwrap_or(field.len());
    let text = core::str::from_utf8(&field[..end]).ok()?;
    u64::from_str_radix(text.trim(), 8).ok()
}

fn write_octal(field: &mut [u8], mut value: u64) {
    let digits = field.len() - 1;
    field[digits] = 0;
    for byte in field[..digits].iter_mut().rev() {
        *byte = b'0' + (value & 7) as u8;
        value >>= 3;
    }
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

    let mut header = [0u8; 512];
    header[..name.len()].copy_from_slice(name);
    header[345..345 + prefix.len()].copy_from_slice(prefix);
    header[157..157 + linkname.len()].copy_from_slice(linkname);
    header[265..265 + uname.len()].copy_from_slice(uname);
    header[297..297 + gname.len()].copy_from_slice(gname);
    header[257..265].copy_from_slice(b"ustar\x0000");
    write_octal(&mut header[100..108], mode);
    write_octal(&mut header[108..116], uid);
    write_octal(&mut header[116..124], gid);
    write_octal(&mut header[124..136], size);
    write_octal(&mut header[136..148], mtime);
    header[156] = if filetype[0] == 0 { b'0' } else { filetype[0] };
    if is_device {
        write_octal(&mut header[329..337], devmajor);
        write_octal(&mut header[337..345], devminor);
    }
    header[148..156].fill(b' ');
    let checksum = header.iter().map(|byte| u64::from(*byte)).sum();
    write_octal(&mut header[148..155], checksum);
    header[155] = b' ';
    unsafe { py_bytes(&header) }
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

    if &bytes[257..265] != b"ustar\x0000" {
        return unsafe { py_none() };
    }
    let raw = bytes;
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

    let mode = number_field(raw_mode, false);
    let uid = number_field(raw_uid, true);
    let gid = number_field(raw_gid, true);
    let size = number_field(raw_size, true);
    let mtime = number_field(raw_mtime, true);
    let checksum = number_field(raw_chksum, false);
    let devmajor = number_field(raw_devmajor, false);
    let devminor = number_field(raw_devminor, false);
    let (Some(mode), Some(uid), Some(gid), Some(size), Some(mtime), Some(checksum),
        Some(devmajor), Some(devminor)) =
        (mode, uid, gid, size, mtime, checksum, devmajor, devminor)
    else {
        return unsafe { py_none() };
    };

    let fields = [
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

unsafe extern "C" fn header_chksums(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return unsafe { py_none() };
    }
    let Some(bytes) = (unsafe { bytes_argument(*args) }) else {
        return ptr::null_mut();
    };
    if bytes.len() < 512 {
        return unsafe { py_none() };
    }
    // Both TAR conventions treat the checksum field as eight ASCII spaces.
    let mut unsigned = 256u64;
    let mut signed = 256i64;
    for byte in bytes[..148].iter().chain(&bytes[156..512]) {
        unsigned += u64::from(*byte);
        signed += i64::from(*byte as i8);
    }
    unsafe { tuple_from_fields([py_uint(unsigned), PyLong_FromLongLong(signed)]) }
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

static METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"create_ustar_header".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: create_ustar_header,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a USTAR header in Rust.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_ustar_header".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_ustar_header,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a standard USTAR header in Rust.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"header_chksums".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: header_chksums },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return unsigned and signed TAR header checksums.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: ptr::null_mut(),
        ml_meth: PyMethodDefFuncPointer { void: ptr::null_mut() },
        ml_flags: 0,
        ml_doc: ptr::null_mut(),
    },
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_Base {
            ob_base: PyObject { ob_refcnt: STATIC_IMMORTAL_REFCNT, ob_type: ptr::null_mut() },
            m_init: None,
            m_index: 0,
            m_copy: ptr::null_mut(),
        },
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
