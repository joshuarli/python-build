use cpython_build_helper::print_linker_args;

fn main() {
    print_linker_args();
    // Keep const data in __DATA: the image has too little of it to fill a
    // second 16 KiB segment, and each segment dyld relocates is a dirty page.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-cdylib-link-arg=-Wl,-no_data_const");
    }
}
