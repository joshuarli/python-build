#![no_std]

use core::panic::PanicInfo;

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn tar_checksum_scan(buf: *const u8, unsigned: *mut i32, signed: *mut i32) {
    let mut u = 256i32;
    let mut s = 256i32;
    let mut offset = 0;
    while offset < 512 {
        if offset < 148 || offset >= 156 {
            let byte = *buf.add(offset);
            u += i32::from(byte);
            s += i32::from(byte as i8);
        }
        offset += 1;
    }
    *unsigned = u;
    *signed = s;
}
