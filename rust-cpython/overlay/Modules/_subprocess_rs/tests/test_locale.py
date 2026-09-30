import sys

import subprocess


def check_locale_loading():
    assert 'locale' not in sys.modules
    assert 'locale' in dir(subprocess)
    assert 'locale' not in sys.modules

    import _subprocess_rs
    spawn = _subprocess_rs.posix_spawn
    read = _subprocess_rs.read
    calls = {'spawn': 0, 'read': 0}

    def counted_spawn(*args):
        calls['spawn'] += 1
        return spawn(*args)

    def counted_read(*args):
        calls['read'] += 1
        return read(*args)

    _subprocess_rs.posix_spawn = counted_spawn
    _subprocess_rs.read = counted_read
    try:
        result = subprocess.run(
            ['/bin/cat'], input=b'\xffbinary', capture_output=True, close_fds=False, check=True)
    finally:
        _subprocess_rs.posix_spawn = spawn
        _subprocess_rs.read = read
    assert result.stdout == b'\xffbinary'
    assert calls['spawn'] == 1 and calls['read'] > 0
    assert 'locale' not in sys.modules

    encoding = subprocess._text_encoding()
    if sys.flags.utf8_mode:
        assert encoding == 'utf-8'
        assert 'locale' not in sys.modules
    else:
        assert 'locale' in sys.modules
        assert encoding == sys.modules['locale'].getencoding()

    module = subprocess.locale
    assert module is sys.modules['locale']
    assert subprocess.locale is module
    assert subprocess.__dict__['locale'] is module

    class AssignedLocale:
        @staticmethod
        def getencoding():
            return 'assigned-encoding'

    subprocess.locale = AssignedLocale
    try:
        expected = 'utf-8' if sys.flags.utf8_mode else 'assigned-encoding'
        assert subprocess._text_encoding() == expected
    finally:
        subprocess.locale = module

    try:
        subprocess.nonexistent_subprocess_attribute
    except AttributeError as error:
        assert str(error) == "module 'subprocess' has no attribute 'nonexistent_subprocess_attribute'"
    else:
        raise AssertionError('unknown attribute did not raise AttributeError')


if __name__ == '__main__':
    check_locale_loading()
    print('locale loading and Rust launch/read coverage passed')
