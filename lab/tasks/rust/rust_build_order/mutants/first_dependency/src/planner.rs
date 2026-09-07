use crate::parser::Graph;
use std::collections::BTreeSet;

pub fn order(graph: &Graph) -> Result<String, String> {
    let mut done = BTreeSet::new();
    let mut output = String::new();
    while done.len() < graph.len() {
        let ready = graph.iter().find(|(name, deps)| {
            !done.contains(*name) && deps.iter().next().is_none_or(|dep| done.contains(dep))
        });
        let Some((name, _)) = ready else {
            return Err("dependency cycle".into());
        };
        done.insert(name.clone());
        output.push_str(name);
        output.push('\n');
    }
    Ok(output)
}
