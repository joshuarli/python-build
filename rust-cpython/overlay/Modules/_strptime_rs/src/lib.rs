//! Date and time directive conversion using call-scoped Python buffers.
#![no_std]
#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

extern crate alloc;

use alloc::{borrow::ToOwned, format};
use core::alloc::{GlobalAlloc, Layout};
use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;
use core::slice;

use chrono::{Datelike, Weekday};
use chrono::format::Parsed;

// These C layouts describe the 64-bit, GIL-enabled CPython module boundary.
type Py_ssize_t = isize;

#[repr(C)]
pub struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut PyTypeObject,
}

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject,
    Void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

impl PyMethodDef {
    const fn zeroed() -> Self {
        Self {
            ml_name: core::ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer { Void: core::ptr::null_mut() },
            ml_flags: 0,
            ml_doc: core::ptr::null_mut(),
        }
    }
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
struct PyModuleDef_Slot {
    slot: c_int,
    value: *mut c_void,
}

type VisitProc = Option<unsafe extern "C" fn(*mut PyObject, *mut c_void) -> c_int>;
type TraverseProc = unsafe extern "C" fn(*mut PyObject, VisitProc, *mut c_void) -> c_int;

#[repr(C)]
struct PyModuleDef {
    m_base: PyModuleDef_Base,
    m_name: *const c_char,
    m_doc: *const c_char,
    m_size: Py_ssize_t,
    m_methods: *mut PyMethodDef,
    m_slots: *mut PyModuleDef_Slot,
    m_traverse: Option<TraverseProc>,
    m_clear: Option<unsafe extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<unsafe extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
// CPython 3.16 full-API module slot and independent-GIL capability values.
const Py_mod_multiple_interpreters: c_int = 86;
const Py_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2_usize as *mut c_void;
// Immortal reference count and static allocation flags in the 64-bit GIL ABI.
const PyModuleDef_HEAD_INIT: PyModuleDef_Base = PyModuleDef_Base {
    ob_base: PyObject {
        ob_refcnt: (3_isize << 30) | (5_isize << 48),
        ob_type: core::ptr::null_mut(),
    },
    m_init: None,
    m_index: 0,
    m_copy: core::ptr::null_mut(),
};

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    fn Py_DecRef(object: *mut PyObject);
    fn PyErr_Occurred() -> *mut PyObject;
    fn PyLong_AsLong(object: *mut PyObject) -> core::ffi::c_long;
    fn PyLong_FromLongLong(value: i64) -> *mut PyObject;
    fn PyTuple_GetItem(tuple: *mut PyObject, index: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    fn PyTuple_Size(tuple: *mut PyObject) -> Py_ssize_t;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyUnicode_FromStringAndSize(bytes: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn PyObject_CallMethod(object: *mut PyObject, name: *const c_char, format: *const c_char, ...) -> *mut PyObject;
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyMem_Malloc(size: usize) -> *mut c_void;
    fn PyMem_Realloc(pointer: *mut c_void, size: usize) -> *mut c_void;
    fn PyMem_Free(pointer: *mut c_void);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

// Temporary strings live until conversion returns under the active interpreter's
// GIL. Offset normalization and fraction padding reuse Python's pools for small
// allocations, keeping freed blocks in the interpreter's existing pools.
struct PythonAllocator;

unsafe impl GlobalAlloc for PythonAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if layout.align() <= core::mem::align_of::<usize>() {
            return unsafe { PyMem_Malloc(layout.size()).cast() };
        }
        let Some(size) = layout.size().checked_add(layout.align()) else {
            return core::ptr::null_mut();
        };
        let base = unsafe { PyMem_Malloc(size).cast::<u8>() };
        if base.is_null() {
            return base;
        }
        let offset = layout.align() - (base as usize % layout.align());
        let aligned = unsafe { base.add(offset) };
        unsafe { aligned.sub(core::mem::size_of::<usize>()).cast::<*mut u8>().write(base) };
        aligned
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        let base = if layout.align() <= core::mem::align_of::<usize>() {
            pointer
        } else {
            unsafe { pointer.sub(core::mem::size_of::<usize>()).cast::<*mut u8>().read() }
        };
        unsafe { PyMem_Free(base.cast()) };
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if layout.align() <= core::mem::align_of::<usize>() {
            return unsafe { PyMem_Realloc(pointer.cast(), size).cast() };
        }
        let Ok(replacement_layout) = Layout::from_size_align(size, layout.align()) else {
            return core::ptr::null_mut();
        };
        let replacement = unsafe { self.alloc(replacement_layout) };
        if !replacement.is_null() {
            unsafe {
                core::ptr::copy_nonoverlapping(pointer, replacement, layout.size().min(size));
                self.dealloc(pointer, layout);
            }
        }
        replacement
    }
}

#[global_allocator]
static ALLOCATOR: PythonAllocator = PythonAllocator;

const MISSING: i64 = i64::MIN;

struct LocaleData<'py> {
    full_weekdays: TupleStrings<'py>,
    short_weekdays: TupleStrings<'py>,
    full_months: TupleStrings<'py>,
    short_months: TupleStrings<'py>,
    am_pm: TupleStrings<'py>,
    timezones: TupleStringGroups<'py>,
    tzname: TupleStrings<'py>,
    daylight: bool,
}

struct Fields {
    iso_year: Option<i64>,
    year: Option<i64>,
    month: i64,
    day: i64,
    hour: i64,
    minute: i64,
    second: i64,
    fraction: i64,
    timezone: i64,
    utc_offset: Option<i64>,
    utc_offset_fraction: i64,
    iso_week: Option<i64>,
    week_of_year: Option<i64>,
    week_start: Option<i64>,
    weekday: Option<i64>,
    julian: Option<i64>,
    has_month: bool,
    has_day: bool,
    has_hour: bool,
    has_minute: bool,
    has_second: bool,
    has_fraction: bool,
}

impl Fields {
    fn new() -> Self {
        Self {
            iso_year: None,
            year: None,
            month: 1,
            day: 1,
            hour: 0,
            minute: 0,
            second: 0,
            fraction: 0,
            timezone: -1,
            utc_offset: None,
            utc_offset_fraction: 0,
            iso_week: None,
            week_of_year: None,
            week_start: None,
            weekday: None,
            julian: None,
            has_month: false,
            has_day: false,
            has_hour: false,
            has_minute: false,
            has_second: false,
            has_fraction: false,
        }
    }
}

// The caller holds the argument tuples and the GIL throughout conversion.
// Their Unicode buffers remain valid until parsing returns; no slice is cached.
unsafe fn read_unicode<'py>(
    object: *mut PyObject,
    _owners: &'py [*mut PyObject],
) -> Option<&'py str> {
    let mut size: Py_ssize_t = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if bytes.is_null() || size < 0 {
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), size as usize) };
    let text = unsafe { core::str::from_utf8_unchecked(bytes) };
    Some(text)
}

unsafe fn tuple_item(tuple: *mut PyObject, index: usize) -> Option<*mut PyObject> {
    if index > isize::MAX as usize {
        return None;
    }
    let item = unsafe { PyTuple_GetItem(tuple, index as Py_ssize_t) };
    (!item.is_null()).then_some(item)
}

unsafe fn tuple_len(tuple: *mut PyObject) -> Option<usize> {
    let size = unsafe { PyTuple_Size(tuple) };
    (size >= 0).then_some(size as usize)
}

// Views only refer to immutable tuples reachable from the held call arguments.
// Validation and iteration cannot invoke user code; no view is stored in module state.
#[derive(Clone, Copy)]
struct PythonTuple<'py> {
    tuple: *mut PyObject,
    size: usize,
    owners: &'py [*mut PyObject],
}

impl<'py> PythonTuple<'py> {
    // The tuple must be an argument or be owned by another immutable argument tuple.
    unsafe fn new(tuple: *mut PyObject, owners: &'py [*mut PyObject]) -> Option<Self> {
        Some(Self {
            tuple,
            size: unsafe { tuple_len(tuple) }?,
            owners,
        })
    }

    fn item(&self, index: usize) -> Option<*mut PyObject> {
        if index >= self.size {
            return None;
        }
        unsafe { tuple_item(self.tuple, index) }
    }
}

struct TupleStrings<'py>(PythonTuple<'py>);

impl<'py> TupleStrings<'py> {
    fn len(&self) -> usize {
        self.0.size
    }

    fn get(&self, index: usize) -> Option<&'py str> {
        unsafe { read_unicode(self.0.item(index)?, self.0.owners) }
    }

    fn iter(&self) -> impl Iterator<Item = &'py str> + '_ {
        (0..self.len()).map(|index| self.get(index).expect("validated Unicode tuple"))
    }
}

unsafe fn tuple_strings<'py>(
    tuple: *mut PyObject,
    owners: &'py [*mut PyObject],
) -> Option<TupleStrings<'py>> {
    let values = TupleStrings(unsafe { PythonTuple::new(tuple, owners) }?);
    for index in 0..values.len() {
        values.get(index)?;
    }
    Some(values)
}

struct TupleStringGroups<'py>(PythonTuple<'py>);

impl<'py> TupleStringGroups<'py> {
    fn len(&self) -> usize {
        self.0.size
    }

    fn iter(&self) -> impl Iterator<Item = TupleStrings<'py>> + '_ {
        (0..self.len()).map(|index| unsafe {
            tuple_strings(self.0.item(index).expect("validated tuple group"), self.0.owners)
                .expect("validated Unicode tuple group")
        })
    }
}

unsafe fn tuple_string_groups<'py>(
    tuple: *mut PyObject,
    owners: &'py [*mut PyObject],
) -> Option<TupleStringGroups<'py>> {
    let groups = TupleStringGroups(unsafe { PythonTuple::new(tuple, owners) }?);
    for index in 0..groups.len() {
        unsafe { tuple_strings(groups.0.item(index)?, owners) }?;
    }
    Some(groups)
}

struct DirectiveGroups<'py>(PythonTuple<'py>);

impl<'py> DirectiveGroups<'py> {
    fn pair(&self, index: usize) -> Option<(&'py str, &'py str)> {
        let pair = self.0.item(index)?;
        if unsafe { tuple_len(pair) }? != 2 {
            return None;
        }
        let key = unsafe { read_unicode(tuple_item(pair, 0)?, self.0.owners) }?;
        let value = unsafe { read_unicode(tuple_item(pair, 1)?, self.0.owners) }?;
        Some((key, value))
    }

    fn iter(&self) -> impl Iterator<Item = (&'py str, &'py str)> + '_ {
        (0..self.0.size).map(|index| self.pair(index).expect("validated directive pair"))
    }
}

unsafe fn read_groups<'py>(
    tuple: *mut PyObject,
    owners: &'py [*mut PyObject],
) -> Option<DirectiveGroups<'py>> {
    let groups = DirectiveGroups(unsafe { PythonTuple::new(tuple, owners) }?);
    for index in 0..groups.0.size {
        groups.pair(index)?;
    }
    Some(groups)
}

fn group_value<'py>(groups: &DirectiveGroups<'py>, key: &str) -> Option<&'py str> {
    groups.iter().find_map(|(group, value)| (group == key).then_some(value))
}

fn parse_decimal(value: &str) -> Option<i64> {
    if !value.is_ascii() {
        return None;
    }
    value.parse().ok()
}

// Exact Unicode objects use CPython's casing tables without invoking an input
// subclass override. Both temporary owners die under the calling interpreter's GIL.
struct Lowercase(*mut PyObject);

impl Lowercase {
    fn new(value: &str) -> Option<Self> {
        let source = unsafe { PyUnicode_FromStringAndSize(value.as_ptr().cast(), value.len().try_into().ok()?) };
        if source.is_null() {
            return None;
        }
        let result = unsafe { PyObject_CallMethod(source, c"lower".as_ptr(), ptr::null()) };
        unsafe { Py_DecRef(source) };
        (!result.is_null()).then_some(Self(result))
    }

    fn text(&self) -> Option<&str> {
        let mut size = 0;
        let bytes = unsafe { PyUnicode_AsUTF8AndSize(self.0, &mut size) };
        if bytes.is_null() || size < 0 {
            return None;
        }
        Some(unsafe { core::str::from_utf8_unchecked(slice::from_raw_parts(bytes.cast(), size as usize)) })
    }
}

impl Drop for Lowercase {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) };
    }
}

fn find_locale_name<'py>(
    value: &str,
    mut names: impl Iterator<Item = &'py str>,
) -> Option<i64> {
    let lowercase = Lowercase::new(value)?;
    let value = lowercase.text()?;
    names
        .position(|name| name == value)
        .map(|index| index as i64)
}

fn python_weekday(value: i64) -> Option<Weekday> {
    match value {
        0 => Some(Weekday::Mon),
        1 => Some(Weekday::Tue),
        2 => Some(Weekday::Wed),
        3 => Some(Weekday::Thu),
        4 => Some(Weekday::Fri),
        5 => Some(Weekday::Sat),
        6 => Some(Weekday::Sun),
        _ => None,
    }
}

fn parse_utc_offset(value: &str) -> Option<(Option<i64>, i64)> {
    if value.is_empty() {
        return Some((None, 0));
    }
    if value == "Z" {
        return Some((Some(0), 0));
    }

    let mut value = value.to_owned();
    if value.as_bytes().get(3) == Some(&b':') {
        value.remove(3);
        if value.len() > 5 {
            if value.as_bytes().get(5) != Some(&b':') {
                return None;
            }
            value.remove(5);
        }
    }

    let bytes = value.as_bytes();
    if bytes.len() < 5 || !matches!(bytes[0], b'+' | b'-') {
        return None;
    }
    let hours = parse_decimal(core::str::from_utf8(bytes.get(1..3)?).ok()?)?;
    let minutes = parse_decimal(core::str::from_utf8(bytes.get(3..5)?).ok()?)?;
    let seconds = if bytes.len() >= 7 {
        parse_decimal(core::str::from_utf8(bytes.get(5..7)?).ok()?)?
    } else {
        0
    };
    let remainder = if bytes.len() > 8 {
        core::str::from_utf8(bytes.get(8..)?).ok()?
    } else {
        ""
    };
    if remainder.len() > 6 || !remainder.is_ascii() {
        return None;
    }
    let fraction = if remainder.is_empty() {
        0
    } else {
        let padded = format!("{remainder:0<6}");
        parse_decimal(&padded)?
    };
    let sign = if bytes[0] == b'-' { -1 } else { 1 };
    let seconds = (hours * 3600 + minutes * 60 + seconds) * sign;
    Some((Some(seconds), fraction * sign))
}

fn convert_groups(
    groups: &DirectiveGroups<'_>,
    locale: &LocaleData<'_>,
) -> Option<[i64; 16]> {
    if locale.full_weekdays.len() != 7
        || locale.short_weekdays.len() != 7
        || locale.full_months.len() != 13
        || locale.short_months.len() != 13
        || locale.am_pm.len() != 2
        || locale.timezones.len() != 2
        || locale.tzname.len() != 2
    {
        return None;
    }
    let mut fields = Fields::new();
    for (key, value) in groups.iter() {
        match key {
            "y" => {
                let mut year = parse_decimal(value)?;
                if let Some(century) = group_value(groups, "C") {
                    year += parse_decimal(century)? * 100;
                } else if year <= 68 {
                    year += 2000;
                } else {
                    year += 1900;
                }
                fields.year = Some(year);
            }
            "Y" => fields.year = Some(parse_decimal(value)?),
            "G" => fields.iso_year = Some(parse_decimal(value)?),
            "C" | "p" => {}
            "m" => {
                fields.month = parse_decimal(value)?;
                fields.has_month = true;
            }
            "B" => {
                fields.month = find_locale_name(value, locale.full_months.iter().skip(1))? + 1;
                fields.has_month = true;
            }
            "b" => {
                fields.month = find_locale_name(value, locale.short_months.iter().skip(1))? + 1;
                fields.has_month = true;
            }
            "d" => {
                fields.day = parse_decimal(value)?;
                fields.has_day = true;
            }
            "H" => {
                fields.hour = parse_decimal(value)?;
                fields.has_hour = true;
            }
            "I" => {
                let mut hour = parse_decimal(value)?;
                let lowercase = Lowercase::new(group_value(groups, "p").unwrap_or(""))?;
                let am_pm = lowercase.text()?;
                let is_pm = locale.am_pm.get(1).is_some_and(|pm| pm == am_pm);
                if is_pm {
                    if hour != 12 {
                        hour += 12;
                    }
                } else if hour == 12 {
                    hour = 0;
                }
                fields.hour = hour;
                fields.has_hour = true;
            }
            "M" => {
                fields.minute = parse_decimal(value)?;
                fields.has_minute = true;
            }
            "S" => {
                fields.second = parse_decimal(value)?;
                fields.has_second = true;
            }
            "f" => {
                if value.is_empty() || value.len() > 6 || !value.is_ascii() {
                    return None;
                }
                let padded = format!("{value:0<6}");
                fields.fraction = parse_decimal(&padded)?;
                fields.has_fraction = true;
            }
            "A" => fields.weekday = Some(find_locale_name(value, locale.full_weekdays.iter())?),
            "a" => fields.weekday = Some(find_locale_name(value, locale.short_weekdays.iter())?),
            "w" => {
                let day = parse_decimal(value)?;
                fields.weekday = Some(if day == 0 { 6 } else { day - 1 });
            }
            "u" => fields.weekday = Some(parse_decimal(value)? - 1),
            "j" => fields.julian = Some(parse_decimal(value)?),
            "U" => {
                fields.week_of_year = Some(parse_decimal(value)?);
                fields.week_start = Some(6);
            }
            "W" => {
                fields.week_of_year = Some(parse_decimal(value)?);
                fields.week_start = Some(0);
            }
            "V" => fields.iso_week = Some(parse_decimal(value)?),
            "z" | "colon_z" => {
                (fields.utc_offset, fields.utc_offset_fraction) = parse_utc_offset(value)?;
            }
            "Z" => {
                let lowercase = Lowercase::new(value)?;
                let found_zone = lowercase.text()?;
                for (index, timezone_names) in locale.timezones.iter().enumerate() {
                    if timezone_names.iter().any(|name| name == found_zone) {
                        if locale.tzname.len() == 2
                            && locale.tzname.get(0)? == locale.tzname.get(1)?
                            && locale.daylight
                            && found_zone != "utc"
                            && found_zone != "gmt"
                        {
                            break;
                        }
                        fields.timezone = index as i64;
                        break;
                    }
                }
            }
            _ => return None,
        }
    }

    let mut parsed = Parsed::new();
    if let Some(year) = fields.year {
        parsed.set_year(year).ok()?;
    }
    if let Some(year) = fields.iso_year {
        parsed.set_isoyear(year).ok()?;
    }
    if fields.has_month {
        parsed.set_month(fields.month).ok()?;
    }
    if fields.has_day {
        parsed.set_day(fields.day).ok()?;
    }
    if fields.has_hour {
        parsed.set_hour(fields.hour).ok()?;
    }
    if fields.has_minute {
        parsed.set_minute(fields.minute).ok()?;
    }
    if fields.has_second {
        parsed.set_second(fields.second).ok()?;
    }
    if fields.has_fraction {
        parsed.set_nanosecond(fields.fraction * 1000).ok()?;
    }
    if let Some(weekday) = fields.weekday {
        parsed.set_weekday(python_weekday(weekday)?).ok()?;
    }
    if let Some(julian) = fields.julian {
        parsed.set_ordinal(julian).ok()?;
    }
    if let Some(week) = fields.week_of_year {
        match fields.week_start {
            Some(6) => parsed.set_week_from_sun(week).ok()?,
            Some(0) => parsed.set_week_from_mon(week).ok()?,
            _ => return None,
        }
    }
    if let Some(week) = fields.iso_week {
        parsed.set_isoweek(week).ok()?;
    }

    if fields.year.is_some()
        && fields.has_month
        && fields.has_day
        && fields.iso_year.is_none()
        && fields.week_of_year.is_none()
        && fields.iso_week.is_none()
        && fields.julian.is_none()
    {
        if let Ok(date) = parsed.to_naive_date() {
            if fields.weekday.is_none() {
                fields.weekday = Some(i64::from(date.weekday().num_days_from_monday()));
            }
            fields.julian = Some(i64::from(date.ordinal()));
        }
    }

    Some([
        fields.iso_year.unwrap_or(MISSING),
        fields.year.unwrap_or(MISSING),
        parsed.month().map(i64::from).unwrap_or(1),
        parsed.day().map(i64::from).unwrap_or(1),
        parsed.hour_div_12().zip(parsed.hour_mod_12()).map_or(0, |(half, hour)| {
            i64::from(half * 12 + hour)
        }),
        parsed.minute().map(i64::from).unwrap_or(0),
        parsed.second().map(i64::from).unwrap_or(0),
        parsed.nanosecond().map_or(0, |value| i64::from(value / 1000)),
        fields.timezone,
        fields.utc_offset.unwrap_or(MISSING),
        fields.utc_offset_fraction,
        fields.iso_week.unwrap_or(MISSING),
        fields.week_of_year.unwrap_or(MISSING),
        fields.week_start.unwrap_or(MISSING),
        parsed.weekday().map_or(MISSING, |weekday| {
            i64::from(weekday.num_days_from_monday())
        }),
        fields.julian.unwrap_or(MISSING),
    ])
}

unsafe fn parse_groups_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 9 {
        return unsafe { PyTuple_New(0) };
    }
    let owners = unsafe { slice::from_raw_parts(args, nargs as usize) };
    let groups = match unsafe { read_groups(owners[0], owners) } {
        Some(groups) => groups,
        None => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            return unsafe { PyTuple_New(0) };
        }
    };
    let full_weekdays = match unsafe { tuple_strings(owners[1], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let short_weekdays = match unsafe { tuple_strings(owners[2], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let full_months = match unsafe { tuple_strings(owners[3], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let short_months = match unsafe { tuple_strings(owners[4], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let am_pm = match unsafe { tuple_strings(owners[5], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let timezones = match unsafe { tuple_string_groups(owners[6], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let tzname = match unsafe { tuple_strings(owners[7], owners) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let daylight = unsafe { PyLong_AsLong(*args.add(8)) };
    if daylight == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    let locale = LocaleData {
        full_weekdays,
        short_weekdays,
        full_months,
        short_months,
        am_pm,
        timezones,
        tzname,
        daylight: daylight != 0,
    };
    let fields = match convert_groups(&groups, &locale) {
        Some(fields) => fields,
        None => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            return unsafe { PyTuple_New(0) };
        }
    };

    let result = unsafe { PyTuple_New(fields.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, value) in fields.iter().copied().enumerate() {
        let item = unsafe { PyLong_FromLongLong(value) };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

unsafe extern "C" fn parse_groups(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { parse_groups_impl(args, nargs) }
}

pub extern "C" fn _strptime_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _strptime_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 2]);

unsafe impl Sync for ModuleSlots {}

// Conversion keeps buffers within each call and holds no shared Python references.
static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: Py_mod_multiple_interpreters,
        value: Py_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

pub static _STRPTIME_RS_MODULE_METHODS: [PyMethodDef; 2] = {
    [
        PyMethodDef {
            ml_name: c"parse_groups".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer {
                PyCFunctionFast: parse_groups,
            },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Parse matched strptime directive fields.".as_ptr() as *mut c_char,
        },
        PyMethodDef::zeroed(),
    ]
};

pub static _STRPTIME_RS_MODULE: ModuleDef = {
    ModuleDef {
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_strptime_rs".as_ptr() as *mut _,
            m_doc: c"Rust strptime directive field parser.".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_STRPTIME_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
            m_traverse: None,
            m_clear: Some(_strptime_rs_clear),
            m_free: Some(_strptime_rs_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__strptime_rs() -> *mut PyObject {
    _STRPTIME_RS_MODULE.init_multi_phase()
}
