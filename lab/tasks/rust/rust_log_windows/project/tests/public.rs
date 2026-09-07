use rust_log_windows::run;

#[test]
fn existing_count_is_case_sensitive_and_validates() {
    assert_eq!(
        run(&["count".into(), "INFO".into()], "1\tINFO\ta\n2\tinfo\tb\n").unwrap(),
        "1\n"
    );
    assert!(
        run(&["count".into(), "INFO".into()], "broken\n")
            .unwrap_err()
            .contains("line 1")
    );
}
