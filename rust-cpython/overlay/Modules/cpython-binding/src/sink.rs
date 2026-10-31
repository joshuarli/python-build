use core::mem::MaybeUninit;

use crate::outcome::Outcome;
use crate::reference::Owned;
use crate::writer::BytesWriter;

/// Where an engine writes its output: spare room that grows on demand.
pub trait Sink {
    /// Bytes written so far.
    fn written(&self) -> usize;

    /// The room after the written bytes. It is empty exactly when the sink
    /// has to grow before it can take more.
    fn spare(&mut self) -> &mut [MaybeUninit<u8>];

    /// Extend the room by `additional` bytes. Failure leaves a Python
    /// exception set.
    fn grow(&mut self, additional: usize) -> Outcome<()>;

    /// # Safety
    /// The first `count` bytes of [`Sink::spare`] are initialized and
    /// `count <= spare().len()`.
    unsafe fn advance(&mut self, count: usize);

    fn append(&mut self, bytes: &[u8]) -> Outcome<()> {
        let missing = bytes.len().saturating_sub(self.spare().len());
        if missing > 0 {
            self.grow(missing)?;
        }
        let room = &mut self.spare()[..bytes.len()];
        for (slot, byte) in room.iter_mut().zip(bytes) {
            slot.write(*byte);
        }
        unsafe { self.advance(bytes.len()) };
        Ok(())
    }
}

/// A `bytes` object that engines fill in place, trimmed to the written size
/// when finished, so the result is never copied.
pub struct BytesSink {
    writer: BytesWriter,
    written: usize,
}

impl BytesSink {
    pub fn with_capacity(capacity: usize) -> Outcome<Self> {
        Ok(Self {
            writer: BytesWriter::create(capacity.max(1))?,
            written: 0,
        })
    }

    pub fn finish(self) -> Outcome<Owned> {
        unsafe { self.writer.finish(self.written) }
    }
}

impl Sink for BytesSink {
    fn written(&self) -> usize {
        self.written
    }

    fn spare(&mut self) -> &mut [MaybeUninit<u8>] {
        let written = self.written;
        &mut self.writer.uninit()[written..]
    }

    fn grow(&mut self, additional: usize) -> Outcome<()> {
        self.writer.grow_exact(additional)
    }

    unsafe fn advance(&mut self, count: usize) {
        self.written += count;
    }
}
