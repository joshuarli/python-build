#![no_std]

pub mod buffer;
pub mod ffi;
pub mod module;
pub mod outcome;
pub mod reference;
pub mod writer;

#[cfg(feature = "abort-on-panic")]
mod panic;

pub use buffer::Buffer;
pub use module::{Module, fastcall, method_table_end, noargs, single_argument};
pub use outcome::{Exception, Outcome, Stop, into_return, raise};
pub use reference::{Borrowed, Owned};
pub use writer::BytesWriter;
