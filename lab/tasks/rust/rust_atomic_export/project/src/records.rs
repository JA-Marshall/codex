use std::collections::BTreeMap;

pub fn parse(input: &str) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    for (index, line) in input.lines().enumerate() {
        if line.is_empty() {
            continue;
        }
        let (key, value) = line
            .split_once('\t')
            .ok_or_else(|| format!("line {}: expected key and value", index + 1))?;
        if key.is_empty()
            || !key
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
            || value.contains('\t')
        {
            return Err(format!("line {}: invalid record", index + 1));
        }
        values.insert(key.into(), value.into());
    }
    Ok(values)
}

pub fn render(values: &BTreeMap<String, String>) -> String {
    values
        .iter()
        .map(|(key, value)| format!("{key}\t{value}\n"))
        .collect()
}
