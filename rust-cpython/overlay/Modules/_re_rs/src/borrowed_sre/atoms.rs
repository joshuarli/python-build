use super::opcode::*;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Error {
    TruncatedCode,
    InvalidJump,
    InvalidPosition,
    NonAsciiInput,
    UnsupportedOpcode(u32),
    UnsupportedCategory(u32),
    UnsupportedAnchor(u32),
    MalformedCharset,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AtomStep {
    pub next_pc: usize,
    pub matched: bool,
    pub consumed: usize,
}

fn ascii(ch: u8) -> Result<(), Error> {
    if ch.is_ascii() { Ok(()) } else { Err(Error::NonAsciiInput) }
}

fn word(ch: u8) -> bool {
    ch.is_ascii_alphanumeric() || ch == b'_'
}

/// Categories are evaluated on ASCII input; Unicode whitespace keeps its
/// additional ASCII control separators instead of inheriting byte-space rules.
pub fn category(kind: u32, ch: u8) -> Result<bool, Error> {
    ascii(ch)?;
    let (positive, negate) = match kind {
        CATEGORY_DIGIT | CATEGORY_NOT_DIGIT | CATEGORY_UNI_DIGIT | CATEGORY_UNI_NOT_DIGIT =>
            (ch.is_ascii_digit(), kind == CATEGORY_NOT_DIGIT || kind == CATEGORY_UNI_NOT_DIGIT),
        CATEGORY_SPACE | CATEGORY_NOT_SPACE =>
            ((b'\t'..=b'\r').contains(&ch) || ch == b' ', kind == CATEGORY_NOT_SPACE),
        CATEGORY_UNI_SPACE | CATEGORY_UNI_NOT_SPACE =>
            ((b'\t'..=b'\r').contains(&ch) || ch == b' ' || (0x1c..=0x1f).contains(&ch),
             kind == CATEGORY_UNI_NOT_SPACE),
        CATEGORY_WORD | CATEGORY_NOT_WORD | CATEGORY_UNI_WORD | CATEGORY_UNI_NOT_WORD =>
            (word(ch), kind == CATEGORY_NOT_WORD || kind == CATEGORY_UNI_NOT_WORD),
        CATEGORY_LINEBREAK | CATEGORY_NOT_LINEBREAK =>
            (ch == b'\n', kind == CATEGORY_NOT_LINEBREAK),
        CATEGORY_UNI_LINEBREAK | CATEGORY_UNI_NOT_LINEBREAK =>
            (matches!(ch, b'\n'..=b'\r' | 0x1c..=0x1e), kind == CATEGORY_UNI_NOT_LINEBREAK),
        _ => return Err(Error::UnsupportedCategory(kind)),
    };
    Ok(positive != negate)
}

/// The slice ends at the set's FAILURE terminator, without subsequent code.
/// Validate the complete slice even after finding a member so malformed code
/// cannot become admissible merely because a particular input matches early.
pub fn charset(set: &[u32], ch: u8) -> Result<bool, Error> {
    ascii(ch)?;
    let mut pc = 0usize;
    let mut negated = false;
    let mut first_match = None;
    loop {
        let op = *set.get(pc).ok_or(Error::TruncatedCode)?;
        pc += 1;
        let matched = match op {
            OP_FAILURE => {
                if pc != set.len() { return Err(Error::MalformedCharset); }
                return Ok(first_match.unwrap_or(negated));
            }
            OP_NEGATE => { negated = !negated; continue; }
            OP_LITERAL => {
                let value = *set.get(pc).ok_or(Error::TruncatedCode)?;
                pc += 1;
                u32::from(ch) == value
            }
            OP_RANGE => {
                let low = *set.get(pc).ok_or(Error::TruncatedCode)?;
                let high = *set.get(pc + 1).ok_or(Error::TruncatedCode)?;
                if low > high { return Err(Error::MalformedCharset); }
                pc += 2;
                (low..=high).contains(&u32::from(ch))
            }
            OP_CHARSET => {
                let end = pc.checked_add(8).ok_or(Error::InvalidJump)?;
                let bits = set.get(pc..end).ok_or(Error::TruncatedCode)?;
                pc = end;
                bits[usize::from(ch) / 32] & (1u32 << (ch % 32)) != 0
            }
            OP_CATEGORY => {
                let kind = *set.get(pc).ok_or(Error::TruncatedCode)?;
                pc += 1;
                category(kind, ch)?
            }
            _ => return Err(Error::UnsupportedOpcode(op)),
        };
        if matched && first_match.is_none() { first_match = Some(!negated); }
    }
}

/// Position uses the whole borrowed subject's beginning and end. A final LF
/// satisfies END, while END_LINE also permits LF before the subject's end.
pub fn anchor(kind: u32, input: &[u8], pos: usize) -> Result<bool, Error> {
    if pos > input.len() { return Err(Error::InvalidPosition); }
    let before = if pos == 0 { None } else { Some(input[pos - 1]) };
    let after = input.get(pos).copied();
    if let Some(ch) = before { ascii(ch)?; }
    if let Some(ch) = after { ascii(ch)?; }
    Ok(match kind {
        AT_BEGINNING | AT_BEGINNING_STRING => pos == 0,
        AT_BEGINNING_LINE => pos == 0 || before == Some(b'\n'),
        AT_END => pos == input.len() || (input.len() - pos == 1 && after == Some(b'\n')),
        AT_END_LINE => pos == input.len() || after == Some(b'\n'),
        AT_END_STRING => pos == input.len(),
        AT_BOUNDARY | AT_UNI_BOUNDARY => before.is_some_and(word) != after.is_some_and(word),
        AT_NON_BOUNDARY | AT_UNI_NON_BOUNDARY => before.is_some_and(word) == after.is_some_and(word),
        _ => return Err(Error::UnsupportedAnchor(kind)),
    })
}

/// Decode one non-control instruction. Empty input still validates every
/// operand and set boundary, allowing structural admission before matching.
pub fn step(code: &[u32], pc: usize, input: &[u8], pos: usize) -> Result<AtomStep, Error> {
    if pos > input.len() { return Err(Error::InvalidPosition); }
    let op = *code.get(pc).ok_or(Error::TruncatedCode)?;
    let operand = pc.checked_add(1).ok_or(Error::InvalidJump)?;
    let ch = input.get(pos).copied();
    if let Some(ch) = ch { ascii(ch)?; }
    let (next_pc, matched, width) = match op {
        OP_LITERAL | OP_NOT_LITERAL => {
            let value = *code.get(operand).ok_or(Error::TruncatedCode)?;
            (operand.checked_add(1).ok_or(Error::InvalidJump)?,
             ch.is_some_and(|c| (u32::from(c) == value) == (op == OP_LITERAL)), 1)
        }
        OP_ANY | OP_ANY_ALL => (operand, ch.is_some_and(|c| op == OP_ANY_ALL || c != b'\n'), 1),
        OP_CATEGORY => {
            let kind = *code.get(operand).ok_or(Error::TruncatedCode)?;
            let member = category(kind, ch.unwrap_or(0))?;
            (operand.checked_add(1).ok_or(Error::InvalidJump)?, ch.is_some() && member, 1)
        }
        OP_IN => {
            let skip = usize::try_from(*code.get(operand).ok_or(Error::TruncatedCode)?)
                .map_err(|_| Error::InvalidJump)?;
            if skip < 2 { return Err(Error::InvalidJump); }
            let next = operand.checked_add(skip).ok_or(Error::InvalidJump)?;
            let start = operand.checked_add(1).ok_or(Error::InvalidJump)?;
            let set = code.get(start..next).ok_or(Error::TruncatedCode)?;
            let member = charset(set, ch.unwrap_or(0))?;
            (next, ch.is_some() && member, 1)
        }
        OP_AT => {
            let kind = *code.get(operand).ok_or(Error::TruncatedCode)?;
            (operand.checked_add(1).ok_or(Error::InvalidJump)?, anchor(kind, input, pos)?, 0)
        }
        _ => return Err(Error::UnsupportedOpcode(op)),
    };
    Ok(AtomStep { next_pc, matched, consumed: if matched { width } else { 0 } })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn categories_cover_every_ascii_byte_and_unicode_space_difference() {
        for ch in 0u8..=127 {
            let digit = (b'0'..=b'9').contains(&ch);
            let word = digit || (b'a'..=b'z').contains(&ch)
                || (b'A'..=b'Z').contains(&ch) || ch == b'_';
            let space = (9..=13).contains(&ch) || ch == 32;
            let uni_space = space || (28..=31).contains(&ch);
            let uni_line = matches!(ch, 10..=13 | 28..=30);
            for (kind, expected) in [(CATEGORY_DIGIT, digit), (CATEGORY_SPACE, space),
                (CATEGORY_WORD, word), (CATEGORY_LINEBREAK, ch == b'\n'),
                (CATEGORY_UNI_DIGIT, digit), (CATEGORY_UNI_SPACE, uni_space),
                (CATEGORY_UNI_WORD, word), (CATEGORY_UNI_LINEBREAK, uni_line)] {
                assert_eq!(category(kind, ch), Ok(expected));
                assert_eq!(category(kind + 1, ch), Ok(!expected));
            }
        }
        assert!(category(CATEGORY_LOC_WORD, b'a').is_err());
        assert!(category(CATEGORY_WORD, 128).is_err());
    }

    #[test]
    fn charset_negation_ranges_and_bitmap_keep_first_match_semantics() {
        let code = [OP_NEGATE, OP_LITERAL, b'a' as u32, OP_RANGE, b'c' as u32,
                    b'f' as u32, OP_FAILURE];
        assert_eq!(charset(&code, b'a'), Ok(false));
        assert_eq!(charset(&code, b'd'), Ok(false));
        assert_eq!(charset(&code, b'z'), Ok(true));
        assert_eq!(charset(&[OP_NEGATE, OP_NEGATE, OP_LITERAL, 97, OP_FAILURE], b'a'), Ok(true));
        assert_eq!(charset(&[OP_LITERAL, 97, OP_NEGATE, OP_FAILURE], b'a'), Ok(true));
        let mut bitmap = [0u32; 10];
        bitmap[0] = OP_CHARSET;
        bitmap[1 + 0 / 32] |= 1 << (0 % 32);
        bitmap[1 + 127 / 32] |= 1 << (127 % 32);
        bitmap[9] = OP_FAILURE;
        for ch in 0u8..=127 {
            assert_eq!(charset(&bitmap, ch), Ok(ch == 0 || ch == 127));
        }
    }

    #[test]
    fn malformed_charset_is_rejected_even_after_a_matching_member() {
        for code in [&[OP_LITERAL][..], &[OP_RANGE, 100, 90, OP_FAILURE],
                     &[OP_CHARSET, 1, OP_FAILURE], &[OP_LITERAL, 97],
                     &[OP_LITERAL, 97, OP_BIGCHARSET, OP_FAILURE],
                     &[OP_FAILURE, OP_LITERAL, 97]] {
            assert!(charset(code, b'a').is_err());
        }
    }

    #[test]
    fn anchors_distinguish_beginning_final_newline_and_empty_nonboundary() {
        assert_eq!(anchor(AT_BEGINNING, b"a\nb", 0), Ok(true));
        assert_eq!(anchor(AT_BEGINNING_LINE, b"a\nb", 2), Ok(true));
        assert_eq!(anchor(AT_BEGINNING_STRING, b"a\nb", 2), Ok(false));
        assert_eq!(anchor(AT_END, b"a\nb", 1), Ok(false));
        assert_eq!(anchor(AT_END_LINE, b"a\nb", 1), Ok(true));
        assert_eq!(anchor(AT_END, b"a\n", 1), Ok(true));
        assert_eq!(anchor(AT_END_STRING, b"a\n", 1), Ok(false));
        for kind in [AT_BEGINNING, AT_BEGINNING_STRING, AT_END, AT_END_STRING] {
            assert_eq!(anchor(kind, b"", 0), Ok(true));
        }
        assert_eq!(anchor(AT_BOUNDARY, b"", 0), Ok(false));
        assert_eq!(anchor(AT_NON_BOUNDARY, b"", 0), Ok(true));
        for kind in [AT_BOUNDARY, AT_UNI_BOUNDARY] {
            assert_eq!(anchor(kind, b" a_!", 1), Ok(true));
            assert_eq!(anchor(kind, b" a_!", 2), Ok(false));
            assert_eq!(anchor(kind, b" a_!", 3), Ok(true));
        }
        assert!(anchor(AT_END, b"x", 2).is_err());
    }

    #[test]
    fn atom_steps_use_checked_skip_and_consumption_on_success_only() {
        let code = [OP_IN, 5, OP_RANGE, 97, 122, OP_FAILURE, OP_ANY_ALL];
        assert_eq!(step(&code, 0, b"a", 0), Ok(AtomStep { next_pc: 6, matched: true, consumed: 1 }));
        assert_eq!(step(&code, 0, b"!", 0), Ok(AtomStep { next_pc: 6, matched: false, consumed: 0 }));
        assert_eq!(step(&[OP_ANY], 0, b"\n", 0).unwrap().matched, false);
        assert_eq!(step(&[OP_ANY_ALL], 0, b"\n", 0).unwrap().matched, true);
        assert_eq!(step(&[OP_LITERAL, 97], 0, b"", 0).unwrap().matched, false);
        assert_eq!(step(&[OP_NOT_LITERAL, 97], 0, b"b", 0).unwrap().matched, true);
        assert_eq!(step(&[OP_AT, AT_END_STRING], 0, b"", 0).unwrap().consumed, 0);
        for code in [&[OP_IN, u32::MAX][..], &[OP_IN, 0], &[OP_LITERAL], &[OP_AT]] {
            assert!(step(code, 0, b"", 0).is_err());
        }
        assert!(step(&[OP_ANY], usize::MAX, b"x", 0).is_err());
    }
}
