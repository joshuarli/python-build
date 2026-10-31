use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::UnsafeCell;
use std::collections::{HashMap, VecDeque};
use std::ffi::{c_char, c_int};
use std::ptr;
use std::slice;
use std::str;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Mutex, MutexGuard, OnceLock};

use cpython_binding::ffi::{
    PyBool_FromLong, PyErr_Clear, PyErr_NoMemory, PyErr_Occurred, PyErr_SetString, PyLong_AsLong,
    PyLong_FromLong, PyLong_FromSsize_t, PyMethodDef, PyObject, PyObject_Type, PyTuple_New,
    PyTuple_SetItem, PyUnicode_AsUTF8AndSize, PyUnicode_GetLength, Py_DecRef, Py_ssize_t,
};
use cpython_binding::ffi_extra::{
    PyCFunction_GetFunction, PyCFunction_GetSelf, PyCFunction_Type, PyDict_GetItemString,
    PyErr_CheckSignals, PyExc_RuntimeError, PyModule_GetDict, PyUnicode_ReadChar,
};
use cpython_binding::{Module, fastcall, method_table_end};
use regex::bytes::{Regex, RegexBuilder};

mod borrowed_sre;

unsafe extern "C" {
    fn re_rs_borrow_pattern(
        pattern: *mut PyObject,
        code: *mut *const u32,
        length: *mut Py_ssize_t,
        source: *mut *mut PyObject,
        flags: *mut c_int,
    ) -> c_int;
}

const CACHE_LIMIT: usize = 512;

// Legacy string preparation parses here and remembers that it was accepted. The
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

// Code and source remain owned by the live Pattern argument. Neither slice
// leaves the call, and execution keeps the GIL so the owner cannot disappear.
unsafe fn compiled_code<'a>(pattern: *mut PyObject) -> Option<&'a [u32]> {
    let mut code = ptr::null();
    let mut length = 0;
    let mut source = ptr::null_mut();
    let mut flags = 0;
    if unsafe { re_rs_borrow_pattern(pattern, &mut code, &mut length, &mut source, &mut flags) } != 1
        || code.is_null()
        || length <= 0
        || length as usize > isize::MAX as usize / std::mem::size_of::<u32>()
        || (flags != 0 && flags != 32)
    {
        return None;
    }
    let pattern = unsafe { ascii_unicode(source) }?;
    if !supported_pattern(pattern) {
        return None;
    }
    Some(unsafe { slice::from_raw_parts(code, length as usize) })
}

// Reject non-ASCII before requesting UTF-8, so an unsupported subject does
// not acquire an encoded cache merely because Rust inspected eligibility.
unsafe fn compiled_subject<'a>(subject: *mut PyObject) -> Option<&'a str> {
    let length = unsafe { PyUnicode_GetLength(subject) };
    if length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    for index in 0..length {
        if unsafe { PyUnicode_ReadChar(subject, index) } > 127 {
            unsafe { PyErr_Clear() };
            return None;
        }
    }
    unsafe { ascii_unicode(subject) }
}

unsafe extern "C" fn prepare_compiled(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return unsafe { PyBool_FromLong(0) };
    }
    let Some(code) = (unsafe { compiled_code(*args) }) else {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { PyBool_FromLong(0) };
    };
    match borrowed_sre::validate(code) {
        Ok(()) => unsafe { PyBool_FromLong(1) },
        Err(borrowed_sre::Error::Unsupported) => unsafe { PyBool_FromLong(0) },
        Err(error) => unsafe { compiled_error(error) },
    }
}

unsafe fn compiled_error(error: borrowed_sre::Error) -> *mut PyObject {
    match error {
        borrowed_sre::Error::AllocationFailed => unsafe { PyErr_NoMemory() },
        borrowed_sre::Error::Interrupted => ptr::null_mut(),
        borrowed_sre::Error::InvalidProgram => {
            unsafe { PyErr_SetString(PyExc_RuntimeError, c"invalid borrowed SRE program".as_ptr()) };
            ptr::null_mut()
        }
        borrowed_sre::Error::Unsupported => unsafe { search_result(0, 0, 0) },
    }
}

unsafe extern "C" fn search_compiled(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return unsafe { search_result(0, 0, 0) };
    }
    let Some(code) = (unsafe { compiled_code(*args) }) else {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { search_result(0, 0, 0) };
    };
    let Some(subject) = (unsafe { compiled_subject(*args.add(1)) }) else {
        return unsafe { search_result(0, 0, 0) };
    };
    match borrowed_sre::search_with_interrupt(code, subject.as_bytes(), || {
        (unsafe { PyErr_CheckSignals() }) != 0
    }) {
        Ok(Some((start, end))) => unsafe { search_result(2, start, end) },
        Ok(None) => unsafe { search_result(1, 0, 0) },
        Err(borrowed_sre::Error::Unsupported) => unsafe { search_result(0, 0, 0) },
        Err(error) => unsafe { compiled_error(error) },
    }
}

unsafe fn native_hook(module: *mut PyObject, name: *const c_char, function: *const ()) -> bool {
    let dictionary = unsafe { PyModule_GetDict(module) };
    let hook = unsafe { PyDict_GetItemString(dictionary, name) };
    if hook.is_null() {
        return false;
    }
    let kind = unsafe { PyObject_Type(hook) };
    let native = kind == ptr::addr_of_mut!(PyCFunction_Type).cast();
    unsafe { Py_DecRef(kind) };
    if !native {
        return false;
    }
    let actual = unsafe { PyCFunction_GetFunction(hook) };
    let intact = actual.is_some_and(|actual| actual as *const () == function)
        && unsafe { PyCFunction_GetSelf(hook) } == module;
    intact
}

// Compare native implementation and bound-module identities on each call.
// A replacement legacy hook must still observe the original string API.
unsafe extern "C" fn legacy_hooks_intact(
    module: *mut PyObject,
    _args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let intact = nargs == 0
        && unsafe { native_hook(module, c"prepare".as_ptr(), prepare as *const ()) }
        && unsafe { native_hook(module, c"search".as_ptr(), search as *const ()) };
    unsafe { PyBool_FromLong(intact.into()) }
}

static METHODS: [PyMethodDef; 6] = [
    fastcall(c"prepare", prepare, c"Prepare a supported regular expression for searching."),
    fastcall(c"search", search, c"Search an ASCII string with a supported expression."),
    fastcall(
        c"prepare_compiled",
        prepare_compiled,
        c"Check a borrowed compiled ASCII expression.",
    ),
    fastcall(
        c"search_compiled",
        search_compiled,
        c"Search with borrowed canonical SRE code.",
    ),
    fastcall(
        c"_legacy_hooks_intact",
        legacy_hooks_intact,
        c"Check native legacy-hook identities.",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_re_rs",
    c"Rust regular-expression search for a compatible ASCII subset.",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__re_rs() -> *mut PyObject {
    MODULE.init()
}

#[cfg(test)]
mod allocator_contract {
    use super::*;
    use std::sync::PoisonError;
    use std::thread;

    static SERIAL: Mutex<()> = Mutex::new(());

    fn serial() -> MutexGuard<'static, ()> {
        SERIAL.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn layout(size: usize, align: usize) -> Layout {
        Layout::from_size_align(size, align).unwrap()
    }

    fn fill(pointer: *mut u8, length: usize) {
        for index in 0..length {
            unsafe { pointer.add(index).write((index % 251) as u8 + 1) };
        }
    }

    fn prefix_intact(pointer: *mut u8, length: usize) -> bool {
        unsafe { slice::from_raw_parts(pointer, length) }
            .iter()
            .enumerate()
            .all(|(index, &byte)| byte == (index % 251) as u8 + 1)
    }

    #[test]
    fn zeroed_allocation_is_zero_when_the_arena_is_reused() {
        let _serial = serial();
        let size = 512;
        {
            let _scope = ArenaScope::enter().unwrap();
            let pointer = unsafe { ALLOCATOR.alloc(layout(size, 8)) };
            assert!(in_arena(pointer));
            unsafe { ptr::write_bytes(pointer, 0xAA, size) };
        }
        let _scope = ArenaScope::enter().unwrap();
        let pointer = unsafe { ALLOCATOR.alloc_zeroed(layout(size, 8)) };
        assert!(in_arena(pointer));
        assert!(unsafe { slice::from_raw_parts(pointer, size) }.iter().all(|&byte| byte == 0));
    }

    #[test]
    fn zeroed_allocation_is_zero_outside_the_arena() {
        let _serial = serial();
        let size = ARENA_SIZE * 2;
        let pointer = unsafe { ALLOCATOR.alloc_zeroed(layout(size, 8)) };
        assert!(!in_arena(pointer));
        assert!(unsafe { slice::from_raw_parts(pointer, size) }.iter().all(|&byte| byte == 0));
        unsafe { ALLOCATOR.dealloc(pointer, layout(size, 8)) };
    }

    #[test]
    fn realloc_keeps_the_common_prefix_through_growth_shrink_and_exhaustion() {
        let _serial = serial();
        let _scope = ArenaScope::enter().unwrap();
        let pointer = unsafe { ALLOCATOR.alloc(layout(32, 8)) };
        assert!(in_arena(pointer));
        fill(pointer, 32);

        let grown = unsafe { ALLOCATOR.realloc(pointer, layout(32, 8), 128) };
        assert!(in_arena(grown));
        assert!(prefix_intact(grown, 32));
        fill(grown, 128);

        let shrunk = unsafe { ALLOCATOR.realloc(grown, layout(128, 8), 16) };
        assert!(prefix_intact(shrunk, 16));

        let exhausted = unsafe { ALLOCATOR.realloc(shrunk, layout(16, 8), ARENA_SIZE * 2) };
        assert!(!in_arena(exhausted));
        assert!(prefix_intact(exhausted, 16));
        fill(exhausted, ARENA_SIZE * 2);

        let system_shrunk = unsafe { ALLOCATOR.realloc(exhausted, layout(ARENA_SIZE * 2, 8), 64) };
        assert!(!in_arena(system_shrunk));
        assert!(prefix_intact(system_shrunk, 64));
        unsafe { ALLOCATOR.dealloc(system_shrunk, layout(64, 8)) };
    }

    #[test]
    fn realloc_preserves_the_requested_alignment() {
        let _serial = serial();
        let _scope = ArenaScope::enter().unwrap();
        for align in [1, 2, 4, 8, 16] {
            let pointer = unsafe { ALLOCATOR.alloc(layout(3, align)) };
            fill(pointer, 3);
            let grown = unsafe { ALLOCATOR.realloc(pointer, layout(3, align), 200) };
            assert_eq!(grown as usize % align, 0);
            assert!(prefix_intact(grown, 3));
        }
        let over_aligned = unsafe { ALLOCATOR.alloc(layout(8, 64)) };
        fill(over_aligned, 8);
        let grown = unsafe { ALLOCATOR.realloc(over_aligned, layout(8, 64), 4096) };
        assert_eq!(grown as usize % 64, 0);
        assert!(prefix_intact(grown, 8));
        unsafe { ALLOCATOR.dealloc(grown, layout(4096, 64)) };
    }

    #[test]
    fn allocations_are_aligned_after_odd_sized_neighbours() {
        let _serial = serial();
        let _scope = ArenaScope::enter().unwrap();
        for align in [1, 2, 4, 8, 16, 32, 64, 4096] {
            let odd = unsafe { ALLOCATOR.alloc(layout(1, 1)) };
            let pointer = unsafe { ALLOCATOR.alloc(layout(24, align)) };
            assert_ne!(odd, pointer);
            assert_eq!(pointer as usize % align, 0);
            assert_eq!(in_arena(pointer), align <= 16);
            if align > 16 {
                unsafe { ALLOCATOR.dealloc(pointer, layout(24, align)) };
            }
        }
    }

    #[test]
    fn other_threads_never_allocate_from_the_owned_arena() {
        let _serial = serial();
        let _scope = ArenaScope::enter().unwrap();
        let in_arena_elsewhere = thread::spawn(|| {
            let pointer = unsafe { ALLOCATOR.alloc(layout(64, 8)) };
            let result = in_arena(pointer);
            unsafe { ALLOCATOR.dealloc(pointer, layout(64, 8)) };
            result
        })
        .join()
        .unwrap();
        assert!(!in_arena_elsewhere);
        assert!(ArenaScope::enter().is_none());
    }
}
