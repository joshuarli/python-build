use cpython_build_helper::print_linker_args;
use std::{env, fs, path::PathBuf, process::Command};

// Configured compiler commands and flags may contain quoted paths. Pass their
// words directly to the compiler, without evaluating shell substitutions.
fn words(text: &str) -> Vec<String> {
    let mut result = Vec::new();
    let mut word = String::new();
    let mut quote = None;
    let mut escaped = false;
    let mut started = false;
    for ch in text.chars() {
        if escaped {
            if quote == Some('"') && !matches!(ch, '$' | '`' | '"' | '\\' | '\n') {
                word.push('\\');
            }
            if ch != '\n' { word.push(ch); }
            escaped = false;
            continue;
        }
        if ch == '\\' && quote != Some('\'') { escaped = true; started = true; continue; }
        if let Some(delimiter) = quote {
            if ch == delimiter { quote = None; } else { word.push(ch); }
        } else if ch == '\'' || ch == '"' {
            quote = Some(ch); started = true;
        } else if ch.is_whitespace() {
            if started { result.push(std::mem::take(&mut word)); started = false; }
        } else { word.push(ch); started = true; }
    }
    assert!(quote.is_none() && !escaped, "unterminated configured compiler argument");
    if started { result.push(word); }
    result
}

fn configured_command(text: &str) -> Command {
    let args = words(text);
    let mut command = Command::new(args.first().expect("empty configured tool command"));
    command.args(&args[1..]);
    command
}

fn main() {
    print_linker_args();
    let manifest = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let source = manifest.parent().unwrap().parent().unwrap();
    let build = PathBuf::from(env::var_os("PYTHON_BUILD_DIR").expect("configured Python build required"));
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    for name in ["PY_CC", "PY_CPPFLAGS", "PY_CFLAGS", "PYTHON_BUILD_DIR"] {
        println!("cargo:rerun-if-env-changed={name}");
    }
    for path in [manifest.join("pattern_view.c"), build.join("pyconfig.h"), build.join("Makefile"), source.join("Modules/_sre/sre.h"), source.join("Modules/_sre/sre_constants.h")] {
        println!("cargo:rerun-if-changed={}", path.display());
    }
    let object = out.join("pattern_view.o");
    let archive = out.join("libre_pattern_view.a");
    let mut compiler = configured_command(&env::var("PY_CC").expect("configured C compiler required"));
    for name in ["PY_CPPFLAGS", "PY_CFLAGS"] {
        compiler.args(words(&env::var(name).expect("configured compiler flags required")));
    }
    // The configured flags supply target, deployment and optimization policy.
    // This object is linked into a shared helper and exports no private C ABI.
    compiler.args(["-fPIC", "-fvisibility=hidden"]);
    for include in [build.clone(), source.join("Include"), source.join("Modules/_sre")] {
        compiler.arg("-I").arg(include);
    }
    assert!(compiler.arg("-c").arg(manifest.join("pattern_view.c")).arg("-o").arg(&object).status().expect("C compiler failed to start").success(), "pattern accessor compilation failed");
    let makefile = fs::read_to_string(build.join("Makefile")).expect("configured Makefile required");
    let ar = makefile.lines().find_map(|line| line.strip_prefix("AR=")).expect("configured archiver required");
    assert!(configured_command(ar).arg("crs").arg(&archive).arg(&object).status().expect("archiver failed to start").success(), "pattern accessor archive failed");
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=re_pattern_view");
}
