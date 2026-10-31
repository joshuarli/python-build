use std::cell::RefCell;
use std::ffi::{CStr, c_char, c_void};
use std::mem::MaybeUninit;
use std::slice;

use cpython_binding::{Outcome, Sink};
use cpython_deflate::{
    Deflater, InflateFlush, Inflater, RAW_WINDOW, RunError, Z_BUF_ERROR, Z_DATA_ERROR,
    Z_FINISH, Z_MEM_ERROR, Z_NO_FLUSH, Z_OK, Z_STREAM_END, Z_STREAM_ERROR, ZLIB_WINDOW,
    copy_failure, crc32, setup_failure, zlib_failure,
};

thread_local! {
    static RAISED: RefCell<Option<(usize, String)>> = const { RefCell::new(None) };
}

#[unsafe(no_mangle)]
static mut PyExc_IndexError: *mut c_void = 1 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_MemoryError: *mut c_void = 2 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_OSError: *mut c_void = 3 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_OverflowError: *mut c_void = 4 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_RuntimeError: *mut c_void = 5 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_TypeError: *mut c_void = 6 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_ValueError: *mut c_void = 7 as *mut c_void;
#[unsafe(no_mangle)]
static mut PyExc_ZeroDivisionError: *mut c_void = 8 as *mut c_void;

const MEMORY_ERROR: usize = 2;
const VALUE_ERROR: usize = 7;

#[unsafe(no_mangle)]
extern "C" fn PyErr_SetString(exception: *mut c_void, message: *const c_char) {
    let message = unsafe { CStr::from_ptr(message) }.to_string_lossy().into_owned();
    RAISED.with(|raised| *raised.borrow_mut() = Some((exception as usize, message)));
}

fn raised() -> (usize, String) {
    RAISED.with(|raised| raised.borrow_mut().take()).expect("an exception was set")
}

struct VecSink {
    bytes: Vec<u8>,
    written: usize,
}

impl VecSink {
    fn with_capacity(capacity: usize) -> Self {
        Self {
            bytes: vec![0; capacity],
            written: 0,
        }
    }

    fn contents(&self) -> &[u8] {
        &self.bytes[..self.written]
    }
}

impl Sink for VecSink {
    fn written(&self) -> usize {
        self.written
    }

    fn spare(&mut self) -> &mut [MaybeUninit<u8>] {
        let rest = &mut self.bytes[self.written..];
        unsafe { slice::from_raw_parts_mut(rest.as_mut_ptr().cast(), rest.len()) }
    }

    fn grow(&mut self, additional: usize) -> Outcome<()> {
        self.bytes.resize(self.bytes.len() + additional, 0);
        Ok(())
    }

    unsafe fn advance(&mut self, count: usize) {
        self.written += count;
    }
}

fn sample(length: usize) -> Vec<u8> {
    let mut state = 0x2545_f491_4f6c_dd1du64;
    (0..length)
        .map(|index| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            if index % 5 == 0 { (state >> 56) as u8 } else { b"abcdefgh"[index % 8] }
        })
        .collect()
}

fn compress(input: &[u8], window: i32, initial_capacity: usize) -> Vec<u8> {
    let mut deflater = Deflater::new(6, window, None).unwrap();
    let mut sink = VecSink::with_capacity(initial_capacity);
    let code = deflater.run(input, Z_FINISH, &mut sink).unwrap();
    assert_eq!(code, Z_STREAM_END);
    sink.contents().to_vec()
}

#[test]
fn crc32_matches_the_check_value() {
    assert_eq!(crc32(0, b"123456789"), 0xCBF4_3926);
    assert_eq!(crc32(crc32(0, b"1234"), b"56789"), 0xCBF4_3926);
}

#[test]
fn round_trip_survives_output_growth_from_a_one_byte_sink() {
    let input = sample(300_000);
    for window in [ZLIB_WINDOW, RAW_WINDOW] {
        let packed = compress(&input, window, 1);
        let mut inflater = Inflater::new(window).unwrap();
        let mut sink = VecSink::with_capacity(1);
        let result = inflater
            .run(&packed, InflateFlush::FinishLast, None, &mut sink)
            .unwrap();
        assert_eq!(result.code, Z_STREAM_END);
        assert_eq!(result.consumed, packed.len());
        assert_eq!(sink.contents(), input.as_slice());
    }
}

#[test]
fn output_limit_stops_exactly_and_the_rest_resumes_from_the_consumed_offset() {
    let input = sample(100_000);
    let packed = compress(&input, ZLIB_WINDOW, 64);
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut produced = Vec::new();
    let mut offset = 0;
    let mut calls = 0;
    loop {
        let mut sink = VecSink::with_capacity(700);
        let result = inflater
            .run(&packed[offset..], InflateFlush::Sync, Some(1000), &mut sink)
            .unwrap();
        assert!(sink.written() <= 1000);
        produced.extend_from_slice(sink.contents());
        offset += result.consumed;
        calls += 1;
        if result.code == Z_STREAM_END {
            break;
        }
        assert!(matches!(result.code, Z_OK | Z_BUF_ERROR));
        assert!(calls < 10_000);
    }
    assert!(calls > 50);
    assert_eq!(produced, input);
}

#[test]
fn bytes_after_the_end_of_the_stream_are_left_unconsumed() {
    let packed = compress(b"hello hello hello", ZLIB_WINDOW, 16);
    let mut joined = packed.clone();
    joined.extend_from_slice(b"TRAILER");
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(4);
    let result = inflater
        .run(&joined, InflateFlush::Sync, None, &mut sink)
        .unwrap();
    assert_eq!(result.code, Z_STREAM_END);
    assert_eq!(result.consumed, packed.len());
    assert_eq!(sink.contents(), b"hello hello hello");
}

#[test]
fn corrupt_input_reports_a_zlib_code_without_raising() {
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(8);
    let result = inflater
        .run(b"this is not a zlib stream", InflateFlush::Sync, None, &mut sink)
        .unwrap();
    assert_eq!(result.code, Z_DATA_ERROR);
}

#[test]
fn truncated_input_is_not_a_finished_stream() {
    let packed = compress(&sample(5000), RAW_WINDOW, 16);
    let mut inflater = Inflater::new(RAW_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(16);
    let result = inflater
        .run(&packed[..packed.len() / 2], InflateFlush::FinishLast, None, &mut sink)
        .unwrap();
    assert_ne!(result.code, Z_STREAM_END);
}

#[test]
fn an_ended_stream_is_a_stream_error() {
    let mut deflater = Deflater::new(6, ZLIB_WINDOW, None).unwrap();
    assert_eq!(deflater.end(), Z_OK);
    assert!(!deflater.is_live());
    let mut sink = VecSink::with_capacity(8);
    let error = deflater.run(b"x", Z_FINISH, &mut sink).unwrap_err();
    assert!(matches!(error, RunError::Zlib(Z_STREAM_ERROR)));

    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    inflater.end();
    let result = inflater
        .run(b"x", InflateFlush::Sync, None, &mut sink)
        .unwrap();
    assert_eq!(result.code, Z_STREAM_ERROR);
}

#[test]
fn empty_input_finishes_a_valid_empty_stream() {
    let packed = compress(b"", ZLIB_WINDOW, 1);
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(1);
    let result = inflater
        .run(&packed, InflateFlush::FinishLast, None, &mut sink)
        .unwrap();
    assert_eq!(result.code, Z_STREAM_END);
    assert!(sink.contents().is_empty());
}

#[test]
fn a_duplicated_compressor_continues_independently() {
    let first = sample(40_000);
    let second = sample(40_000).into_iter().rev().collect::<Vec<_>>();
    let mut original = Deflater::new(6, ZLIB_WINDOW, None).unwrap();
    let mut head = VecSink::with_capacity(16);
    original.run(&first, Z_NO_FLUSH, &mut head).unwrap();
    let mut copy = original.duplicate().unwrap();
    let mut from_original = VecSink::with_capacity(16);
    let mut from_copy = VecSink::with_capacity(16);
    original.run(&second, Z_FINISH, &mut from_original).unwrap();
    copy.run(&second, Z_FINISH, &mut from_copy).unwrap();
    assert_eq!(from_original.contents(), from_copy.contents());

    let mut whole = head.contents().to_vec();
    whole.extend_from_slice(from_original.contents());
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(16);
    let result = inflater
        .run(&whole, InflateFlush::FinishLast, None, &mut sink)
        .unwrap();
    assert_eq!(result.code, Z_STREAM_END);
    let mut expected = first;
    expected.extend_from_slice(&second);
    assert_eq!(sink.contents(), expected.as_slice());
}

#[test]
fn append_grows_the_sink_to_fit() {
    let mut sink = VecSink::with_capacity(3);
    sink.append(b"ab").unwrap();
    sink.append(b"cdefghij").unwrap();
    assert_eq!(sink.contents(), b"abcdefghij");
}

#[test]
fn failures_carry_the_codes_and_messages_the_python_wrappers_parse() {
    let mut inflater = Inflater::new(ZLIB_WINDOW).unwrap();
    let mut sink = VecSink::with_capacity(8);
    let result = inflater
        .run(b"not zlib at all", InflateFlush::Sync, None, &mut sink)
        .unwrap();
    zlib_failure(inflater.stream(), result.code, "while decompressing data");
    let (exception, message) = raised();
    assert_eq!(exception, VALUE_ERROR);
    assert!(message.starts_with("Error -3 while decompressing data: "), "{message}");

    zlib_failure(&Default::default(), Z_BUF_ERROR, "while flushing");
    assert_eq!(raised().1, "Error -5 while flushing: incomplete or truncated stream");

    setup_failure(Z_MEM_ERROR, "while compressing data");
    assert_eq!(raised(), (MEMORY_ERROR, "Out of memory".to_owned()));

    copy_failure(&Default::default(), Z_STREAM_ERROR, c"unused", "while copying");
    assert_eq!(raised(), (VALUE_ERROR, "Inconsistent stream state".to_owned()));
    copy_failure(&Default::default(), Z_MEM_ERROR, c"Can't allocate", "while copying");
    assert_eq!(raised(), (MEMORY_ERROR, "Can't allocate".to_owned()));
}
