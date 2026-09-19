"""CPython recipe policy, before executing the expensive build."""
from pathlib import Path
import unittest

from buildsys.cpython import configuration
from buildsys.targets import TARGETS


class CPythonTests(unittest.TestCase):
    def test_release_policy_and_private_dependencies(self):
        args, env = configuration(Path('/private'), TARGETS['x86_64-unknown-linux-musl'])
        self.assertIn('--with-lto=thin', args)
        self.assertIn('--enable-shared', args)
        self.assertIn('--without-ensurepip', args)
        self.assertNotIn('--enable-optimizations', args)
        self.assertIn('--enable-experimental-jit=no', args)
        # Tcl/Tk is out of scope (plan "Current scope decision"); configure
        # has no knob to mark _tkinter "disabled" rather than "missing" when
        # Tcl/Tk isn't built, so exclusion is enforced by never building or
        # pinning Tcl/Tk, not by a module-state override.
        self.assertIn('--with-readline=editline', args)
        self.assertEqual(env['PKG_CONFIG_LIBDIR'], '/private/lib/pkgconfig:/private/share/pkgconfig')
        self.assertIn('/private/lib/libbz2.a', env['BZIP2_LIBS'])
        self.assertNotIn('-flto', env.get('CFLAGS', ''))
        # $ORIGIN rpaths are applied by a post-install ELF edit, not baked
        # into configure-time LDFLAGS (see buildsys/cpython.py for why).
        self.assertNotIn('ORIGIN', env['LDFLAGS'])
        self.assertEqual(env['CPPFLAGS'], '-I/private/include')
        self.assertEqual(env['ZLIB_LIBS'], '/private/lib/libz.a')
        self.assertIn('-I/private/include/uuid', env['LIBUUID_CFLAGS'])
        self.assertIn('-march=x86-64', env['CFLAGS'])

    def test_cpu_baseline_follows_the_requested_target(self):
        _, env = configuration(Path('/private'), TARGETS['aarch64-unknown-linux-musl'])
        self.assertIn('-march=armv8-a', env['CFLAGS'])
        self.assertNotIn('x86-64', env['CFLAGS'])


class MacOSCPythonTests(unittest.TestCase):
    """macOS policy (plan 5.3): same product policy, different platform facts."""

    def setUp(self):
        self.args, self.env = configuration(
            Path('/private'), TARGETS['aarch64-apple-darwin']
        )

    def test_product_policy_is_identical_to_linux(self):
        self.assertIn('--with-lto=thin', self.args)
        self.assertIn('--enable-shared', self.args)
        self.assertIn('--without-ensurepip', self.args)
        self.assertIn('--enable-experimental-jit=no', self.args)
        self.assertIn('--with-tail-call-interp=no', self.args)
        self.assertNotIn('--enable-optimizations', self.args)

    def test_deployment_floor_is_explicit_in_flags(self):
        # Left unset, clang inherits the SDK's version (newer than the
        # declared floor), so this has to be passed and not assumed.
        self.assertIn('-mmacosx-version-min=26.0', self.env['CFLAGS'])
        self.assertIn('-mmacosx-version-min=26.0', self.env['LDFLAGS'])

    def test_header_padding_is_requested_for_install_name_edits(self):
        self.assertIn('-headerpad_max_install_names', self.env['LDFLAGS'])

    def test_elf_only_flags_are_absent(self):
        flags = self.env['CFLAGS'] + self.env['LDFLAGS']
        self.assertNotIn('noexecstack', flags)
        self.assertNotIn('build-id', flags)
        self.assertNotIn('FORTIFY', flags)
        self.assertNotIn('stack-protector', flags)

    def test_musl_thread_stack_policy_does_not_cross_over(self):
        self.assertNotIn('THREAD_STACK_SIZE', ' '.join(self.args))

    def test_db_backend_is_ndbm_not_berkeley_db(self):
        self.assertIn('--with-dbmliborder=ndbm', self.args)
        self.assertNotIn('bdb', ' '.join(self.args))

    def test_platform_libraries_are_not_shadowed_by_private_copies(self):
        # zlib, Expat and libedit come from the SDK on macOS (plan 5.2), so
        # the private prefix must not be offered for them.
        for key in ('ZLIB_CFLAGS', 'ZLIB_LIBS', 'LIBUUID_CFLAGS', 'DBM_CFLAGS'):
            self.assertNotIn(key, self.env)
        self.assertEqual(self.env['LIBEDIT_LIBS'], '-ledit')

    def test_bundled_dependencies_still_point_at_the_private_prefix(self):
        self.assertIn('/private/lib/libbz2.a', self.env['BZIP2_LIBS'])
        self.assertIn('/private/lib/libsqlite3.a', self.env['LIBSQLITE3_LIBS'])
        self.assertIn('/private/lib/libmpdec.a', self.env['LIBMPDEC_LIBS'])
        self.assertIn('/private/lib/libncursesw.a', self.env['CURSES_LIBS'])
