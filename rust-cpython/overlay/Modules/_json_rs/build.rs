use cpython_build_helper::print_linker_args;
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    print_linker_args();
    println!("cargo:rerun-if-env-changed=PYTHON_BUILD_DIR");
    println!("cargo:rerun-if-env-changed=PY_GIL_DISABLED");
    let build = PathBuf::from(env::var("PYTHON_BUILD_DIR").expect("JSON native declarations require the configured CPython build"));
    let config = build.join("pyconfig.h");
    println!("cargo:rerun-if-changed={}", config.display());
    let source = fs::read_to_string(config).expect("read configured CPython header");
    let defines: Vec<Vec<&str>> = source.lines().map(|line| line.split_whitespace().collect()).collect();
    assert!(defines.iter().any(|words| words.as_slice() == ["#define", "SIZEOF_VOID_P", "8"]), "JSON declarations require 64-bit CPython");
    for words in &defines {
        if words.first() == Some(&"#define") && words.get(1) == Some(&"Py_GIL_DISABLED") {
            panic!("JSON declarations require a header without Py_GIL_DISABLED");
        }
    }
    if let Ok(value) = env::var("PY_GIL_DISABLED") {
        assert!(value.is_empty() || value == "0", "JSON declarations require GIL-enabled CPython");
    }
}
