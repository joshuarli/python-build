//! Search canonical SRE programs without retaining a second compiled engine.
#[path = "borrowed_sre/atoms.rs"]
mod atoms;
#[path = "borrowed_sre/opcode.rs"]
mod opcode;
use opcode::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error { Unsupported, InvalidProgram, AllocationFailed, Interrupted }
fn atom_error(error: atoms::Error) -> Error {
    match error {
        atoms::Error::UnsupportedOpcode(_) | atoms::Error::UnsupportedCategory(_) |
        atoms::Error::UnsupportedAnchor(_) => Error::Unsupported,
        _ => Error::InvalidProgram,
    }
}
fn push<T>(items: &mut Vec<T>, value: T) -> Result<(), Error> {
    items.try_reserve(1).map_err(|_| Error::AllocationFailed)?;
    items.push(value); Ok(())
}
fn word(code: &[u32], pc: usize) -> Result<u32, Error> {
    code.get(pc).copied().ok_or(Error::InvalidProgram)
}
fn offset(code: &[u32], pc: usize) -> Result<usize, Error> {
    let target = pc.checked_add(word(code, pc)? as usize).ok_or(Error::InvalidProgram)?;
    if target >= code.len() { return Err(Error::InvalidProgram); }
    Ok(target)
}
fn claim(marks: &mut [u8], start: usize, end: usize) -> Result<(), Error> {
    if end > marks.len() || start >= end || marks[start] == 2 { return Err(Error::InvalidProgram); }
    marks[start] = 1;
    for value in &mut marks[start + 1..end] {
        if *value == 1 { return Err(Error::InvalidProgram); }
        *value = 2;
    }
    Ok(())
}
// Each executable word and operand has one role. Forward targets must never
// enter an operand, including branch offsets and repeat bounds.
pub fn validate(code: &[u32]) -> Result<(), Error> {
    if code.is_empty() { return Err(Error::InvalidProgram); }
    let mut marks = Vec::new();
    marks.try_reserve_exact(code.len()).map_err(|_| Error::AllocationFailed)?;
    marks.resize(code.len(), 0);
    let mut pending = Vec::new(); push(&mut pending, 0usize)?;
    while let Some(pc) = pending.pop() {
        if pc >= code.len() || marks[pc] == 2 { return Err(Error::InvalidProgram); }
        if marks[pc] == 1 { continue; }
        match word(code, pc)? {
            OP_SUCCESS | OP_FAILURE => claim(&mut marks, pc, pc + 1)?,
            OP_INFO => {
                let next = offset(code, pc + 1)?;
                if next < pc + 5 || word(code, pc + 2)? & !7 != 0 { return Err(Error::InvalidProgram); }
                claim(&mut marks, pc, next)?; push(&mut pending, next)?;
            }
            OP_MARK => { word(code, pc + 1)?; claim(&mut marks, pc, pc + 2)?; push(&mut pending, pc + 2)?; }
            OP_JUMP => {
                let next = offset(code, pc + 1)?;
                if next <= pc + 1 { return Err(Error::InvalidProgram); }
                claim(&mut marks, pc, pc + 2)?; push(&mut pending, next)?;
            }
            OP_BRANCH => {
                claim(&mut marks, pc, pc + 1)?;
                let mut arm = pc + 1;
                loop {
                    if marks.get(arm).copied().unwrap_or(1) != 0 { return Err(Error::InvalidProgram); }
                    marks[arm] = 2;
                    if word(code, arm)? == 0 { break; }
                    let next = offset(code, arm)?;
                    if next <= arm + 1 { return Err(Error::InvalidProgram); }
                    push(&mut pending, arm + 1)?; arm = next;
                }
            }
            OP_REPEAT | OP_REPEAT_ONE | OP_MIN_REPEAT_ONE => {
                let end = offset(code, pc + 1)?;
                let min = word(code, pc + 2)?; let max = word(code, pc + 3)?;
                if min > max || end <= pc + 4 { return Err(Error::InvalidProgram); }
                claim(&mut marks, pc, pc + 4)?;
                if code[pc] == OP_REPEAT {
                    if !matches!(word(code, end)?, OP_MAX_UNTIL | OP_MIN_UNTIL) { return Err(Error::InvalidProgram); }
                    push(&mut pending, end)?;
                } else {
                    let atom = atoms::step(code, pc + 4, b"", 0).map_err(atom_error)?;
                    if atom.next_pc != end - 1 || word(code, end - 1)? != OP_SUCCESS { return Err(Error::InvalidProgram); }
                    push(&mut pending, end)?;
                }
                push(&mut pending, pc + 4)?;
            }
            OP_MAX_UNTIL | OP_MIN_UNTIL => {
                claim(&mut marks, pc, pc + 1)?; push(&mut pending, pc + 1)?;
            }
            _ => {
                let atom = atoms::step(code, pc, b"", 0).map_err(atom_error)?;
                claim(&mut marks, pc, atom.next_pc)?; push(&mut pending, atom.next_pc)?;
            }
        }
    }
    if marks.contains(&0) { return Err(Error::InvalidProgram); }
    Ok(())
}
pub fn supported(code: &[u32]) -> bool { validate(code).is_ok() }

#[derive(Clone, Copy)]
struct State { pc: usize, pos: usize, repeat: Option<usize> }
#[derive(Clone, Copy)]
struct Repeat {
    parent: Option<usize>, body: usize, until: usize, tail: usize,
    min: u32, max: u32, count: u32, previous: Option<usize>, greedy: bool,
}
// Repeat contexts are immutable snapshots indexed by pending alternatives.
// They are discarded after this search; empty bodies may satisfy the minimum
// but cannot keep growing after the first iteration without progress.
fn repeat_step(state: State, repeats: &mut Vec<Repeat>, alternatives: &mut Vec<State>) -> Result<Option<State>, Error> {
    let index = state.repeat.ok_or(Error::InvalidProgram)?;
    let repeat = *repeats.get(index).ok_or(Error::InvalidProgram)?;
    let tail = State { pc: repeat.tail, pos: state.pos, repeat: repeat.parent };
    let can_grow = repeat.count < repeat.max && (repeat.count < repeat.min || repeat.previous != Some(state.pos));
    let body = if can_grow {
        let index = repeats.len();
        push(repeats, Repeat { count: repeat.count + 1, previous: Some(state.pos), ..repeat })?;
        Some(State { pc: repeat.body, pos: state.pos, repeat: Some(index) })
    } else { None };
    if repeat.count < repeat.min { return Ok(body); }
    match body {
        Some(body) if repeat.greedy => { push(alternatives, tail)?; Ok(Some(body)) }
        Some(body) => { push(alternatives, body)?; Ok(Some(tail)) }
        None => Ok(Some(tail)),
    }
}
// Discard snapshots whose branches have finished. Parent indices precede child
// indices, so compaction rewrites each live parent before its children and keeps
// memory proportional to pending paths rather than all explored paths.
fn compact_repeats(repeats: &mut Vec<Repeat>, current: &mut Option<State>, alternatives: &mut [State]) -> Result<(), Error> {
    let length = repeats.len();
    let mut mapping = Vec::new();
    mapping.try_reserve_exact(length).map_err(|_| Error::AllocationFailed)?;
    mapping.resize(length, usize::MAX);
    for state in current.iter().chain(alternatives.iter()) {
        let mut parent = state.repeat;
        while let Some(index) = parent {
            let mark = mapping.get_mut(index).ok_or(Error::InvalidProgram)?;
            if *mark != usize::MAX { break; }
            *mark = length;
            parent = repeats[index].parent;
        }
    }
    let mut kept = 0;
    for index in 0..length {
        if mapping[index] == usize::MAX { continue; }
        let mut repeat = repeats[index];
        repeat.parent = repeat.parent.map(|parent| mapping[parent]);
        repeats[kept] = repeat;
        mapping[index] = kept;
        kept += 1;
    }
    for state in current.iter_mut().chain(alternatives.iter_mut()) {
        state.repeat = state.repeat.map(|index| mapping[index]);
    }
    repeats.truncate(kept);
    Ok(())
}
pub fn search(code: &[u32], input: &[u8]) -> Result<Option<(usize, usize)>, Error> {
    search_with_interrupt(code, input, || false)
}
pub fn search_with_interrupt(code: &[u32], input: &[u8], mut poll: impl FnMut() -> bool) -> Result<Option<(usize, usize)>, Error> {
    if !input.is_ascii() { return Err(Error::Unsupported); }
    validate(code)?;
    let mut alternatives = Vec::new(); let mut repeats: Vec<Repeat> = Vec::new();
    let mut ticks = 0u32;
    for start in 0..=input.len() {
        alternatives.clear(); repeats.clear();
        let mut current = Some(State { pc: 0, pos: start, repeat: None });
        while let Some(mut state) = current {
            ticks = ticks.wrapping_add(1);
            if ticks & 1023 == 0 {
                if poll() { return Err(Error::Interrupted); }
                if repeats.len() > 1024 {
                    let mut selected = Some(state);
                    compact_repeats(&mut repeats, &mut selected, &mut alternatives)?;
                    state = selected.ok_or(Error::InvalidProgram)?;
                }
            }
            if let Some(index) = state.repeat {
                if repeats[index].until == state.pc {
                    current = repeat_step(state, &mut repeats, &mut alternatives)?;
                    if current.is_none() { current = alternatives.pop(); }
                    continue;
                }
            }
            current = match word(code, state.pc)? {
                OP_SUCCESS => return Ok(Some((start, state.pos))),
                OP_FAILURE => None,
                OP_INFO | OP_JUMP => { state.pc = offset(code, state.pc + 1)?; Some(state) }
                OP_MARK => { state.pc += 2; Some(state) }
                OP_BRANCH => {
                    let base = alternatives.len(); let mut arm = state.pc + 1;
                    while word(code, arm)? != 0 {
                        push(&mut alternatives, State { pc: arm + 1, ..state })?;
                        arm = offset(code, arm)?;
                    }
                    alternatives[base..].reverse(); alternatives.pop()
                }
                OP_REPEAT | OP_REPEAT_ONE | OP_MIN_REPEAT_ONE => {
                    let end = offset(code, state.pc + 1)?;
                    let general = code[state.pc] == OP_REPEAT;
                    let repeat = Repeat { parent: state.repeat, body: state.pc + 4,
                        until: if general { end } else { end - 1 }, tail: if general { end + 1 } else { end },
                        min: code[state.pc + 2], max: code[state.pc + 3], count: 0, previous: None,
                        greedy: if general { code[end] == OP_MAX_UNTIL } else { code[state.pc] == OP_REPEAT_ONE } };
                    let index = repeats.len(); push(&mut repeats, repeat)?;
                    state.repeat = Some(index); state.pc = repeat.until;
                    repeat_step(state, &mut repeats, &mut alternatives)?
                }
                OP_MAX_UNTIL | OP_MIN_UNTIL => return Err(Error::InvalidProgram),
                _ => {
                    let atom = atoms::step(code, state.pc, input, state.pos).map_err(atom_error)?;
                    if atom.matched { state.pc = atom.next_pc; state.pos += atom.consumed; Some(state) } else { None }
                }
            };
            if current.is_none() { current = alternatives.pop(); }
        }
    }
    Ok(None)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn leftmost_branch_priority() {
        let code = [OP_BRANCH, 5, OP_LITERAL, 97, OP_JUMP, 7, 5, OP_LITERAL, 98, OP_JUMP, 2, 0, OP_SUCCESS];
        assert_eq!(search(&code, b"xba"), Ok(Some((1, 2))));
    }
    #[test] fn greedy_and_reluctant_one() {
        let mut code = [OP_REPEAT_ONE, 6, 0, u32::MAX, OP_LITERAL, 97, OP_SUCCESS, OP_LITERAL, 97, OP_SUCCESS];
        assert_eq!(search(&code, b"aaa"), Ok(Some((0, 3))));
        code[0] = OP_MIN_REPEAT_ONE;
        assert_eq!(search(&code, b"aaa"), Ok(Some((0, 1))));
    }
    #[test] fn grouped_repeat_and_empty_progress() {
        let code = [OP_REPEAT, 7, 0, u32::MAX, OP_LITERAL, 97, OP_LITERAL, 98, OP_MAX_UNTIL, OP_SUCCESS];
        assert_eq!(search(&code, b"ababx"), Ok(Some((0, 4))));
        let empty = [OP_REPEAT, 5, 2, u32::MAX, OP_MARK, 0, OP_MAX_UNTIL, OP_SUCCESS];
        assert_eq!(search(&empty, b""), Ok(Some((0, 0))));
    }
    #[test] fn nested_repeat_backtracks_to_outer_tail() {
        // (a*)*b: an empty inner iteration must not retain the outer loop.
        let code = [OP_REPEAT, 10, 0, u32::MAX, OP_REPEAT_ONE, 6, 0, u32::MAX,
            OP_LITERAL, 97, OP_SUCCESS, OP_MAX_UNTIL, OP_LITERAL, 98, OP_SUCCESS];
        assert_eq!(search(&code, b"aaab"), Ok(Some((0, 4))));
        assert_eq!(search(&code, b"aaa"), Ok(None));
    }
    #[test] fn repeat_arena_compaction_retains_only_live_parent_chains() {
        let base = Repeat { parent: None, body: 1, until: 2, tail: 3, min: 0,
            max: 9, count: 1, previous: Some(0), greedy: true };
        let mut repeats = vec![base, base, Repeat { parent: Some(0), ..base }, base];
        let mut current = Some(State { pc: 1, pos: 2, repeat: Some(2) });
        let mut alternatives = vec![State { pc: 3, pos: 1, repeat: Some(0) }];
        compact_repeats(&mut repeats, &mut current, &mut alternatives).unwrap();
        assert_eq!(repeats.len(), 2);
        assert_eq!(current.unwrap().repeat, Some(1));
        assert_eq!(repeats[1].parent, Some(0));
        assert_eq!(alternatives[0].repeat, Some(0));
    }
    #[test] fn dead_branch_snapshots_do_not_accumulate() {
        let repeat = Repeat { parent: None, body: 1, until: 2, tail: 3, min: 0,
            max: 9, count: 1, previous: Some(0), greedy: true };
        let mut repeats = vec![repeat];
        let mut current = Some(State { pc: 1, pos: 0, repeat: Some(0) });
        let mut alternatives = vec![State { pc: 3, pos: 0, repeat: Some(0) }];
        for _ in 0..20 {
            // Finished branches have no references in the pending states.
            for _ in 0..1024 { push(&mut repeats, repeat).unwrap(); }
            compact_repeats(&mut repeats, &mut current, &mut alternatives).unwrap();
            assert_eq!(repeats.len(), 1);
        }
        let code = [14, 4, 0, 1, u32::MAX, 23, 19, 0, u32::MAX,
            17, 0, 16, 97, 7, 3, 15, 7, 5, 16, 97, 15, 2, 0, 17, 1, 18, 16, 98, 1];
        assert_eq!(search(&code, b"aaaaaaaaaaaaaaaa"), Ok(None));
        assert_eq!(search(&code, b"aaaaaaaaaaaaaaaab"), Ok(Some((0, 17))));
    }
    #[test] fn interruption_is_distinct_from_no_match() {
        let code = [OP_LITERAL, 97, OP_SUCCESS];
        assert_eq!(search_with_interrupt(&code, &vec![98; 2048], || true), Err(Error::Interrupted));
    }
    #[test] fn malformed_targets_and_unsupported_are_distinct() {
        assert_eq!(search(&[OP_JUMP, 0, OP_SUCCESS], b""), Err(Error::InvalidProgram));
        assert_eq!(search(&[4, 0, OP_SUCCESS], b""), Err(Error::Unsupported));
    }
}
