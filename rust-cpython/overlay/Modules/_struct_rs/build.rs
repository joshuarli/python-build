use cpython_build_helper::print_linker_args;

fn main() {
    // The private object header declarations exclude free-threaded and
    // reference-tracing layouts, which must fail before Rust compilation.
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
}
