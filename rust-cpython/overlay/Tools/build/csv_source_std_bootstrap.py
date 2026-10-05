"""Expose already-built native modules to the configured build interpreter."""
import os
import sys


def build_library_path(build, environment):
    # Before installation the build interpreter's libpython install name points
    # at its future stage. Nested build interpreters need the same owned build
    # library search path as the normal make launcher, never another prefix.
    owner = os.path.realpath(os.fspath(build))
    if owner != os.path.abspath(os.fspath(build)) or not os.path.isdir(owner):
        raise ValueError('build library owner is not canonical')
    inherited = environment.get('DYLD_LIBRARY_PATH')
    if inherited not in (None, owner):
        raise ValueError('build library owner differs from the configured build')
    return owner


def configure_bootstrap_path():
    # The shared-module copying step runs after this helper is built. Its build
    # interpreter can use the prerequisite extensions directly from Modules;
    # accepting a different interpreter would mix independent runtime owners.
    raw = os.environ['PYTHON_BUILD_DIR']
    build = os.path.abspath(raw)
    if raw != build or os.path.realpath(build) != build or not os.path.isdir(build):
        raise ValueError('bootstrap build owner is not a canonical directory')
    executable = os.path.realpath(sys.executable)
    if os.path.dirname(executable) != build or not os.path.isfile(executable):
        raise ValueError('bootstrap interpreter does not belong to the configured build')
    modules = os.path.join(build, 'Modules')
    if os.path.realpath(modules) != modules or not os.path.isdir(modules):
        raise ValueError('bootstrap native Modules owner is not canonical')
    if modules not in sys.path:
        sys.path.insert(0, modules)
    return modules
