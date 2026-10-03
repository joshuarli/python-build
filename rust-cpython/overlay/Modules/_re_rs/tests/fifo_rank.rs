use super::{CACHE_LIMIT, RegexCache, portable_expression, prepare_expression, regex_cache};
use std::collections::VecDeque;
use std::sync::{Arc, Barrier, Mutex, OnceLock};

static TEST_SERIAL: Mutex<()> = Mutex::new(());
static COMPILE_PAUSE: OnceLock<Mutex<Option<CompilePause>>> = OnceLock::new();

struct CompilePause {
    pattern: &'static str,
    barrier: Arc<Barrier>,
}

pub(super) fn after_compile(pattern: &str) {
    let barrier = COMPILE_PAUSE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap()
        .as_ref()
        .filter(|pause| pause.pattern == pattern)
        .map(|pause| Arc::clone(&pause.barrier));
    if let Some(barrier) = barrier {
        barrier.wait();
    }
}

struct Reset;

impl Drop for Reset {
    fn drop(&mut self) {
        *COMPILE_PAUSE.get_or_init(|| Mutex::new(None)).lock().unwrap() = None;
        *regex_cache() = RegexCache::new();
    }
}

fn insertion_order() -> Vec<String> {
    let cache = regex_cache();
    assert!(cache.expressions.len() <= CACHE_LIMIT);
    let mut entries: Vec<_> = cache.expressions.iter().collect();
    entries.sort_by_key(|(_, entry)| entry.insertion_rank);
    for (rank, (_, entry)) in entries.iter().enumerate() {
        assert_eq!(usize::from(entry.insertion_rank), rank);
    }
    entries.into_iter().map(|(pattern, _)| pattern.clone()).collect()
}

#[test]
fn insertion_fifo_matches_reference_through_hits_and_churn() {
    let _serial = TEST_SERIAL.lock().unwrap();
    let _reset = Reset;
    *regex_cache() = RegexCache::new();
    let mut expected: VecDeque<String> = VecDeque::new();
    for index in 0..(CACHE_LIMIT + 900) {
        if let Some(oldest) = expected.front() {
            let before = insertion_order();
            assert!(portable_expression(oldest).unwrap().is_match(oldest.as_bytes()));
            assert_eq!(insertion_order(), before);
        }
        let pattern = format!("fifo_{index}");
        assert!(portable_expression(&pattern).unwrap().is_match(pattern.as_bytes()));
        if expected.len() == CACHE_LIMIT {
            expected.pop_front();
        }
        expected.push_back(pattern);
        assert_eq!(insertion_order(), expected.iter().cloned().collect::<Vec<_>>());
    }
}

#[test]
fn held_expression_survives_eviction_and_reinsertion() {
    let _serial = TEST_SERIAL.lock().unwrap();
    let _reset = Reset;
    *regex_cache() = RegexCache::new();
    let held = portable_expression("held_[0-9]+").unwrap();
    let held_text = held.as_str().as_ptr();
    for index in 0..CACHE_LIMIT {
        portable_expression(&format!("held_churn_{index}")).unwrap();
    }
    assert!(!regex_cache().expressions.contains_key("held_[0-9]+"));
    assert!(held.is_match(b"held_42"));
    let reinserted = portable_expression("held_[0-9]+").unwrap();
    assert_ne!(held_text, reinserted.as_str().as_ptr());
    assert!(reinserted.is_match(b"held_42"));
    let order = insertion_order();
    assert_eq!(order.first().unwrap(), "held_churn_1");
    assert_eq!(order.last().unwrap(), "held_[0-9]+");
}

#[test]
fn rejected_patterns_and_prepare_do_not_change_fifo() {
    let _serial = TEST_SERIAL.lock().unwrap();
    let _reset = Reset;
    *regex_cache() = RegexCache::new();
    for index in 0..5 {
        portable_expression(&format!("valid_{index}")).unwrap();
    }
    let before = insertion_order();
    for pattern in ["*", "[", "(?=x)", "é", "value=(\\d+)$"] {
        assert!(portable_expression(pattern).is_none());
        assert_eq!(insertion_order(), before);
    }
    assert!(prepare_expression("prepared_[0-9]+"));
    assert_eq!(insertion_order(), before);
}

#[test]
fn eight_compile_racers_return_one_winner_without_duplicate_age() {
    let _serial = TEST_SERIAL.lock().unwrap();
    let _reset = Reset;
    *regex_cache() = RegexCache::new();
    const PATTERN: &str = "race_[0-9]+";
    *COMPILE_PAUSE.get_or_init(|| Mutex::new(None)).lock().unwrap() = Some(CompilePause {
        pattern: PATTERN,
        barrier: Arc::new(Barrier::new(8)),
    });
    let workers: Vec<_> = (0..8)
        .map(|_| std::thread::spawn(|| portable_expression(PATTERN).unwrap()))
        .collect();
    let held: Vec<_> = workers.into_iter().map(|worker| worker.join().unwrap()).collect();
    *COMPILE_PAUSE.get().unwrap().lock().unwrap() = None;
    assert_eq!(insertion_order(), [PATTERN]);
    let cached_text = regex_cache().expressions[PATTERN].expression.as_str().as_ptr();
    for expression in &held {
        assert_eq!(expression.as_str().as_ptr(), cached_text);
    }
    for index in 0..CACHE_LIMIT {
        portable_expression(&format!("race_churn_{index}")).unwrap();
    }
    assert!(!regex_cache().expressions.contains_key(PATTERN));
    assert_eq!(insertion_order().len(), CACHE_LIMIT);
    for expression in held {
        assert!(expression.is_match(b"race_42"));
    }
}
