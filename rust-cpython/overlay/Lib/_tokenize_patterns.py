"""Construct independent compatibility grammar for one tokenizer module."""


def _group(*choices):
    return '(' + '|'.join(choices) + ')'


def _any(*choices):
    return _group(*choices) + '*'


def _maybe(*choices):
    return _group(*choices) + '?'


def _string_prefixes():
    prefixes = {''}
    for prefix in ('b', 'r', 'u', 'f', 't', 'br', 'fr', 'tr'):
        permutations = (prefix,) if len(prefix) == 1 else (prefix, prefix[::-1])
        for permutation in permutations:
            variants = ['']
            for character in permutation:
                variants = [variant + case for variant in variants
                            for case in (character, character.upper())]
            prefixes.update(variants)
    return prefixes


def _escape_operator(operator):
    # Python operators contain only ASCII punctuation. Escape exactly the
    # punctuation that has regex syntax or participates in extended regex mode.
    return ''.join('\\' + character if character in '()[]{}?*+-|^$\\.&~# \t\n\r\v\f'
                   else character for character in operator)


def _build_patterns(operators):
    # Note: we use unicode matching for names ("\w") but ascii matching for
    # number literals.
    Whitespace = r'[ \f\t]*'
    Comment = r'#[^\r\n]*'
    Ignore = Whitespace + _any(r'\\\r?\n' + Whitespace) + _maybe(Comment)
    Name = r'\w+'

    Hexnumber = r'0[xX](?:_?[0-9a-fA-F])+'
    Binnumber = r'0[bB](?:_?[01])+'
    Octnumber = r'0[oO](?:_?[0-7])+'
    Decnumber = r'(?:0(?:_?0)*|[1-9](?:_?[0-9])*)'
    Intnumber = _group(Hexnumber, Binnumber, Octnumber, Decnumber)
    Exponent = r'[eE][-+]?[0-9](?:_?[0-9])*'
    Pointfloat = _group(r'[0-9](?:_?[0-9])*\.(?:[0-9](?:_?[0-9])*)?',
                       r'\.[0-9](?:_?[0-9])*') + _maybe(Exponent)
    Expfloat = r'[0-9](?:_?[0-9])*' + Exponent
    Floatnumber = _group(Pointfloat, Expfloat)
    Imagnumber = _group(r'[0-9](?:_?[0-9])*[jJ]', Floatnumber + r'[jJ]')
    Number = _group(Imagnumber, Floatnumber, Intnumber)

    # Note that since _string_prefixes includes the empty string,
    #  StringPrefix can be the empty string (making it optional).
    StringPrefix = _group(*_string_prefixes())

    # Tail end of ' string.
    Single = r"[^'\\]*(?:\\.[^'\\]*)*'"
    # Tail end of " string.
    Double = r'[^"\\]*(?:\\.[^"\\]*)*"'
    # Tail end of ''' string.
    Single3 = r"[^'\\]*(?:(?:\\.|'(?!''))[^'\\]*)*'''"
    # Tail end of """ string.
    Double3 = r'[^"\\]*(?:(?:\\.|"(?!""))[^"\\]*)*"""'
    Triple = _group(StringPrefix + "'''", StringPrefix + '"""')
    # Single-line ' or " string.
    String = _group(StringPrefix + r"'[^\n'\\]*(?:\\.[^\n'\\]*)*'",
                   StringPrefix + r'"[^\n"\\]*(?:\\.[^\n"\\]*)*"')

    # Sorting in reverse order puts the long operators before their prefixes.
    # Otherwise if = came before ==, == would get recognized as two instances
    # of =.
    Special = _group(*map(_escape_operator, operators))
    Funny = _group(r'\r?\n', Special)

    PlainToken = _group(Number, Funny, String, Name)
    Token = Ignore + PlainToken

    # First (or only) line of ' or " string.
    ContStr = _group(StringPrefix + r"'[^\n'\\]*(?:\\.[^\n'\\]*)*" +
                    _group("'", r'\\\r?\n'),
                    StringPrefix + r'"[^\n"\\]*(?:\\.[^\n"\\]*)*' +
                    _group('"', r'\\\r?\n'))
    PseudoExtras = _group(r'\\\r?\n|\z', Comment, Triple)
    PseudoToken = Whitespace + _group(PseudoExtras, Number, Funny, ContStr, Name)

    # For a given string prefix plus quotes, endpats maps it to a regex
    #  to match the remainder of that string. _prefix can be empty, for
    #  a normal single or triple quoted string (with no prefix).
    endpats = {}
    for _prefix in _string_prefixes():
        endpats[_prefix + "'"] = Single
        endpats[_prefix + '"'] = Double
        endpats[_prefix + "'''"] = Single3
        endpats[_prefix + '"""'] = Double3
    del _prefix

    # A set of all of the single and triple quoted string prefixes,
    #  including the opening quotes.
    single_quoted = set()
    triple_quoted = set()
    for t in _string_prefixes():
        for u in (t + '"', t + "'"):
            single_quoted.add(u)
        for u in (t + '"""', t + "'''"):
            triple_quoted.add(u)
    del t, u

    return {
        'Whitespace': Whitespace,
        'Comment': Comment,
        'Ignore': Ignore,
        'Name': Name,
        'Hexnumber': Hexnumber,
        'Binnumber': Binnumber,
        'Octnumber': Octnumber,
        'Decnumber': Decnumber,
        'Intnumber': Intnumber,
        'Exponent': Exponent,
        'Pointfloat': Pointfloat,
        'Expfloat': Expfloat,
        'Floatnumber': Floatnumber,
        'Imagnumber': Imagnumber,
        'Number': Number,
        'StringPrefix': StringPrefix,
        'Single': Single,
        'Double': Double,
        'Single3': Single3,
        'Double3': Double3,
        'Triple': Triple,
        'String': String,
        'Special': Special,
        'Funny': Funny,
        'PlainToken': PlainToken,
        'Token': Token,
        'ContStr': ContStr,
        'PseudoExtras': PseudoExtras,
        'PseudoToken': PseudoToken,
        'endpats': endpats,
        'single_quoted': single_quoted,
        'triple_quoted': triple_quoted,
    }
