use super::*;
use regex::bytes::RegexBuilder;
use regex_automata::{nfa::thompson::WhichCaptures, PatternID};

fn compare(pattern: &str, subjects: &[&[u8]]) {
    let old = RegexBuilder::new(pattern).unicode(false).build().unwrap();
    let new = compile_expression(pattern).unwrap();
    assert_eq!(new.get_config().get_which_captures(), WhichCaptures::All);
    assert_eq!(new.group_info().group_len(PatternID::ZERO), old.captures_len());
    for subject in subjects {
        let expected = old.find(subject).map(|m| (m.start(), m.end()));
        assert_eq!(new.find(*subject).map(|m| (m.start(), m.end())), expected, "{pattern:?} {subject:?}");
        assert_eq!(new.clone().find(*subject).map(|m| (m.start(), m.end())), expected);
    }
}

#[test]
fn source_owner_elision_preserves_kernel_engines_and_capture_metadata() {
    let subjects: &[&[u8]] = &[
        b"alice@example.com", b"record=42;name=alice-9", b"Alice 2026",
        b"GET /records HTTP/1.1", b"192.168.1.2", b"not a match", b"",
    ];
    for pattern in [r"\b(\w+)@(\w+)\.com\b", r"^record=(\d+);name=([a-z-]+\d*)",
        r"[A-Z][a-z]+ \d{4}", r"(?:GET|POST) (/\S*) HTTP/1\.[01]", r"\d+\.\d+\.\d+\.\d+"] {
        assert!(supported_pattern(pattern));
        compare(pattern, subjects);
    }
}

#[test]
fn source_owner_elision_preserves_leftmost_empty_byte_and_anchor_semantics() {
    let subjects: &[&[u8]] = &[b"", b"ab", b"a\nb", b"\r\n", b" \t\n\r\x0c\x0b\x1c\x1f", b"\xffa", b"_ a-1"];
    for pattern in ["", "a|ab", "ab|a", "a*", "^a", r"\Aa", r"\b\w+", r"\s+",
        r"(a)(b)?", r"(?:a|b)+", r"[a-z--m]+"] {
        compare(pattern, subjects);
    }
    for depth in [8, 128] {
        let pattern = format!("{}a{}", "(".repeat(depth), ")".repeat(depth));
        compare(&pattern, &[b"a", b"b"]);
    }
}

#[test]
fn source_owner_elision_preserves_compile_rejections_and_error_conversion() {
    for depth in [249, 250, 251] {
        let pattern = format!("{}a{}", "(".repeat(depth), ")".repeat(depth));
        let old = RegexBuilder::new(&pattern).unicode(false).build();
        let new = compile_expression(&pattern);
        assert_eq!(old.is_ok(), new.is_ok(), "nesting depth {depth}");
        if old.is_ok() {
            compare(&pattern, &[b"a", b"b"]);
        }
    }
    let nested = format!("{}a{}", "(".repeat(300), ")".repeat(300));
    for pattern in ["(", "[", "a{2,1}", r"\q", "a{10000000}", nested.as_str()] {
        let old = RegexBuilder::new(pattern).unicode(false).build().unwrap_err();
        let new = compile_expression(pattern).unwrap_err();
        match old {
            regex::Error::CompiledTooBig(limit) => assert_eq!(new.size_limit(), Some(limit)),
            regex::Error::Syntax(message) => {
                let converted = new.syntax_error().map(|e| e.to_string()).unwrap_or_else(|| new.to_string());
                assert_eq!(converted, message);
            }
            _ => panic!("unexpected reference error"),
        }
    }
}

#[test]
fn source_owner_elision_preserves_fifo_hits_reinsert_and_held_engine() {
    *regex_cache() = RegexCache::new();
    let first = "source-owner-fifo-0";
    let held = portable_expression(first).unwrap();
    for index in 1..CACHE_LIMIT {
        portable_expression(&format!("source-owner-fifo-{index}")).unwrap();
    }
    portable_expression(first).unwrap();
    portable_expression("source-owner-fifo-extra").unwrap();
    {
        let cache = regex_cache();
        assert_eq!(cache.expressions.len(), CACHE_LIMIT);
        assert_eq!(cache.insertion_order.len(), CACHE_LIMIT);
        assert!(!cache.expressions.contains_key(first));
        assert_eq!(cache.insertion_order.front().unwrap(), "source-owner-fifo-1");
    }
    assert_eq!(held.find(first.as_bytes()).unwrap().range(), 0..first.len());
    let rebuilt = portable_expression(first).unwrap();
    assert_eq!(rebuilt.find(first.as_bytes()).unwrap().range(), 0..first.len());
    let cache = regex_cache();
    assert_eq!(cache.insertion_order.back().unwrap(), first);
    assert!(!cache.expressions.contains_key("source-owner-fifo-1"));
}
