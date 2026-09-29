use std::borrow::Cow;
use std::cell::UnsafeCell;
use std::collections::HashMap;
use std::ffi::{CStr, c_char, c_int, c_void};
use std::ptr;
use std::slice;
use std::str;

use cpython_sys::PyBool_FromLong;
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
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyDict_GetItemWithError;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyIter_Next;
use cpython_sys::PyObject_CallNoArgs;
use cpython_sys::PyObject_CallOneArg;
use cpython_sys::PyObject_GetAttr;
use cpython_sys::PyObject_GetIter;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyObject_Size;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyTuple_Type;
use cpython_sys::PyType_GetFlags;
use cpython_sys::PyUnicode_InternFromString;
use cpython_sys::Py_TPFLAGS_UNICODE_SUBCLASS;
use cpython_sys::_Py_NoneStruct;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyBuffer_Release;
use cpython_sys::Py_ssize_t;
use cpython_sys::Py_buffer;
use quick_xml::events::Event;
use quick_xml::name::ResolveResult;
use quick_xml::reader::NsReader;
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

const MAX_SERIALIZE_DEPTH: usize = 400;

fn fallback<T>() -> Parsed<T> {
    unsafe { PyErr_Clear() };
    Err(Stop::Unsupported)
}

fn checked(raw: *mut PyObject) -> Parsed<Obj> {
    if raw.is_null() { fallback() } else { Ok(Obj(raw)) }
}

fn is_none(object: *mut PyObject) -> bool {
    object == ptr::addr_of_mut!(_Py_NoneStruct).cast::<PyObject>()
}

fn as_str<'a>(object: *mut PyObject) -> Parsed<&'a str> {
    let flags = unsafe { PyType_GetFlags(Py_TYPE(object)) };
    if flags & u64::from(Py_TPFLAGS_UNICODE_SUBCLASS) == 0 {
        return Err(Stop::Unsupported);
    }
    let mut length: Py_ssize_t = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if bytes.is_null() {
        return fallback();
    }
    let text = unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    // NUL separates output chunks, so text containing one stays on the Python path.
    if text.contains(&0) {
        return Err(Stop::Unsupported);
    }
    Ok(unsafe { str::from_utf8_unchecked(text) })
}

/// `None` and empty strings are absent; anything else must be a string.
fn optional_text<'a>(object: *mut PyObject) -> Parsed<Option<&'a str>> {
    if is_none(object) {
        return Ok(None);
    }
    let text = as_str(object)?;
    Ok(if text.is_empty() { None } else { Some(text) })
}

fn iterate(object: *mut PyObject) -> Parsed<Obj> {
    checked(unsafe { PyObject_GetIter(object) })
}

fn next_item(iterator: &Obj) -> Parsed<Option<Obj>> {
    let item = unsafe { PyIter_Next(iterator.0) };
    if !item.is_null() {
        return Ok(Some(Obj(item)));
    }
    if unsafe { PyErr_Occurred() }.is_null() {
        Ok(None)
    } else {
        fallback()
    }
}

fn pair(object: *mut PyObject) -> Parsed<(*mut PyObject, *mut PyObject)> {
    if unsafe { Py_TYPE(object) } != ptr::addr_of_mut!(PyTuple_Type) || unsafe { PyTuple_Size(object) } != 2 {
        return Err(Stop::Unsupported);
    }
    Ok(unsafe { (PyTuple_GetItem(object, 0), PyTuple_GetItem(object, 1)) })
}

struct Serializer {
    qnames: *mut PyObject,
    comment: *mut PyObject,
    instruction: *mut PyObject,
    short_empty: bool,
    tag: Obj,
    text: Obj,
    tail: Obj,
    items: Obj,
    /// Output chunks, each terminated by NUL.
    out: Vec<u8>,
}

impl Serializer {
    fn mark(&mut self) {
        self.out.push(0);
    }

    fn raw(&mut self, value: &str) {
        self.out.extend_from_slice(value.as_bytes());
    }

    fn escaped(&mut self, value: &str, attribute: bool) {
        let bytes = value.as_bytes();
        let mut start = 0;
        for (index, byte) in bytes.iter().enumerate() {
            let replacement: &[u8] = match byte {
                b'&' => b"&amp;",
                b'<' => b"&lt;",
                b'>' => b"&gt;",
                b'"' if attribute => b"&quot;",
                b'\r' if attribute => b"&#13;",
                b'\n' if attribute => b"&#10;",
                b'\t' if attribute => b"&#09;",
                _ => continue,
            };
            self.out.extend_from_slice(&bytes[start..index]);
            self.out.extend_from_slice(replacement);
            start = index + 1;
        }
        self.out.extend_from_slice(&bytes[start..]);
    }

    fn qname<'a>(&self, key: *mut PyObject) -> Parsed<Option<&'a str>> {
        let value = unsafe { PyDict_GetItemWithError(self.qnames, key) };
        if value.is_null() {
            return fallback();
        }
        if is_none(value) {
            return Ok(None);
        }
        as_str(value).map(Some)
    }

    fn children(&mut self, element: *mut PyObject, depth: usize) -> Parsed<()> {
        let iterator = iterate(element)?;
        while let Some(child) = next_item(&iterator)? {
            self.element(child.0, &[], depth + 1)?;
        }
        Ok(())
    }

    fn cdata(&mut self, text: Option<&str>) {
        if let Some(text) = text {
            self.escaped(text, false);
            self.mark();
        }
    }

    fn element(&mut self, element: *mut PyObject, namespaces: &[(String, String)], depth: usize) -> Parsed<()> {
        if depth > MAX_SERIALIZE_DEPTH {
            return Err(Stop::Unsupported);
        }
        let tag = checked(unsafe { PyObject_GetAttr(element, self.tag.0) })?;
        let text = checked(unsafe { PyObject_GetAttr(element, self.text.0) })?;
        if tag.0 == self.comment || tag.0 == self.instruction {
            let (open, close) = if tag.0 == self.comment { ("<!--", "-->") } else { ("<?", "?>") };
            let text = as_str(text.0)?;
            self.raw(open);
            self.raw(text);
            self.raw(close);
            self.mark();
        } else {
            let text = optional_text(text.0)?;
            match self.qname(tag.0)? {
                None => {
                    self.cdata(text);
                    self.children(element, depth)?;
                }
                Some(name) => {
                    self.raw("<");
                    self.raw(name);
                    self.mark();
                    for (uri, prefix) in namespaces {
                        if prefix.is_empty() {
                            self.raw(" xmlns=\"");
                        } else {
                            self.raw(" xmlns:");
                            self.raw(prefix);
                            self.raw("=\"");
                        }
                        self.escaped(uri, true);
                        self.raw("\"");
                        self.mark();
                    }
                    let method = checked(unsafe { PyObject_GetAttr(element, self.items.0) })?;
                    let items = checked(unsafe { PyObject_CallNoArgs(method.0) })?;
                    let iterator = iterate(items.0)?;
                    while let Some(item) = next_item(&iterator)? {
                        let (key, value) = pair(item.0)?;
                        let Some(key) = self.qname(key)? else {
                            return Err(Stop::Unsupported);
                        };
                        let value = as_str(value)?;
                        self.raw(" ");
                        self.raw(key);
                        self.raw("=\"");
                        self.escaped(value, true);
                        self.raw("\"");
                        self.mark();
                    }
                    let length = unsafe { PyObject_Size(element) };
                    if length < 0 {
                        return fallback();
                    }
                    if text.is_some() || length > 0 || !self.short_empty {
                        self.raw(">");
                        self.mark();
                        self.cdata(text);
                        self.children(element, depth)?;
                        self.raw("</");
                        self.raw(name);
                        self.raw(">");
                        self.mark();
                    } else {
                        self.raw(" />");
                        self.mark();
                    }
                }
            }
        }
        let tail = checked(unsafe { PyObject_GetAttr(element, self.tail.0) })?;
        let tail = optional_text(tail.0)?;
        self.cdata(tail);
        Ok(())
    }

    fn emit(&self, write: *mut PyObject) -> Parsed<()> {
        for chunk in self.out.split(|byte| *byte == 0).filter(|chunk| !chunk.is_empty()) {
            let text = new_str(str::from_utf8(chunk).map_err(|_| Stop::Unsupported)?)?;
            drop(Obj::new(unsafe { PyObject_CallOneArg(write, text.0) })?);
        }
        Ok(())
    }
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
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 7 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"serialize expects (element, qnames, namespaces, short_empty, write, comment, pi)".as_ptr(),
            )
        };
        return ptr::null_mut();
    }
    let args = unsafe { slice::from_raw_parts(args, 7) };
    let outcome = unsafe { serialize_tree(args) };
    match outcome {
        Ok(()) => unsafe { PyBool_FromLong(1) },
        Err(Stop::Unsupported) => unsafe { PyBool_FromLong(0) },
        Err(Stop::PyError) => ptr::null_mut(),
    }
}

unsafe fn serialize_tree(args: &[*mut PyObject]) -> Parsed<()> {
    let attr = |name: &CStr| checked(unsafe { PyUnicode_InternFromString(name.as_ptr()) });
    let mut namespaces = Vec::new();
    let iterator = iterate(args[2])?;
    while let Some(item) = next_item(&iterator)? {
        let (uri, prefix) = pair(item.0)?;
        namespaces.push((as_str(uri)?.to_owned(), as_str(prefix)?.to_owned()));
    }
    let short_empty = match unsafe { PyObject_IsTrue(args[3]) } {
        -1 => return fallback(),
        value => value != 0,
    };
    let mut serializer = Serializer {
        qnames: args[1],
        comment: args[5],
        instruction: args[6],
        short_empty,
        tag: attr(c"tag")?,
        text: attr(c"text")?,
        tail: attr(c"tail")?,
        items: attr(c"items")?,
        out: Vec::new(),
    };
    serializer.element(args[0], &namespaces, 0)?;
    serializer.emit(args[4])
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
            ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: serialize },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Serialize an ElementTree element tree to write callbacks.".as_ptr() as *mut c_char,
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
