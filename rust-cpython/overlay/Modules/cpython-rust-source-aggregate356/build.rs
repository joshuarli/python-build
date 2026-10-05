use cpython_build_helper::print_linker_args;

fn main() {
    print_linker_args();
    println!("cargo:rustc-link-arg-cdylib=-Wl,-dead_strip_dylibs");
}
