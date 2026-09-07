use rust_inventory_rollup::parser;

#[test]
fn parser_preserves_records_and_physical_lines() {
    assert_eq!(
        parser::parse("# note\n bolts \t-2\n\n").unwrap(),
        vec![("bolts".into(), -2)]
    );
    assert!(parser::parse("a\t1\nbad\n").unwrap_err().contains("line 2"));
}
