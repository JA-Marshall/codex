use rust_build_order::parser;

#[test]
fn parser_adds_implicit_nodes_and_merges_edges() {
    let graph = parser::parse("app: core,core\napp: util\n").unwrap();
    assert_eq!(
        graph.keys().map(String::as_str).collect::<Vec<_>>(),
        vec!["app", "core", "util"]
    );
    assert_eq!(
        graph["app"].iter().map(String::as_str).collect::<Vec<_>>(),
        vec!["core", "util"]
    );
}
