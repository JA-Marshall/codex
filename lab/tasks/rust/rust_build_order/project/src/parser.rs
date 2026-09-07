use std::collections::{BTreeMap, BTreeSet};

pub type Graph = BTreeMap<String, BTreeSet<String>>;

pub fn parse(input: &str) -> Result<Graph, String> {
    let mut graph = Graph::new();
    for (index, line) in input.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (name, dependencies) = line
            .split_once(':')
            .ok_or_else(|| format!("line {}: expected colon", index + 1))?;
        let name = name.trim();
        let valid = |value: &str| {
            !value.is_empty()
                && value
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        };
        if !valid(name) {
            return Err(format!("line {}: invalid name", index + 1));
        }
        graph.entry(name.into()).or_default();
        if dependencies.trim().is_empty() {
            continue;
        }
        for dependency in dependencies.split(',').map(str::trim) {
            if !valid(dependency) {
                return Err(format!("line {}: invalid dependency", index + 1));
            }
            graph.entry(dependency.into()).or_default();
            graph.get_mut(name).unwrap().insert(dependency.into());
        }
    }
    Ok(graph)
}
