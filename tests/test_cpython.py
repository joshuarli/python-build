"""CPython recipe policy, before executing the expensive build."""
from pathlib import Path
import unittest
from unittest.mock import patch

from buildsys.cpython import (
    CPYTHON_PGO_HASH_SEED, configuration, pgo_profile_task,
    resolve_build_jobs, resolve_pgo_jobs,
)
from buildsys.targets import TARGETS


class CPythonTests(unittest.TestCase):
    def test_filc_uses_its_safe_allocator_without_changing_ordinary_musl(self):
        prefix = Path('/private')
        filc_args, filc_env = configuration(prefix, TARGETS['x86_64-filc-linux-musl'])
        ordinary_args, _ = configuration(prefix, TARGETS['x86_64-unknown-linux-musl'])
        self.assertIn('--without-mimalloc', filc_args)
        self.assertIn('--without-pymalloc', filc_args)
        self.assertNotIn('--without-freelists', filc_args)
        self.assertNotIn('--without-mimalloc', ordinary_args)
        self.assertNotIn('--without-pymalloc', ordinary_args)
        self.assertNotIn('--with-lto=thin', filc_args)
        self.assertIn('--without-remote-debug', filc_args)
        self.assertNotIn('--without-remote-debug', ordinary_args)
        self.assertEqual(filc_env['ac_cv_func_fexecve'], 'no')
        for unsupported in ('prlimit', 'sethostname', 'clock_settime',
                            'pthread_kill', 'pthread_getcpuclockid',
                            'sched_rr_get_interval',
                            'unshare', 'setns'):
            self.assertEqual(filc_env[f'ac_cv_func_{unsupported}'], 'no')
        self.assertEqual(filc_env['ac_cv_lib_rt_clock_settime'], 'no')
        self.assertNotIn('--enable-optimizations', filc_args)
        self.assertIn('--with-dbmliborder=', filc_args)
        self.assertNotIn('DBM_LIBS', filc_env)
        self.assertEqual(filc_env['PKG_CONFIG_LIBDIR'],
                         '/private/lib/pkgconfig:/private/share/pkgconfig')
        for probe in ('x64', 'x87', 'mc68881'):
            self.assertEqual(filc_env[f'ac_cv_gcc_asm_for_{probe}'], 'no')

    def test_release_policy_and_private_dependencies(self):
        args, env = configuration(Path('/private'), TARGETS['x86_64-unknown-linux-musl'])
        self.assertIn('--with-lto=thin', args)
        self.assertIn('--enable-shared', args)
        self.assertIn('--enable-loadable-sqlite-extensions', args)
        self.assertIn('--without-ensurepip', args)
        self.assertNotIn('--enable-optimizations', args)
        self.assertNotIn('PROFILE_TASK', env)
        self.assertIn('--enable-experimental-jit=no', args)
        # Tcl/Tk is out of scope (plan "Current scope decision"); configure
        # has no knob to mark _tkinter "disabled" rather than "missing" when
        # Tcl/Tk isn't built, so exclusion is enforced by never building or
        # pinning Tcl/Tk, not by a module-state override.
        self.assertIn('--with-readline=editline', args)
        self.assertEqual(env['PKG_CONFIG_LIBDIR'], '/private/lib/pkgconfig:/private/share/pkgconfig')
        self.assertIn('/private/lib/libbz2.a', env['BZIP2_LIBS'])
        self.assertIn('/private/lib/libzstd.a', env['LIBZSTD_LIBS'])
        self.assertIn('-pthread', env['LIBZSTD_LIBS'])
        self.assertNotIn('-flto', env.get('CFLAGS', ''))
        # $ORIGIN rpaths are applied by a post-install ELF edit, not baked
        # into configure-time LDFLAGS (see buildsys/cpython.py for why).
        self.assertNotIn('ORIGIN', env['LDFLAGS'])
        self.assertEqual(env['CPPFLAGS'], '-I/private/include')
        self.assertEqual(env['ZLIB_LIBS'], '/private/lib/libz.a')
        self.assertIn('-I/private/include/uuid', env['LIBUUID_CFLAGS'])
        self.assertIn('-march=x86-64', env['CFLAGS'])

    def test_pgo_profile_task_matches_pbs_and_requires_a_worker(self):
        self.assertEqual(pgo_profile_task(8), '-m test --pgo -j 8')
        with self.assertRaises(ValueError):
            pgo_profile_task(0)

    def test_pgo_default_matches_compile_parallelism(self):
        with patch('buildsys.cpython.os.cpu_count', return_value=10):
            self.assertEqual(resolve_build_jobs(), 9)
            self.assertEqual(resolve_pgo_jobs(), 9)

    def test_cpu_baseline_follows_the_requested_target(self):
        _, env = configuration(Path('/private'), TARGETS['aarch64-unknown-linux-musl'])
        self.assertIn('-march=armv8-a', env['CFLAGS'])
        self.assertNotIn('x86-64', env['CFLAGS'])

    def test_curses_panel_link_line_has_no_bare_directory(self):
        # A bare directory on a link line is fed to the linker as an input
        # file. CPython appends CURSES_LIBS+PANEL_LIBS to LIBS for its
        # initscr probe, so one stray token disables _curses *and*
        # _curses_panel with no build error (seen in CI: post-strip smoke
        # import failed with "No module named '_curses'").
        _, env = configuration(Path('/private'), TARGETS['x86_64-unknown-linux-musl'])
        self.assertEqual(
            env['PANEL_LIBS'],
            '-L/private/lib /private/lib/libpanelw.a /private/lib/libncursesw.a',
        )
        for key, value in env.items():
            if not key.endswith('_LIBS'):
                continue
            for token in value.split():
                self.assertTrue(
                    token.startswith('-') or '.' in Path(token).name,
                    f"{key}: bare directory token {token!r}",
                )


class MacOSCPythonTests(unittest.TestCase):
    """macOS policy (plan 5.3): same product policy, different platform facts."""

    def setUp(self):
        self.args, self.env = configuration(
            Path('/private'), TARGETS['aarch64-apple-darwin'], pgo_jobs=4
        )

    def test_product_policy_enables_exact_macos_pgo(self):
        self.assertIn('--with-lto=thin', self.args)
        self.assertIn('--enable-shared', self.args)
        self.assertIn('--enable-loadable-sqlite-extensions', self.args)
        self.assertIn('--without-ensurepip', self.args)
        self.assertIn('--enable-experimental-jit=no', self.args)
        self.assertIn('--with-tail-call-interp=no', self.args)
        self.assertIn('--enable-optimizations', self.args)
        self.assertEqual(self.env['PROFILE_TASK'], '-m test --pgo -j 4')
        self.assertEqual(self.env['PYTHONHASHSEED'], CPYTHON_PGO_HASH_SEED)
        self.assertNotIn('-fno-omit-frame-pointer', self.env['CFLAGS'])

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
        self.assertIn('/private/lib/libzstd.a', self.env['LIBZSTD_LIBS'])
        self.assertNotIn('-pthread', self.env['LIBZSTD_LIBS'])
        self.assertIn('/private/lib/libsqlite3.a', self.env['LIBSQLITE3_LIBS'])
        self.assertIn('/private/lib/libmpdec.a', self.env['LIBMPDEC_LIBS'])

    def test_curses_is_not_pointed_at_the_private_prefix(self):
        # ncurses/panel come from the platform on macOS, matching the
        # reference's /usr/lib/libncurses.5.4.dylib load command. Leaving
        # these set makes configure link whatever static library is sitting
        # in the prefix, which is how a stale libncursesw.a got in unnoticed.
        self.assertNotIn('CURSES_LIBS', self.env)
        self.assertNotIn('PANEL_LIBS', self.env)
        self.assertNotIn('CURSES_CFLAGS', self.env)

    def test_private_prefix_leads_the_search_path_for_static_linking(self):
        # Expat is linked from source (the reference carries no libexpat load
        # command), and configure finds it because the prefix comes first.
        self.assertTrue(self.env['CPPFLAGS'].startswith('-I/private/include'))
        self.assertTrue(self.env['LDFLAGS'].startswith('-L/private/lib'))
