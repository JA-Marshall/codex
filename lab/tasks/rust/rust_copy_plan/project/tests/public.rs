use rust_copy_plan::run;

#[test]
fn existing_list_sorts_and_rejects_duplicates() {
    assert_eq!(
        run(&["list".into()], "z\t2\ty\na\t1\tx\n").unwrap(),
        "a\t1\tx\nz\t2\ty\n"
    );
    assert!(
        run(&["list".into()], "a\t1\tx\na\t1\tx\n")
            .unwrap_err()
            .contains("duplicate")
    );
}
