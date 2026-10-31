use cpython_binding::ffi_ext as ours;
use cpython_sys as fork;

#[test]
fn unicode_subclass_flag_matches_the_fork() {
    assert_eq!(ours::Py_TPFLAGS_UNICODE_SUBCLASS, u64::from(fork::Py_TPFLAGS_UNICODE_SUBCLASS));
}
