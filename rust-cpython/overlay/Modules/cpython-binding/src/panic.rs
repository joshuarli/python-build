use core::panic::PanicInfo;

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    unsafe { abort() }
}
