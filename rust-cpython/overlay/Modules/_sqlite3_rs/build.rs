use cpython_build_helper::print_linker_args;
use std::env;
use std::fs;
use std::path::Path;

fn main() {
    print_linker_args();

    // SQLite statement handles must be used with the same library instance
    // that created them in CPython's _sqlite3 extension.
    let build_dir = env::var_os("PYTHON_BUILD_DIR").expect("PYTHON_BUILD_DIR is required");
    let makefile = Path::new(&build_dir).join("Makefile");
    println!("cargo:rerun-if-changed={}", makefile.display());
    let contents = fs::read_to_string(&makefile).expect("read CPython Makefile");
    let flags = contents
        .lines()
        .find_map(|line| line.strip_prefix("MODULE__SQLITE3_LDFLAGS="))
        .expect("CPython SQLite link flags are required");
    let mut words = flags.split_whitespace();
    let mut has_sqlite = false;
    while let Some(word) = words.next() {
        if word == "-lsqlite3" {
            has_sqlite = true;
        } else if word == "-L" {
            let directory = words.next().expect("SQLite -L needs a directory");
            println!("cargo:rustc-link-search=native={directory}");
        } else if let Some(directory) = word.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={directory}");
        }
    }
    assert!(has_sqlite, "CPython SQLite link flags must select sqlite3");
}
