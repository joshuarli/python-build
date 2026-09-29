r"""plistlib.py -- a tool to generate and parse MacOSX .plist files.

The property list (.plist) file format is a simple XML pickle supporting
basic object types, like dictionaries, lists, numbers and strings.
Usually the top level object is a dictionary or a frozen dictionary.

To write out a plist file, use the dump(value, file)
function. 'value' is the top level object, 'file' is
a (writable) file object.

To parse a plist from a file, use the load(file) function,
with a (readable) file object as the only argument. It
returns the top level object (again, usually a dictionary).

To work with plist data in bytes objects, you can use loads()
and dumps().

Values can be strings, integers, floats, booleans, tuples, lists,
dictionaries (but only with string keys), Data, bytes, bytearray, or
datetime.datetime objects.

Generate Plist example:

    import datetime as dt
    import plistlib

    pl = dict(
        aString = "Doodah",
        aList = ["A", "B", 12, 32.1, [1, 2, 3]],
        aFloat = 0.1,
        anInt = 728,
        aDict = dict(
            anotherString = "<hello & hi there!>",
            aThirdString = "M\xe4ssig, Ma\xdf",
            aTrueValue = True,
            aFalseValue = False,
        ),
        someData = b"<binary gunk>",
        someMoreData = b"<lots of binary gunk>" * 10,
        aDate = dt.datetime.now()
    )
    print(plistlib.dumps(pl).decode())

Parse Plist example:

    import plistlib

    plist = b'''<plist version="1.0">
    <dict>
        <key>foo</key>
        <string>bar</string>
    </dict>
    </plist>'''
    pl = plistlib.loads(plist)
    print(pl["foo"])
"""
__all__ = [
    "InvalidFileException", "FMT_XML", "FMT_BINARY", "load", "dump", "loads", "dumps", "UID"
]

import codecs
import datetime
import enum
from io import BytesIO
import os


PlistFormat = enum.Enum('PlistFormat', 'FMT_XML FMT_BINARY', module=__name__)
globals().update(PlistFormat.__members__)

class UID:
    def __init__(self, data):
        if not isinstance(data, int):
            raise TypeError("data must be an int")
        if data >= 1 << 64:
            raise ValueError("UIDs cannot be >= 2**64")
        if data < 0:
            raise ValueError("UIDs must be positive")
        self.data = data

    def __index__(self):
        return self.data

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, repr(self.data))

    def __reduce__(self):
        return self.__class__, (self.data,)

    def __eq__(self, other):
        if not isinstance(other, UID):
            return NotImplemented
        return self.data == other.data

    def __hash__(self):
        return hash(self.data)


#
# XML support
#


# XML 'header'
PLISTHEADER = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
"""

def _date_to_string(d, aware_datetime):
    if aware_datetime:
        d = d.astimezone(datetime.UTC)
    return '%04d-%02d-%02dT%02d:%02d:%02dZ' % (
        d.year, d.month, d.day,
        d.hour, d.minute, d.second
    )


def _is_fmt_xml(header):
    prefixes = (b'<?xml', b'<plist')

    for pfx in prefixes:
        if header.startswith(pfx):
            return True

    # Also check for alternative XML encodings, this is slightly
    # overkill because the Apple tools (and plistlib) will not
    # generate files with these encodings.
    for bom, encoding in (
                (codecs.BOM_UTF8, "utf-8"),
                (codecs.BOM_UTF16_BE, "utf-16-be"),
                (codecs.BOM_UTF16_LE, "utf-16-le"),
                # expat does not support utf-32
                #(codecs.BOM_UTF32_BE, "utf-32-be"),
                #(codecs.BOM_UTF32_LE, "utf-32-le"),
            ):
        if not header.startswith(bom):
            continue

        for start in prefixes:
            prefix = bom + start.decode('ascii').encode(encoding)
            if header[:len(prefix)] == prefix:
                return True

    return False


class InvalidFileException (ValueError):
    def __init__(self, message="Invalid file"):
        ValueError.__init__(self, message)



def _is_fmt_binary(header):
    return header[:8] == b'bplist00'



_FORMAT_CODES = frozendict({FMT_XML: 0, FMT_BINARY: 1})


def _fallback():
    import _plistlib_py
    return _plistlib_py


def __getattr__(name):
    # The pure Python parsers and writers live in _plistlib_py, which loads
    # the first time one of their private names is used.
    if name.startswith("_") and not name.startswith("__"):
        try:
            value = getattr(_fallback(), name)
        except AttributeError:
            pass
        else:
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_rust = None


def _rust_module():
    # Keep import-time bootstrap independent of the optional extension.
    global _rust
    if _rust is None:
        try:
            import _plistlib_rs
        except ImportError:
            _rust = False
        else:
            _rust = _plistlib_rs
    return _rust


def _aware_xml_date(*fields):
    return datetime.datetime(*fields, tzinfo=datetime.UTC)


def _naive_binary_date(seconds):
    return datetime.datetime(2001, 1, 1) + datetime.timedelta(seconds=seconds)


def _aware_binary_date(seconds):
    epoch = datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)
    return epoch + datetime.timedelta(seconds=seconds)


def _date_to_seconds(d, aware_datetime):
    if aware_datetime:
        d = d.astimezone(datetime.UTC)
        return (d - datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)).total_seconds()
    return (d - datetime.datetime(2001, 1, 1)).total_seconds()


def _rust_loads(module, data, fmt, aware_datetime):
    # NotImplemented means the input is outside what the Rust reader handles;
    # the Python parser then reads it and raises the exact exceptions.
    if aware_datetime:
        xml_date, binary_date = _aware_xml_date, _aware_binary_date
    else:
        xml_date, binary_date = datetime.datetime, _naive_binary_date
    return module.loads(data, 0 if fmt is FMT_XML else 1, UID, xml_date, binary_date)


def _rust_load(fp, fmt, aware_datetime):
    module = _rust_module()
    if not module:
        return NotImplemented
    if isinstance(fp, BytesIO):
        if fp.tell() != 0:
            return NotImplemented
        data = fp.getvalue()
    else:
        try:
            if fp.tell() != 0:
                return NotImplemented
            data = fp.read()
        except (AttributeError, OSError, ValueError, TypeError):
            return NotImplemented
        if type(data) is not bytes:
            fp.seek(0)
            return NotImplemented
    result = _rust_loads(module, data, fmt, aware_datetime)
    if result is NotImplemented:
        if not isinstance(fp, BytesIO):
            fp.seek(0)
    elif isinstance(fp, BytesIO):
        fp.seek(0, os.SEEK_END)
    return result


def load(fp, *, fmt=None, dict_type=dict, aware_datetime=False):
    """Read a .plist file. 'fp' should be a readable and binary file object.
    Return the unpacked root object (which usually is a dictionary).
    """
    if fmt is None:
        header = fp.read(32)
        fp.seek(0)
        if _is_fmt_xml(header):
            fmt = FMT_XML
        elif _is_fmt_binary(header):
            fmt = FMT_BINARY
        else:
            raise InvalidFileException()

    else:
        _FORMAT_CODES[fmt]

    if dict_type is dict:
        result = _rust_load(fp, fmt, aware_datetime)
        if result is not NotImplemented:
            return result
    P = _fallback()._FORMATS[fmt]['parser']
    p = P(dict_type=dict_type, aware_datetime=aware_datetime)
    return p.parse(fp)


def loads(value, *, fmt=None, dict_type=dict, aware_datetime=False):
    """Read a .plist file from a bytes object.
    Return the unpacked root object (which usually is a dictionary).
    """
    if isinstance(value, str):
        if fmt == FMT_BINARY:
            raise TypeError("value must be bytes-like object when fmt is "
                            "FMT_BINARY")
        value = value.encode()
    if type(value) is bytes and dict_type is dict:
        module = _rust_module()
        if module:
            if fmt is None:
                header = value[:32]
                if _is_fmt_xml(header):
                    fmt = FMT_XML
                elif _is_fmt_binary(header):
                    fmt = FMT_BINARY
            if fmt is FMT_XML or fmt is FMT_BINARY:
                result = _rust_loads(module, value, fmt, aware_datetime)
                if result is not NotImplemented:
                    return result
    fp = BytesIO(value)
    return load(fp, fmt=fmt, dict_type=dict_type, aware_datetime=aware_datetime)


def _dump_bytes(value, *, fmt, skipkeys, sort_keys, aware_datetime):
    if fmt not in _FORMAT_CODES:
        raise ValueError("Unsupported format: %r"%(fmt,))

    module = _rust_module()
    if module:
        binary = fmt is FMT_BINARY
        result = module.dumps(
            value, 1 if binary else 0, bool(sort_keys), bool(skipkeys),
            bool(aware_datetime), UID, frozendict, datetime.datetime,
            _date_to_seconds if binary else _date_to_string)
        if result is not NotImplemented:
            return result

    fp = BytesIO()
    writer = _fallback()._FORMATS[fmt]["writer"](
        fp, sort_keys=sort_keys, skipkeys=skipkeys,
        aware_datetime=aware_datetime)
    writer.write(value)
    return fp.getvalue()


def dump(value, fp, *, fmt=FMT_XML, sort_keys=True, skipkeys=False,
         aware_datetime=False):
    """Write 'value' to a .plist file. 'fp' should be a writable,
    binary file object.
    """
    fp.write(_dump_bytes(value, fmt=fmt, sort_keys=sort_keys,
                         skipkeys=skipkeys, aware_datetime=aware_datetime))


def dumps(value, *, fmt=FMT_XML, skipkeys=False, sort_keys=True,
          aware_datetime=False):
    """Return a bytes object with the contents for a .plist file.
    """
    return _dump_bytes(value, fmt=fmt, skipkeys=skipkeys,
                       sort_keys=sort_keys, aware_datetime=aware_datetime)

