#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Event {
    pub id: String,
    pub account: String,
    pub delta: i64,
}

pub fn parse(input: &str) -> Result<Vec<Event>, String> {
    let mut events = Vec::new();
    for (index, line) in input.lines().enumerate() {
        if line.is_empty() {
            continue;
        }
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 3 || fields[0].is_empty() || fields[1].is_empty() {
            return Err(format!("line {}: invalid event", index + 1));
        }
        let delta = fields[2]
            .parse::<i64>()
            .map_err(|_| format!("line {}: invalid delta", index + 1))?;
        events.push(Event {
            id: fields[0].into(),
            account: fields[1].into(),
            delta,
        });
    }
    Ok(events)
}
