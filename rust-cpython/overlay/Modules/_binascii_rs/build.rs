use cpython_build_helper::print_linker_args;

fn main() {
    // These declarations cover the GIL-enabled object header, not the
    // different free-threaded or reference-tracing object layouts.
    let directory = std::env::var("PYTHON_BUILD_DIR")
        .expect("PYTHON_BUILD_DIR is required for the CPython ABI");
    let config = std::fs::read_to_string(std::path::Path::new(&directory).join("pyconfig.h"))
        .expect("cannot read the configured CPython ABI");
    for name in ["Py_GIL_DISABLED", "Py_TRACE_REFS"] {
        let enabled = config.lines().any(|line| {
            let mut fields = line.split_whitespace();
            fields.next() == Some("#define") && fields.next() == Some(name)
        });
        assert!(!enabled, "unsupported CPython object header: {name}");
    }
    print_linker_args();
    // Keep the read-only data in the single __DATA segment: the loader's
    // relocations dirty one 16 KiB page instead of two per extension image.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-cdylib-link-arg=-Wl,-no_data_const");
    }
}
