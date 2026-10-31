use std::fs;
use std::mem::{align_of, offset_of, size_of};
use std::path::PathBuf;

use cpython_binding::ffi as ours;
use cpython_sys as fork;

fn fork_include(header: &str) -> String {
    let source_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let path = source_root.join("Include").join(header);
    fs::read_to_string(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()))
}

fn define_value(header: &str, name: &str) -> String {
    fork_include(header)
        .lines()
        .filter_map(|line| line.trim_start().strip_prefix('#'))
        .filter_map(|directive| directive.trim_start().strip_prefix("define"))
        .filter_map(|definition| definition.trim_start().strip_prefix(name))
        .find_map(|rest| rest.strip_prefix(' '))
        .unwrap_or_else(|| panic!("{header} does not define {name}"))
        .trim()
        .to_owned()
}

macro_rules! same_layout {
    ($ours:ty, $fork:ty, [$($field:ident),* $(,)?]) => {
        assert_eq!(size_of::<$ours>(), size_of::<$fork>(), stringify!($ours));
        assert_eq!(align_of::<$ours>(), align_of::<$fork>(), stringify!($ours));
        $(assert_eq!(
            offset_of!($ours, $field),
            offset_of!($fork, $field),
            concat!(stringify!($ours), ".", stringify!($field)),
        );)*
    };
}

#[test]
fn object_header_matches_the_fork() {
    same_layout!(ours::PyObject, fork::_object, [ob_type]);
    assert_eq!(offset_of!(ours::PyObject, ob_refcnt), 0);
}

#[test]
fn method_and_module_definitions_match_the_fork() {
    same_layout!(
        ours::PyMethodDef,
        fork::PyMethodDef,
        [ml_name, ml_meth, ml_flags, ml_doc]
    );
    same_layout!(
        ours::PyModuleDef_Base,
        fork::PyModuleDef_Base,
        [ob_base, m_init, m_index, m_copy]
    );
    same_layout!(
        ours::PyModuleDef_Slot,
        fork::PyModuleDef_Slot,
        [slot, value]
    );
    same_layout!(
        ours::PyModuleDef,
        fork::PyModuleDef,
        [m_base, m_name, m_doc, m_size, m_methods, m_slots, m_traverse, m_clear, m_free]
    );
}

#[test]
fn buffer_view_matches_the_fork() {
    same_layout!(
        ours::Py_buffer,
        fork::Py_buffer,
        [buf, obj, len, itemsize, readonly, ndim, format, shape, strides, suboffsets, internal]
    );
}

#[test]
fn method_flags_match_the_fork() {
    assert_eq!(ours::METH_O, fork::METH_O);
    assert_eq!(ours::METH_NOARGS, fork::METH_NOARGS);
    assert_eq!(ours::METH_FASTCALL, fork::METH_FASTCALL);
}

#[test]
fn static_immortal_refcount_matches_the_fork_headers() {
    let initial = fork::_Py_IMMORTAL_INITIAL_REFCNT as isize;
    let flags = (fork::_Py_STATICALLY_ALLOCATED_FLAG | fork::_Py_IMMORTAL_FLAGS) as isize;
    assert_eq!(
        define_value("refcount.h", "_Py_STATIC_IMMORTAL_INITIAL_REFCNT"),
        "(((Py_ssize_t)_Py_IMMORTAL_INITIAL_REFCNT) | (_Py_STATIC_FLAG_BITS << 48))"
    );
    assert_eq!(ours::STATIC_IMMORTAL_REFCNT, initial | (flags << 48));
    type Split = fork::_object__bindgen_ty_1__bindgen_ty_1;
    assert_eq!(offset_of!(Split, ob_refcnt), 0);
    assert_eq!(offset_of!(Split, ob_flags), 6);
    assert!(cfg!(target_endian = "little"));
}

#[test]
fn multiple_interpreters_slot_matches_the_fork_headers() {
    assert_eq!(
        define_value("slots_generated.h", "Py_mod_multiple_interpreters"),
        format!("_Py_SLOT_COMPAT_VALUE(3, {})", ours::Py_mod_multiple_interpreters)
    );
    assert_eq!(
        define_value("moduleobject.h", "Py_MOD_PER_INTERPRETER_GIL_SUPPORTED"),
        "((void *)2)"
    );
    assert_eq!(ours::Py_MOD_PER_INTERPRETER_GIL_SUPPORTED as usize, 2);
}

#[test]
fn simple_buffer_request_matches_the_fork_headers() {
    assert_eq!(define_value("pybuffer.h", "PyBUF_SIMPLE"), "0");
    assert_eq!(ours::PyBUF_SIMPLE as u32, fork::PyBUF_SIMPLE);
}
