pub fn parse(input: &str) -> Result<Vec<(String, i64)>, String> {
    let mut rows = Vec::new();
    for (index, line) in input.lines().enumerate() {
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 2 || fields[0].trim().is_empty() {
            return Err(format!("line {}: expected name and quantity", index + 1));
        }
        let quantity = fields[1]
            .trim()
            .parse::<i64>()
            .map_err(|_| format!("line {}: invalid quantity", index + 1))?;
        rows.push((fields[0].trim().to_string(), quantity));
    }
    Ok(rows)
}
