""" Python 'utf-8' Codec


Written by Marc-Andre Lemburg (mal@lemburg.com).

(c) Copyright CNRI, All Rights Reserved. NO WARRANTY.

"""
import codecs

### Codec APIs

encode = codecs.utf_8_encode
_buffer_decode = codecs.utf_8_decode

# Import eagerly: the path importer is ready before the startup encodings are
# imported, and a lazy import would add extension-loading system calls to the
# first user file read or write.
try:
    import _codecs_rs as _rust
except ImportError:
    _rust = None

def _rust_codecs():
    return _rust

def _rust_encode(input, errors):
    if (codecs.utf_8_encode is encode and type(input) is str and
            type(errors) is str and errors == 'strict'):
        rust = _rust_codecs()
        if rust is not None:
            output = rust.encode_utf8(input)
            if output is not None:
                return output
    return codecs.utf_8_encode(input, errors)[0]

def _rust_buffer_decode(input, errors, final):
    if type(input) is bytes and type(errors) is str and errors == 'strict':
        rust = _rust_codecs()
        if rust is not None:
            output = rust.decode_utf8(input, final)
            if output is not None:
                return output
    return _buffer_decode(input, errors, final)

def decode(input, errors='strict'):
    return codecs.utf_8_decode(input, errors, True)

class IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input, final=False):
        return _rust_encode(input, self.errors)

class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
    _buffer_decode = staticmethod(_rust_buffer_decode)

class StreamWriter(codecs.StreamWriter):
    encode = codecs.utf_8_encode

class StreamReader(codecs.StreamReader):
    decode = codecs.utf_8_decode

### encodings module API

def getregentry():
    return codecs.CodecInfo(
        name='utf-8',
        encode=encode,
        decode=decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder,
        streamreader=StreamReader,
        streamwriter=StreamWriter,
        _expat_decoding_table=(*range(128),
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2,
            -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2, -2,
            -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3,
            -4, -4, -4, -4, -4, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1),
    )
