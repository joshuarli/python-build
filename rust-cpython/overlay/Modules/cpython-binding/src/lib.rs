#![no_std]

#[cfg(feature = "alloc")]
extern crate alloc;

pub mod arguments;
pub mod buffer;
#[cfg(feature = "alloc")]
pub mod capsule;
pub mod ffi;
pub mod ffi_extra;
pub mod module;
pub mod outcome;
pub mod pymem;
pub mod reference;
pub mod sink;
pub mod values;
pub mod writer;

#[cfg(all(feature = "abort-on-panic", panic = "abort"))]
mod panic;

pub use buffer::Buffer;
#[cfg(feature = "alloc")]
pub use capsule::{CapsuleState, capsule_state, new_capsule};
pub use module::{Module, fastcall, method_table_end, noargs, single_argument, varargs};
pub use outcome::{Exception, Outcome, Stop, into_return, raise};
pub use reference::{Borrowed, Owned, fastcall_arguments};
pub use sink::{BytesSink, Sink};
pub use writer::BytesWriter;
