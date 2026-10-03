use super::{CACHE_LIMIT, portable_expression, regex_cache};
use std::sync::Mutex;

static TEST_CACHE: Mutex<()> = Mutex::new(());

fn clear_cache() {
    let mut cache = regex_cache();
    cache.expressions.clear();
    cache.insertion_order.clear();
}

#[test]
fn map_and_fifo_retain_one_key_buffer_and_hits_keep_order() {
    let _serial = TEST_CACHE.lock().unwrap();
    clear_cache();
    let pattern = "shared-key-identity";
    let first = portable_expression(pattern).unwrap();
    let second = portable_expression(pattern).unwrap();
    let cache = regex_cache();
    assert_eq!(cache.expressions.len(), 1);
    assert_eq!(cache.insertion_order.len(), 1);
    let map_key = cache.expressions.get_key_value(pattern).unwrap().0;
    let fifo_key = cache.insertion_order.front().unwrap();
    assert_eq!(map_key.as_ptr(), fifo_key.as_ptr());
    assert_eq!(&**map_key, pattern);
    assert_eq!(&**fifo_key, pattern);
    assert_eq!(first.as_str().as_ptr(), second.as_str().as_ptr());
    assert!(first.is_match(pattern));
    assert!(second.is_match(pattern));
}

#[test]
fn bounded_fifo_eviction_preserves_held_engines_and_reinsertion() {
    let _serial = TEST_CACHE.lock().unwrap();
    clear_cache();
    let oldest = "shared-key-evict-0";
    let held = portable_expression(oldest).unwrap();
    for index in 1..CACHE_LIMIT {
        portable_expression(&format!("shared-key-evict-{index}")).unwrap();
    }
    portable_expression(oldest).unwrap();
    {
        let cache = regex_cache();
        assert_eq!(cache.expressions.len(), CACHE_LIMIT);
        assert_eq!(&**cache.insertion_order.front().unwrap(), oldest);
    }
    portable_expression("shared-key-evict-new").unwrap();
    {
        let cache = regex_cache();
        assert_eq!(cache.expressions.len(), CACHE_LIMIT);
        assert_eq!(cache.insertion_order.len(), CACHE_LIMIT);
        assert!(!cache.expressions.contains_key(oldest));
        assert_eq!(&**cache.insertion_order.front().unwrap(), "shared-key-evict-1");
        assert_eq!(&**cache.insertion_order.back().unwrap(), "shared-key-evict-new");
        for fifo_key in &cache.insertion_order {
            let map_key = cache.expressions.get_key_value(&**fifo_key).unwrap().0;
            assert_eq!(map_key.as_ptr(), fifo_key.as_ptr());
        }
    }
    assert!(held.is_match(oldest));
    assert!(portable_expression(oldest).unwrap().is_match(oldest));
    {
        let cache = regex_cache();
        assert!(!cache.expressions.contains_key("shared-key-evict-1"));
        assert_eq!(&**cache.insertion_order.back().unwrap(), oldest);
    }
    assert!(portable_expression("value=(\\d+)$").is_none());
    assert_eq!(regex_cache().expressions.len(), CACHE_LIMIT);
}
