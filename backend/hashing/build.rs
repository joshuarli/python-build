fn main() {
    pyo3_build_config::add_extension_module_link_args();
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-cdylib-link-arg=-install_name");
        println!("cargo:rustc-cdylib-link-arg=@rpath/_hashlib_graviola.abi3.so");
    }
}
