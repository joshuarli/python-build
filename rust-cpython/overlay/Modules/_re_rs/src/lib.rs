use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::UnsafeCell;
use std::collections::{HashMap, VecDeque};
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;
use std::str;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Mutex, MutexGuard, OnceLock};

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyErr_Clear, PyErr_Occurred, PyLong_AsLong,
    PyLong_FromLong, PyLong_FromSsize_t, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject, PyTuple_New, PyTuple_SetItem,
    PyUnicode_AsUTF8AndSize, Py_DecRef, Py_ssize_t,
};
use regex::bytes::{Regex, RegexBuilder};

const CACHE_LIMIT: usize = 512;

// Compiling a pattern parses it here and remembers that it was accepted. The
// search engine is built when a search first needs it: most compiled patterns
// are never searched through the module-level functions, so engines built at
// compile time were retained heap for nothing.
//
// The parse is transient, so it runs in a scratch arena that lives in this
// library's zero-filled data segment. That keeps its many differently sized
// allocations off fresh malloc pages, which would stay dirty for the life of
// the process.
const ARENA_SIZE: usize = 60 * 1024;
const MEMO_SLOTS: usize = 512;

#[repr(C, align(16))]
struct Scratch {
    memo: [AtomicU64; MEMO_SLOTS],
    arena: UnsafeCell<[u8; ARENA_SIZE]>,
}

unsafe impl Sync for Scratch {}

static SCRATCH: Scratch = Scratch {
    memo: [const { AtomicU64::new(0) }; MEMO_SLOTS],
    arena: UnsafeCell::new([0; ARENA_SIZE]),
};

// Thread that owns the arena (0: none), and the bump offset inside it. Only
// the owner allocates from the arena, and only between `ArenaScope::enter` and
// its drop, so nothing allocated there can outlive the scope.
static ARENA_OWNER: AtomicUsize = AtomicUsize::new(0);
static ARENA_TOP: AtomicUsize = AtomicUsize::new(0);

unsafe extern "C" {
    fn pthread_self() -> usize;
}

struct ScratchAllocator;

fn arena_base() -> usize {
    SCRATCH.arena.get() as usize
}

fn in_arena(pointer: *mut u8) -> bool {
    let address = pointer as usize;
    address >= arena_base() && address < arena_base() + ARENA_SIZE
}

fn arena_owned() -> bool {
    let owner = ARENA_OWNER.load(Ordering::Acquire);
    owner != 0 && owner == unsafe { pthread_self() }
}

fn arena_allocate(layout: Layout) -> Option<*mut u8> {
    if layout.align() > 16 {
        return None;
    }
    let start = ARENA_TOP.load(Ordering::Relaxed).next_multiple_of(layout.align());
    let end = start.checked_add(layout.size())?;
    if end > ARENA_SIZE {
        return None;
    }
    ARENA_TOP.store(end, Ordering::Relaxed);
    Some((arena_base() + start) as *mut u8)
}

unsafe impl GlobalAlloc for ScratchAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if arena_owned() {
            if let Some(pointer) = arena_allocate(layout) {
                return pointer;
            }
        }
        unsafe { System.alloc(layout) }
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        if !in_arena(pointer) {
            unsafe { System.dealloc(pointer, layout) };
        }
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        if !in_arena(pointer) {
            return unsafe { System.realloc(pointer, layout, new_size) };
        }
        let Ok(new_layout) = Layout::from_size_align(new_size, layout.align()) else {
            return ptr::null_mut();
        };
        let replacement = unsafe { self.alloc(new_layout) };
        if !replacement.is_null() {
            unsafe {
                ptr::copy_nonoverlapping(pointer, replacement, layout.size().min(new_size));
            }
        }
        replacement
    }
}

#[global_allocator]
static ALLOCATOR: ScratchAllocator = ScratchAllocator;

struct ArenaScope;

impl ArenaScope {
    fn enter() -> Option<Self> {
        let me = unsafe { pthread_self() };
        ARENA_OWNER
            .compare_exchange(0, me, Ordering::AcqRel, Ordering::Acquire)
            .ok()?;
        ARENA_TOP.store(0, Ordering::Relaxed);
        Some(Self)
    }
}

impl Drop for ArenaScope {
    fn drop(&mut self) {
        ARENA_TOP.store(0, Ordering::Relaxed);
        ARENA_OWNER.store(0, Ordering::Release);
    }
}

fn pattern_hash(pattern: &str) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325u64;
    for &byte in pattern.as_bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    hash | 1
}

fn memo_slot(hash: u64) -> &'static AtomicU64 {
    &SCRATCH.memo[(hash >> 32) as usize % MEMO_SLOTS]
}

fn parses(pattern: &str) -> bool {
    let _scope = ArenaScope::enter();
    let accepted = regex_syntax::ParserBuilder::new()
        .unicode(false)
        .utf8(false)
        .build()
        .parse(pattern)
        .is_ok();
    accepted
}

struct RegexCache {
    expressions: HashMap<String, Regex>,
    insertion_order: VecDeque<String>,
}

impl RegexCache {
    fn new() -> Self {
        Self {
            expressions: HashMap::new(),
            insertion_order: VecDeque::new(),
        }
    }
}

static REGEX_CACHE: OnceLock<Mutex<RegexCache>> = OnceLock::new();

fn regex_cache() -> MutexGuard<'static, RegexCache> {
    REGEX_CACHE
        .get_or_init(|| Mutex::new(RegexCache::new()))
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn supported_pattern(pattern: &str) -> bool {
    pattern.is_ascii() && portable_syntax(pattern.as_bytes())
}

fn prepare_expression(pattern: &str) -> bool {
    if !supported_pattern(pattern) {
        return false;
    }
    let hash = pattern_hash(pattern);
    let slot = memo_slot(hash);
    if slot.load(Ordering::Relaxed) == hash {
        return true;
    }
    // Patterns and subjects are ASCII, so byte-mode ASCII classes match exactly
    // what the Unicode classes would, without Unicode tables or their NFAs.
    let accepted = parses(pattern);
    if accepted {
        slot.store(hash, Ordering::Relaxed);
    }
    accepted
}

fn portable_expression(pattern: &str) -> Option<Regex> {
    if !supported_pattern(pattern) {
        return None;
    }

    if let Some(expression) = regex_cache().expressions.get(pattern) {
        return Some(expression.clone());
    }

    let expression = RegexBuilder::new(pattern).unicode(false).build().ok()?;
    let mut cache = regex_cache();
    if let Some(cached) = cache.expressions.get(pattern) {
        return Some(cached.clone());
    }
    if cache.expressions.len() >= CACHE_LIMIT {
        if let Some(oldest) = cache.insertion_order.pop_front() {
            cache.expressions.remove(&oldest);
        }
    }
    cache.insertion_order.push_back(pattern.to_owned());
    cache
        .expressions
        .insert(pattern.to_owned(), expression.clone());
    Some(expression)
}

fn portable_syntax(pattern: &[u8]) -> bool {
    let mut in_class = false;
    let mut class_has_character = false;
    let mut group_depth = 0usize;
    let mut index = 0usize;

    while index < pattern.len() {
        let byte = pattern[index];
        if byte == b'\\' {
            let Some(&escaped) = pattern.get(index + 1) else {
                return false;
            };
            let supported = match escaped {
                b'd' | b'D' | b's' | b'S' | b'w' | b'W' | b'n' | b'r' | b't' | b'f'
                | b'v' => true,
                b'b' if !in_class => true,
                b'A' | b'z' if !in_class => true,
                b'\\' | b'.' | b'^' | b'$' | b'*' | b'+' | b'?' | b'{' | b'}' | b'['
                | b']' | b'(' | b')' | b'|' | b'-' | b'#' | b'&' | b'~' | b' ' => true,
                _ => false,
            };
            if !supported {
                return false;
            }
            if in_class {
                class_has_character = true;
            }
            index += 2;
            continue;
        }

        if in_class {
            match byte {
                b'[' | b'&' | b'~' => return false,
                b']' => {
                    if !class_has_character {
                        return false;
                    }
                    in_class = false;
                }
                b'^' if !class_has_character => {}
                _ => class_has_character = true,
            }
            index += 1;
            continue;
        }

        match byte {
            b'[' => {
                in_class = true;
                class_has_character = false;
            }
            b']' | b'$' => return false,
            b'(' => {
                if pattern.get(index + 1) == Some(&b'?') {
                    if pattern.get(index + 2) != Some(&b':') {
                        return false;
                    }
                    index += 2;
                }
                group_depth += 1;
            }
            b')' => {
                let Some(depth) = group_depth.checked_sub(1) else {
                    return false;
                };
                group_depth = depth;
            }
            b'*' | b'+' | b'?' | b'}' => {
                if pattern.get(index + 1) == Some(&b'+') {
                    return false;
                }
            }
            _ => {}
        }
        index += 1;
    }

    !in_class && group_depth == 0
}

// The result borrows the string's own buffer: callers use it only during the
// call, while the argument is alive.
unsafe fn ascii_unicode<'a>(object: *mut PyObject) -> Option<&'a str> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    if !bytes.is_ascii() {
        return None;
    }
    str::from_utf8(bytes).ok()
}

unsafe fn supported_flags(object: *mut PyObject) -> bool {
    let flags = unsafe { PyLong_AsLong(object) };
    let error = unsafe { PyErr_Occurred() };
    if flags == -1 && !error.is_null() {
        unsafe { PyErr_Clear() };
        return false;
    }
    flags == 0 || flags == 32
}

unsafe fn prepare_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 2 {
        return unsafe { PyBool_FromLong(0) };
    }
    let pattern = unsafe { ascii_unicode(*args) };
    let flags_ok = unsafe { supported_flags(*args.add(1)) };
    let prepared = pattern
        .filter(|_| flags_ok)
        .is_some_and(prepare_expression);
    unsafe { PyBool_FromLong(if prepared { 1 } else { 0 }) }
}

unsafe fn search_result(status: c_int, start: usize, end: usize) -> *mut PyObject {
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let values = [
        unsafe { PyLong_FromLong(status.into()) },
        unsafe { PyLong_FromSsize_t(start as Py_ssize_t) },
        unsafe { PyLong_FromSsize_t(end as Py_ssize_t) },
    ];
    for (index, value) in values.into_iter().enumerate() {
        if value.is_null()
            || unsafe { PyTuple_SetItem(result, index as Py_ssize_t, value) } != 0
        {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

unsafe fn search_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { search_result(0, 0, 0) };
    }
    let pattern = unsafe { ascii_unicode(*args) };
    let subject = unsafe { ascii_unicode(*args.add(1)) };
    let flags_ok = unsafe { supported_flags(*args.add(2)) };
    let Some((pattern, subject)) = pattern.zip(subject).filter(|_| flags_ok) else {
        return unsafe { search_result(0, 0, 0) };
    };
    let Some(expression) = portable_expression(pattern) else {
        return unsafe { search_result(0, 0, 0) };
    };
    match expression.find(subject.as_bytes()) {
        Some(found) => unsafe { search_result(2, found.start(), found.end()) },
        None => unsafe { search_result(1, 0, 0) },
    }
}

unsafe extern "C" fn prepare(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { prepare_impl(args, nargs) }
}

unsafe extern "C" fn search(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { search_impl(args, nargs) }
}

pub extern "C" fn _re_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _re_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _RE_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"prepare".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: prepare,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Prepare a supported regular expression for searching.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"search".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: search,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Search an ASCII string with a supported expression.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _RE_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_re_rs".as_ptr() as *mut _,
        m_doc: c"Rust regular-expression search for a compatible ASCII subset.".as_ptr()
            as *mut _,
        m_size: 0,
        m_methods: &_RE_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_re_rs_clear),
        m_free: Some(_re_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__re_rs() -> *mut PyObject {
    _RE_RS_MODULE.init_multi_phase()
}
