"""Observe HTML scanner boundaries, Python ownership, errors and public routing."""

import gc
import html.parser as parser_module
import weakref
import _html_parser_rs as native


def scan(text, start=0, end=True, convert=True):
    return native.next_token(text, start, end, convert, None, False, False)


for text, expected in (("", ("eof", 0)), ("€😀", ("data", 2)),
                       ("<p>", ("starttag", 3)), ("</p>", ("endtag", 4)),
                       ("<!--x-->", ("comment", 8)), ("<?p>", ("pi", 4)),
                       ("<!DOCTYPE html>", ("declaration", 15))):
    assert scan(text) == expected, (text, expected)
assert scan("<div", end=False) == ("incomplete", 0)
assert scan("&#65;", convert=False) == ("charref", 5)
assert scan("&amp;", convert=False) == ("entityref", 5)
assert scan("abc", start=3) == ("eof", 3)

class Text(str):
    pass
text = Text("€😀")
owner = weakref.ref(text)
result = scan(text)
del text
gc.collect()
assert owner() is None
assert result == ("data", 2)

failure = RuntimeError("truth conversion")
class FailsTruth:
    def __bool__(self):
        raise failure
try:
    scan("text", end=FailsTruth())
except RuntimeError as error:
    assert error is failure
else:
    raise AssertionError("truth callback exception lost")
for arguments, exception, message in (
        ((), ValueError, "next_token() expects seven arguments"),
        (("x", -1, True, True, None, False, False), ValueError, "token offset must be nonnegative"),
        (("x", 2, True, True, None, False, False), ValueError, "token offset exceeds input length")):
    try:
        native.next_token(*arguments)
    except exception as error:
        assert str(error) == message
    else:
        raise AssertionError((arguments, "error lost"))
try:
    scan("x", start=1 << 100)
except OverflowError:
    pass
else:
    raise AssertionError("oversized Python index accepted")

class Recorder(parser_module.HTMLParser):
    def __init__(self, convert):
        super().__init__(convert_charrefs=convert)
        self.events = []
    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, attrs))
    def handle_startendtag(self, tag, attrs):
        self.events.append(("empty", tag, attrs))
    def handle_endtag(self, tag):
        self.events.append(("end", tag))
    def handle_data(self, data):
        self.events.append(("data", data))
    def handle_comment(self, text):
        self.events.append(("comment", text))
    def handle_decl(self, text):
        self.events.append(("decl", text))
    def handle_pi(self, text):
        self.events.append(("pi", text))
    def handle_entityref(self, text):
        self.events.append(("entity", text))
    def handle_charref(self, text):
        self.events.append(("char", text))


original_helper = parser_module._html_parser_rs
original_scan = native.next_token
calls = []
def trace(*args):
    calls.append(args[1])
    return original_scan(*args)
native.next_token = trace
try:
    assert original_helper is native
    fragments = (("<p class='", "one'>€ &amp; 😀", "</p>"),
                 ("x<!-- c --><?pi?><!DOCTYPE html><br/>",),
                 ("<script>if (a < b) &amp;</script><title>&amp;</title>",),
                 ("α &a", "mp; β"))
    for convert in (True, False):
        for pieces in fragments:
            routed = Recorder(convert)
            for piece in pieces:
                routed.feed(piece)
            routed.close()
            parser_module._html_parser_rs = None
            try:
                reference = Recorder(convert)
                for piece in pieces:
                    reference.feed(piece)
                reference.close()
            finally:
                parser_module._html_parser_rs = original_helper
            assert routed.events == reference.events, (convert, pieces, routed.events, reference.events)
    assert calls
finally:
    native.next_token = original_scan
    parser_module._html_parser_rs = original_helper

print("HTML core scanner boundaries, Unicode ownership, callback errors and public Rust event parity passed")
