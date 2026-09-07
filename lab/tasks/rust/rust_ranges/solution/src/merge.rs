use crate::ranges::Range;

pub fn merge(mut ranges: Vec<Range>) -> String {
    ranges.sort_by_key(|range| (range.start, range.end));
    let mut merged: Vec<Range> = Vec::new();
    for range in ranges {
        if let Some(previous) = merged.last_mut()
            && range.start <= previous.end
        {
            previous.end = previous.end.max(range.end);
            continue;
        }
        merged.push(range);
    }
    merged
        .into_iter()
        .map(|range| format!("{},{}\n", range.start, range.end))
        .collect()
}
