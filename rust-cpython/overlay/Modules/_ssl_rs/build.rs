use std::path::PathBuf;

use cpython_build_helper::print_linker_args;

fn main() {
    print_linker_args();

    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let lock = manifest.join("../../Cargo.lock");
    let content = std::fs::read_to_string(&lock)
        .unwrap_or_else(|_| panic!("cannot read {}", lock.display()));

    for package in ["rustls", "graviola", "rustls-graviola", "ring"] {
        let version = extract_version(&content, package);
        let variable = format!("{}_VERSION", package.to_uppercase().replace('-', "_"));
        println!("cargo:rustc-env={variable}={version}");
    }
    println!("cargo:rerun-if-changed={}", lock.display());
}

fn extract_version(lock: &str, package_name: &str) -> String {
    let mut name = None;
    for line in lock.lines() {
        let line = line.trim();
        if line == "[[package]]" {
            name = None;
        } else if let Some(value) = line.strip_prefix("name = ") {
            name = Some(value.trim_matches('"'));
        } else if let Some(value) = line.strip_prefix("version = ") {
            if name == Some(package_name) {
                return value.trim_matches('"').to_string();
            }
        }
    }
    panic!("missing locked package version: {package_name}")
}
