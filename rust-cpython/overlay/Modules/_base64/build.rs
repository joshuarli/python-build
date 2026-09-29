use cpython_build_helper::print_linker_args;

fn main() {
    print_linker_args();
    // Keep the read-only data in the single __DATA segment: the loader's
    // relocations dirty one 16 KiB page instead of two per extension image.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-cdylib-link-arg=-Wl,-no_data_const");
    }
}
