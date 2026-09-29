use std::borrow::Cow;
use std::cell::UnsafeCell;
use std::collections::HashMap;
use std::ffi::{CStr, c_char, c_int, c_void};
use std::ptr;
use std::slice;
use std::str;

use cpython_sys::METH_O;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyDict_Contains;
use cpython_sys::PyDict_New;
use cpython_sys::PyDict_SetItem;
use cpython_sys::PyErr_Clear;
use cpython_sys::METH_FASTCALL;
use cpython_sys::PyObject_GetAttrString;
use cpython_sys::PyObject_Vectorcall;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::PyUnicode_Type;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_TYPE;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyBuffer_Release;
use cpython_sys::Py_ssize_t;
use cpython_sys::Py_buffer;
use quick_xml::events::{BytesEnd, BytesPI, BytesStart, BytesText, Event};
use quick_xml::name::ResolveResult;
use quick_xml::reader::NsReader;
use quick_xml::writer::Writer;
use quick_xml::XmlVersion;

const PYBUF_SIMPLE: c_int = 0;

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = std::mem::MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return None;
        }
        Some(Self {
            view: unsafe { view.assume_init() },
        })
    }

    fn bytes(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

fn new_bytes(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

fn invalid_event_stream() -> *mut PyObject {
    unsafe {
        PyErr_SetString(
            PyExc_ValueError,
            c"invalid ElementTree XML event stream".as_ptr(),
        );
    }
    ptr::null_mut()
}

fn valid_xml_characters(value: &str) -> bool {
    value.chars().all(|ch| {
        matches!(ch as u32, 0x9 | 0xA | 0xD)
            || matches!(ch as u32, 0x20..=0xD7FF | 0xE000..=0xFFFD | 0x10000..=0x10FFFF)
    })
}

fn valid_name_part(name: &str) -> bool {
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '.' | '-'))
}

fn valid_qname(name: &str) -> bool {
    let mut parts = name.split(':');
    let first = parts.next().unwrap_or_default();
    let second = parts.next();
    if parts.next().is_some() || !valid_name_part(first) {
        return false;
    }
    second.is_none_or(valid_name_part)
}

fn xml_declaration_end(text: &str) -> Option<usize> {
    if !text.starts_with("<?") {
        return Some(0);
    }
    let target_end = text[2..]
        .find(|ch| matches!(ch, ' ' | '\t' | '\r' | '\n' | '?'))?
        + 2;
    let target = &text[2..target_end];
    if !target.eq_ignore_ascii_case("xml") {
        return Some(0);
    }
    if target != "xml" {
        return None;
    }
    let rest = &text[target_end..];
    if !rest.chars().next().is_some_and(|ch| matches!(ch, ' ' | '\t' | '\r' | '\n')) {
        return None;
    }
    let end = text.find("?>")?;
    let declaration = &text[target_end..end];
    let mut fields = declaration.split_ascii_whitespace();
    let version = fields.next()?;
    if version != "version='1.0'" && version != "version=\"1.0\"" {
        return None;
    }
    let mut encoding_seen = false;
    let mut standalone_seen = false;
    for field in fields {
        if let Some(value) = field.strip_prefix("encoding=") {
            if encoding_seen || standalone_seen {
                return None;
            }
            encoding_seen = true;
            let encoding = if let Some(value) = value.strip_prefix('\'') {
                value.strip_suffix('\'')?
            } else {
                value.strip_prefix('"')?.strip_suffix('"')?
            };
            let encoding = encoding.to_ascii_lowercase();
            if !matches!(encoding.as_str(), "utf-8" | "utf8" | "us-ascii" | "ascii") {
                return None;
            }
            if matches!(encoding.as_str(), "us-ascii" | "ascii") && !text.is_ascii() {
                return None;
            }
        } else if let Some(value) = field.strip_prefix("standalone=") {
            if standalone_seen {
                return None;
            }
            standalone_seen = true;
            if !matches!(value, "'yes'" | "'no'" | "\"yes\"" | "\"no\"") {
                return None;
            }
        } else {
            return None;
        }
    }
    Some(end + 2)
}

fn common_document(text: &str) -> bool {
    if text.starts_with('\u{feff}') || text.contains("]]>") {
        return false;
    }
    let Some(_) = xml_declaration_end(text) else {
        return false;
    };
    true
}

fn expanded_name<'a>(result: ResolveResult<'_>, local: &'a str) -> Option<Cow<'a, str>> {
    match result {
        ResolveResult::Unbound => Some(Cow::Borrowed(local)),
        ResolveResult::Bound(namespace) => Some(Cow::Owned(format!("{{{}}}{local}", namespace.0))),
        ResolveResult::Unknown(_) => None,
    }
}

struct Obj(*mut PyObject);

impl Obj {
    fn new(raw: *mut PyObject) -> Parsed<Self> {
        if raw.is_null() { Err(Stop::PyError) } else { Ok(Self(raw)) }
    }
}

impl Drop for Obj {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) }
    }
}

enum Stop {
    Unsupported,
    PyError,
}

type Parsed<T> = Result<T, Stop>;

fn new_str(value: &str) -> Parsed<Obj> {
    Obj::new(unsafe {
        PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), value.len() as Py_ssize_t)
    })
}

/// Feeds parsed events straight into a Python `TreeBuilder`.
struct Sink {
    start: Obj,
    end: Obj,
    data: Obj,
    comment: Obj,
    // Tag and attribute-name objects are shared by every occurrence.
    names: HashMap<Box<str>, Obj>,
    open: Vec<*mut PyObject>,
    pending: String,
}

impl Sink {
    fn new(target: *mut PyObject) -> Parsed<Self> {
        let method = |name: &CStr| Obj::new(unsafe { PyObject_GetAttrString(target, name.as_ptr()) });
        Ok(Self {
            start: method(c"start")?,
            end: method(c"end")?,
            data: method(c"data")?,
            comment: method(c"comment")?,
            names: HashMap::new(),
            open: Vec::new(),
            pending: String::new(),
        })
    }

    fn name(&mut self, key: &str) -> Parsed<*mut PyObject> {
        if let Some(name) = self.names.get(key) {
            return Ok(name.0);
        }
        let object = new_str(key)?;
        let raw = object.0;
        self.names.insert(key.into(), object);
        Ok(raw)
    }

    fn call(callable: &Obj, args: &[*mut PyObject]) -> Parsed<()> {
        let result = Obj::new(unsafe {
            PyObject_Vectorcall(callable.0, args.as_ptr(), args.len(), ptr::null_mut())
        })?;
        drop(result);
        Ok(())
    }

    fn flush(&mut self) -> Parsed<()> {
        if self.pending.is_empty() {
            return Ok(());
        }
        let text = new_str(&self.pending)?;
        self.pending.clear();
        Self::call(&self.data, &[text.0])
    }

    fn text(&mut self, value: &str) {
        self.pending.push_str(value);
    }

    fn comment(&mut self, value: &str) -> Parsed<()> {
        self.flush()?;
        let text = new_str(value)?;
        Self::call(&self.comment, &[text.0])
    }

    fn start(&mut self, name: &str, attrs: Obj) -> Parsed<()> {
        self.flush()?;
        let tag = self.name(name)?;
        self.open.push(tag);
        Self::call(&self.start, &[tag, attrs.0])
    }

    fn end(&mut self) -> Parsed<()> {
        self.flush()?;
        let tag = self.open.pop().ok_or(Stop::Unsupported)?;
        Self::call(&self.end, &[tag])
    }
}

fn parse_document(input: &[u8], sink: &mut Sink) -> Parsed<()> {
    let Ok(text) = str::from_utf8(input) else {
        return Err(Stop::Unsupported);
    };
    if !common_document(text) || !valid_xml_characters(text) {
        return Err(Stop::Unsupported);
    }
    let declaration_at_start = xml_declaration_end(text).is_some_and(|end| end != 0);

    let mut reader = NsReader::from_reader(input);
    reader.config_mut().check_end_names = true;
    reader.config_mut().check_comments = true;
    let mut buffer = Vec::new();
    let mut depth = 0usize;
    let mut saw_root = false;
    let mut saw_prior_event = false;

    loop {
        let (resolved, event) = match reader.read_resolved_event_into(&mut buffer) {
            Ok(event) => event,
            Err(_) => return Err(Stop::Unsupported),
        };
        if !matches!(&event, Event::Decl(_) | Event::Eof) {
            saw_prior_event = true;
        }
        match event {
            event @ (Event::Start(_) | Event::Empty(_)) => {
                let (element, empty) = match event {
                    Event::Start(element) => (element, false),
                    Event::Empty(element) => (element, true),
                    _ => unreachable!(),
                };
                let element_name = element.name();
                let raw_name = element_name.as_ref();
                if !valid_qname(raw_name) {
                    return Err(Stop::Unsupported);
                }
                let Some(name) = expanded_name(resolved, raw_name.rsplit(':').next().unwrap_or(raw_name)) else {
                    return Err(Stop::Unsupported);
                };
                if depth == 0 {
                    if saw_root {
                        return Err(Stop::Unsupported);
                    }
                    saw_root = true;
                }
                let attrs = Obj::new(unsafe { PyDict_New() })?;
                let mut attributes = element.attributes();
                attributes.with_checks(true);
                for attribute in attributes {
                    let Ok(attribute) = attribute else {
                        return Err(Stop::Unsupported);
                    };
                    if attribute.value.contains('<') {
                        return Err(Stop::Unsupported);
                    }
                    let raw_key = attribute.key.as_ref();
                    if raw_key == "xmlns" || raw_key.starts_with("xmlns:") {
                        if attribute.value.contains('&')
                            || attribute.value.contains('\t')
                            || attribute.value.contains('\r')
                            || attribute.value.contains('\n')
                            || matches!(
                                attribute.value.as_ref(),
                                "http://www.w3.org/XML/1998/namespace"
                                    | "http://www.w3.org/2000/xmlns/"
                            )
                        {
                            return Err(Stop::Unsupported);
                        }
                        continue;
                    }
                    if !valid_qname(raw_key) {
                        return Err(Stop::Unsupported);
                    }
                    let (namespace, local) = reader.resolver().resolve_attribute(attribute.key);
                    let Some(key) = expanded_name(namespace, local.as_ref()) else {
                        return Err(Stop::Unsupported);
                    };
                    let key = sink.name(&key)?;
                    match unsafe { PyDict_Contains(attrs.0, key) } {
                        0 => {}
                        -1 => return Err(Stop::PyError),
                        _ => return Err(Stop::Unsupported),
                    }
                    let Ok(value) = attribute.normalized_value(XmlVersion::Implicit1_0) else {
                        return Err(Stop::Unsupported);
                    };
                    if !valid_xml_characters(&value) {
                        return Err(Stop::Unsupported);
                    }
                    let value = new_str(&value)?;
                    if unsafe { PyDict_SetItem(attrs.0, key, value.0) } != 0 {
                        return Err(Stop::PyError);
                    }
                }
                sink.start(&name, attrs)?;
                if empty {
                    sink.end()?;
                } else {
                    depth += 1;
                }
            }
            Event::End(element) => {
                if depth == 0 {
                    return Err(Stop::Unsupported);
                }
                let element_name = element.name();
                if !valid_qname(element_name.as_ref()) || matches!(resolved, ResolveResult::Unknown(_)) {
                    return Err(Stop::Unsupported);
                }
                sink.end()?;
                depth -= 1;
            }
            Event::Text(text) => {
                let value = text.xml_content(XmlVersion::Implicit1_0);
                if !valid_xml_characters(&value) {
                    return Err(Stop::Unsupported);
                }
                if depth == 0 {
                    if !value.chars().all(|ch| matches!(ch, ' ' | '\t' | '\n' | '\r')) {
                        return Err(Stop::Unsupported);
                    }
                } else {
                    sink.text(&value);
                }
            }
            Event::CData(text) => {
                if depth == 0 {
                    return Err(Stop::Unsupported);
                }
                let value = text.xml_content(XmlVersion::Implicit1_0);
                if !valid_xml_characters(&value) {
                    return Err(Stop::Unsupported);
                }
                sink.text(&value);
            }
            Event::Comment(comment) => {
                let value = comment.xml_content(XmlVersion::Implicit1_0);
                if !valid_xml_characters(&value) {
                    return Err(Stop::Unsupported);
                }
                sink.comment(&value)?;
            }
            Event::PI(instruction) => {
                let target = instruction.target();
                if !valid_qname(target) || target.eq_ignore_ascii_case("xml") {
                    return Err(Stop::Unsupported);
                }
            }
            Event::DocType(_) => return Err(Stop::Unsupported),
            Event::GeneralRef(reference) => {
                if depth == 0 {
                    return Err(Stop::Unsupported);
                }
                match reference.as_ref() {
                    "amp" => sink.text("&"),
                    "lt" => sink.text("<"),
                    "gt" => sink.text(">"),
                    "apos" => sink.text("'"),
                    "quot" => sink.text("\""),
                    _ => match reference.resolve_char_ref() {
                        Ok(Some(ch)) if valid_xml_characters(&ch.to_string()) => {
                            let mut utf8 = [0u8; 4];
                            sink.text(ch.encode_utf8(&mut utf8));
                        }
                        _ => return Err(Stop::Unsupported),
                    },
                }
            }
            Event::Decl(_) => {
                if !declaration_at_start || saw_prior_event {
                    return Err(Stop::Unsupported);
                }
                saw_prior_event = true;
            }
            Event::Eof => break,
        }
        buffer.clear();
    }

    if !saw_root || depth != 0 {
        Err(Stop::Unsupported)
    } else {
        Ok(())
    }
}

fn event_field<'a>(input: &'a [u8], position: &mut usize) -> Option<&'a str> {
    if *position >= input.len() {
        return None;
    }
    let remaining = &input[*position..];
    let end = remaining.iter().position(|byte| *byte == 0)?;
    let value = str::from_utf8(&remaining[..end]).ok()?;
    *position += end + 1;
    Some(value)
}

fn record_start_chunks(
    writer: &Writer<Vec<u8>>,
    start: usize,
    end: usize,
    name: &str,
    attributes: &[(&str, &str)],
    empty: bool,
    chunks: &mut Vec<(usize, usize)>,
) -> Result<(), ()> {
    let output = writer.get_ref();
    let mut position = start;
    let name_end = position + 1 + name.len();
    if name_end > end || &output[position..name_end] != format!("<{name}").as_bytes() {
        return Err(());
    }
    chunks.push((position, name_end));
    position = name_end;

    for (key, value) in attributes {
        let attribute = format!(" {key}=\"{value}\"");
        let attribute_end = position + attribute.len();
        if attribute_end > end || &output[position..attribute_end] != attribute.as_bytes() {
            return Err(());
        }
        chunks.push((position, attribute_end));
        position = attribute_end;
    }

    let ending = if empty { b" />".as_slice() } else { b">".as_slice() };
    let ending_end = position + ending.len();
    if ending_end != end || &output[position..ending_end] != ending {
        return Err(());
    }
    chunks.push((position, ending_end));
    Ok(())
}

fn write_start(
    writer: &mut Writer<Vec<u8>>,
    input: &[u8],
    position: &mut usize,
    empty: bool,
    chunks: &mut Vec<(usize, usize)>,
) -> Result<(), ()> {
    let name = event_field(input, position).ok_or(())?;
    let count = event_field(input, position).ok_or(())?.parse::<usize>().map_err(|_| ())?;
    let mut element = BytesStart::new(name);
    let mut attributes = Vec::with_capacity(count);
    for _ in 0..count {
        let key = event_field(input, position).ok_or(())?;
        let value = event_field(input, position).ok_or(())?;
        attributes.push((key, value));
        element.push_attribute((key, value));
    }
    let start = writer.get_ref().len();
    if empty {
        writer.write_event(Event::Empty(element)).map_err(|_| ())?;
    } else {
        writer.write_event(Event::Start(element)).map_err(|_| ())?;
    }
    let end = writer.get_ref().len();
    record_start_chunks(writer, start, end, name, &attributes, empty, chunks)
}

fn serialize_events(input: &[u8]) -> Result<Vec<u8>, ()> {
    let mut writer = Writer::new(Vec::new());
    writer.config_mut().add_space_before_slash_in_empty_elements = true;
    let mut chunks = Vec::new();
    let mut position = 0;
    while position < input.len() {
        let Some(event) = event_field(input, &mut position) else {
            return Err(());
        };
        match event {
            "S" => write_start(&mut writer, input, &mut position, false, &mut chunks)?,
            "V" => write_start(&mut writer, input, &mut position, true, &mut chunks)?,
            "E" => {
                let name = event_field(input, &mut position).ok_or(())?;
                let start = writer.get_ref().len();
                writer.write_event(Event::End(BytesEnd::new(name))).map_err(|_| ())?;
                chunks.push((start, writer.get_ref().len()));
            }
            "T" => {
                let text = event_field(input, &mut position).ok_or(())?;
                let start = writer.get_ref().len();
                writer.write_event(Event::Text(BytesText::from_escaped(text.to_owned())))
                    .map_err(|_| ())?;
                chunks.push((start, writer.get_ref().len()));
            }
            "C" => {
                let text = event_field(input, &mut position).ok_or(())?;
                let start = writer.get_ref().len();
                writer.write_event(Event::Comment(BytesText::from_escaped(text)))
                    .map_err(|_| ())?;
                chunks.push((start, writer.get_ref().len()));
            }
            "P" => {
                let text = event_field(input, &mut position).ok_or(())?;
                let start = writer.get_ref().len();
                writer.write_event(Event::PI(BytesPI::new(text))).map_err(|_| ())?;
                chunks.push((start, writer.get_ref().len()));
            }
            _ => return Err(()),
        }
    }
    let output = writer.into_inner();
    let mut chunked = Vec::with_capacity(output.len() + chunks.len());
    for (index, (start, end)) in chunks.into_iter().enumerate() {
        if index > 0 {
            chunked.push(0);
        }
        chunked.extend_from_slice(&output[start..end]);
    }
    Ok(chunked)
}

unsafe extern "C" fn parse(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"parse expects (document, target)".as_ptr()) };
        return ptr::null_mut();
    }
    let (data, target) = unsafe { (*args, *args.add(1)) };
    let Ok(mut sink) = Sink::new(target) else {
        return ptr::null_mut();
    };
    let outcome = if unsafe { Py_TYPE(data) } == ptr::addr_of_mut!(PyUnicode_Type) {
        let mut length: Py_ssize_t = 0;
        let bytes = unsafe { PyUnicode_AsUTF8AndSize(data, &mut length) };
        if bytes.is_null() {
            unsafe { PyErr_Clear() };
            Err(Stop::Unsupported)
        } else {
            parse_document(unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) }, &mut sink)
        }
    } else {
        let Some(input) = (unsafe { BorrowedBuffer::from_object(data) }) else {
            return ptr::null_mut();
        };
        parse_document(input.bytes(), &mut sink)
    };
    match outcome {
        Ok(()) => unsafe { PyBool_FromLong(1) },
        Err(Stop::Unsupported) => unsafe { PyBool_FromLong(0) },
        Err(Stop::PyError) => ptr::null_mut(),
    }
}

unsafe extern "C" fn serialize(
    _module: *mut PyObject,
    input: *mut PyObject,
) -> *mut PyObject {
    let Some(input) = (unsafe { BorrowedBuffer::from_object(input) }) else {
        return ptr::null_mut();
    };
    match serialize_events(input.bytes()) {
        Ok(output) => new_bytes(&output),
        Err(()) => invalid_event_stream(),
    }
}

pub extern "C" fn _elementtree_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _elementtree_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_module(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _ELEMENTTREE_RS_MODULE_METHODS: [PyMethodDef; 3] = {
    [
        PyMethodDef {
            ml_name: c"parse".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: parse },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Parse a supported complete XML document.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"serialize".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: serialize },
            ml_flags: METH_O,
            ml_doc: c"Serialize ElementTree XML events.".as_ptr() as *mut c_char,
        },
        PyMethodDef::zeroed(),
    ]
};

pub static _ELEMENTTREE_RS_MODULE: ModuleDef = {
    ModuleDef {
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_elementtree_rs".as_ptr() as *mut _,
            m_doc: c"Rust complete-document XML parser and writer.".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_ELEMENTTREE_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: ptr::null_mut(),
            m_traverse: None,
            m_clear: Some(_elementtree_rs_clear),
            m_free: Some(_elementtree_rs_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__elementtree_rs() -> *mut PyObject {
    _ELEMENTTREE_RS_MODULE.init_module()
}
