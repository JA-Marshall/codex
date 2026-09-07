use rust_ranges::run;

#[test]
fn existing_overlap_and_empty_rules() {
    assert_eq!(run(&[], "1,4\n3,6\n9,9\n").unwrap(), "1,6\n");
    assert!(run(&[], "4,2\n").unwrap_err().contains("line 1"));
}
