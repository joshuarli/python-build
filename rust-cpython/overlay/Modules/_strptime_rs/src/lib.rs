use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use chrono::{Datelike, Weekday};
use chrono::format::Parsed;
use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyLong_FromLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyUnicode_AsUTF8AndSize;

const MISSING: i64 = i64::MIN;

struct LocaleData {
    full_weekdays: Vec<String>,
    short_weekdays: Vec<String>,
    full_months: Vec<String>,
    short_months: Vec<String>,
    am_pm: Vec<String>,
    timezones: Vec<Vec<String>>,
    tzname: Vec<String>,
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

unsafe fn read_unicode(object: *mut PyObject) -> Option<String> {
    let mut size: Py_ssize_t = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if bytes.is_null() || size < 0 {
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), size as usize) };
    let text = unsafe { std::str::from_utf8_unchecked(bytes) };
    Some(text.to_owned())
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

unsafe fn tuple_strings(tuple: *mut PyObject) -> Option<Vec<String>> {
    let size = unsafe { tuple_len(tuple) }?;
    let mut values = Vec::with_capacity(size);
    for index in 0..size {
        let item = unsafe { tuple_item(tuple, index) }?;
        values.push(unsafe { read_unicode(item) }?);
    }
    Some(values)
}

unsafe fn tuple_string_groups(tuple: *mut PyObject) -> Option<Vec<Vec<String>>> {
    let size = unsafe { tuple_len(tuple) }?;
    let mut groups = Vec::with_capacity(size);
    for index in 0..size {
        let item = unsafe { tuple_item(tuple, index) }?;
        groups.push(unsafe { tuple_strings(item) }?);
    }
    Some(groups)
}

unsafe fn read_groups(tuple: *mut PyObject) -> Option<Vec<(String, String)>> {
    let size = unsafe { tuple_len(tuple) }?;
    let mut groups = Vec::with_capacity(size);
    for index in 0..size {
        let pair = unsafe { tuple_item(tuple, index) }?;
        if unsafe { tuple_len(pair) }? != 2 {
            return None;
        }
        let key = unsafe { read_unicode(tuple_item(pair, 0)?) }?;
        let value = unsafe { read_unicode(tuple_item(pair, 1)?) }?;
        groups.push((key, value));
    }
    Some(groups)
}

fn group_value<'a>(groups: &'a [(String, String)], key: &str) -> Option<&'a str> {
    groups
        .iter()
        .find_map(|(group, value)| (group == key).then_some(value.as_str()))
}

fn parse_decimal(value: &str) -> Option<i64> {
    if !value.is_ascii() {
        return None;
    }
    value.parse().ok()
}

fn find_locale_name(value: &str, names: &[String]) -> Option<i64> {
    let value = value.to_lowercase();
    names
        .iter()
        .position(|name| name == &value)
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
    let hours = parse_decimal(std::str::from_utf8(bytes.get(1..3)?).ok()?)?;
    let minutes = parse_decimal(std::str::from_utf8(bytes.get(3..5)?).ok()?)?;
    let seconds = if bytes.len() >= 7 {
        parse_decimal(std::str::from_utf8(bytes.get(5..7)?).ok()?)?
    } else {
        0
    };
    let remainder = if bytes.len() > 8 {
        std::str::from_utf8(bytes.get(8..)?).ok()?
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
    groups: &[(String, String)],
    locale: &LocaleData,
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
    for (key, value) in groups {
        match key.as_str() {
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
                fields.month = find_locale_name(value, locale.full_months.get(1..)?)? + 1;
                fields.has_month = true;
            }
            "b" => {
                fields.month = find_locale_name(value, locale.short_months.get(1..)?)? + 1;
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
                let am_pm = group_value(groups, "p").unwrap_or("").to_lowercase();
                let is_pm = locale.am_pm.get(1).is_some_and(|pm| pm == &am_pm);
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
            "A" => fields.weekday = Some(find_locale_name(value, &locale.full_weekdays)?),
            "a" => fields.weekday = Some(find_locale_name(value, &locale.short_weekdays)?),
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
                let found_zone = value.to_lowercase();
                for (index, timezone_names) in locale.timezones.iter().enumerate() {
                    if timezone_names.iter().any(|name| name == &found_zone) {
                        if locale.tzname.len() == 2
                            && locale.tzname[0] == locale.tzname[1]
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
    let groups = match unsafe { read_groups(*args) } {
        Some(groups) => groups,
        None => {
            if !unsafe { PyErr_Occurred() }.is_null() {
                return ptr::null_mut();
            }
            return unsafe { PyTuple_New(0) };
        }
    };
    let full_weekdays = match unsafe { tuple_strings(*args.add(1)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let short_weekdays = match unsafe { tuple_strings(*args.add(2)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let full_months = match unsafe { tuple_strings(*args.add(3)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let short_months = match unsafe { tuple_strings(*args.add(4)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let am_pm = match unsafe { tuple_strings(*args.add(5)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let timezones = match unsafe { tuple_string_groups(*args.add(6)) } {
        Some(values) => values,
        None => return unsafe { PyTuple_New(0) },
    };
    let tzname = match unsafe { tuple_strings(*args.add(7)) } {
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
        None => return unsafe { PyTuple_New(0) },
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
            m_slots: ptr::null_mut(),
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
