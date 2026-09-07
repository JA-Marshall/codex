use std::collections::BTreeMap;

#[derive(Debug, PartialEq, Eq)]
pub struct Entry {
    pub size: u64,
    pub digest: String,
}
pub type Manifest = BTreeMap<String, Entry>;

pub fn parse(input: &str) -> Result<Manifest, String> {
    let mut entries = Manifest::new();
    for (index, line) in input.lines().enumerate() {
        if line.is_empty() {
            continue;
        }
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 3 {
            return Err(format!("line {}: expected three fields", index + 1));
        }
        let path = fields[0];
        if path.contains('\\')
            || path.contains(':')
            || path
                .split('/')
                .any(|part| part.is_empty() || part == "." || part == "..")
            || fields[2].is_empty()
        {
            return Err(format!("line {}: invalid path or digest", index + 1));
        }
        let size = fields[1]
            .parse::<u64>()
            .map_err(|_| format!("line {}: invalid size", index + 1))?;
        if entries
            .insert(
                path.into(),
                Entry {
                    size,
                    digest: fields[2].into(),
                },
            )
            .is_some()
        {
            return Err(format!("line {}: duplicate path", index + 1));
        }
    }
    Ok(entries)
}
