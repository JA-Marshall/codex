pub struct Record {
    pub timestamp: u64,
    pub level: String,
}

pub fn parse(input: &str) -> Result<Vec<Record>, String> {
    let mut records = Vec::new();
    for (index, line) in input.lines().enumerate() {
        if line.is_empty() {
            continue;
        }
        let fields: Vec<_> = line.splitn(3, '\t').collect();
        if fields.len() != 3 || fields[1].is_empty() {
            return Err(format!("line {}: invalid record", index + 1));
        }
        let timestamp = fields[0]
            .parse::<u64>()
            .map_err(|_| format!("line {}: invalid timestamp", index + 1))?;
        records.push(Record {
            timestamp,
            level: fields[1].into(),
        });
    }
    Ok(records)
}
