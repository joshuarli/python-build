use cpython_build_helper::print_linker_args;

fn main() {
    print_linker_args();
    println!("cargo:rustc-check-cfg=cfg(socket_c_image)");
    println!("cargo:rerun-if-env-changed=SOCKET_C_IMAGE");
    println!("cargo:rerun-if-env-changed=SOCKET_C_OBJECT");
    if std::env::var("SOCKET_C_IMAGE").as_deref() == Ok("1") {
        assert!(std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos"),
                "C socket co-location requires macOS");
        let object = std::env::var("SOCKET_C_OBJECT")
            .expect("C socket co-location requires its compiled object");
        let path = std::path::Path::new(&object);
        assert!(path.is_absolute() && path.is_file(), "missing absolute C socket object");
        println!("cargo:rerun-if-changed={object}");
        println!("cargo:rustc-cfg=socket_c_image");
        // Link the original C object only into this shared library.
        println!("cargo:rustc-cdylib-link-arg={object}");
    }
}
