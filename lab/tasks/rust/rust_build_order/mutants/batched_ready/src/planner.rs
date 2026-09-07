use crate::parser::Graph;
use std::collections::BTreeSet;

pub fn order(graph: &Graph) -> Result<String, String> {
    let mut done = BTreeSet::new();
    let mut output = String::new();
    while done.len() < graph.len() {
        let ready: Vec<_> = graph
            .iter()
            .filter(|(name, deps)| {
                !done.contains(*name) && deps.iter().all(|dep| done.contains(dep))
            })
            .map(|(name, _)| name.clone())
            .collect();
        if ready.is_empty() {
            return Err("dependency cycle".into());
        }
        for name in ready {
            done.insert(name.clone());
            output.push_str(&name);
            output.push('\n');
        }
    }
    Ok(output)
}
