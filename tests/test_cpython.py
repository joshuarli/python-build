"""CPython recipe policy, before executing the expensive build."""
from pathlib import Path
import unittest

from buildsys.cpython import configuration


class CPythonTests(unittest.TestCase):
    def test_release_policy_and_private_dependencies(self):
        args, env = configuration(Path('/private'))
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
