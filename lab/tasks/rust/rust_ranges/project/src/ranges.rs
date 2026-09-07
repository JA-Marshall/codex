#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Range {
    pub start: i64,
    pub end: i64,
}

pub fn parse(input: &str) -> Result<Vec<Range>, String> {
    let mut ranges = Vec::new();
    for (index, line) in input.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let fail = || format!("line {}: invalid range", index + 1);
        let (start, end) = line.split_once(',').ok_or_else(fail)?;
        let start = start.trim().parse::<i64>().map_err(|_| fail())?;
        let end = end.trim().parse::<i64>().map_err(|_| fail())?;
        if start > end {
            return Err(fail());
        }
        if start < end {
            ranges.push(Range { start, end });
        }
    }
    Ok(ranges)
}
