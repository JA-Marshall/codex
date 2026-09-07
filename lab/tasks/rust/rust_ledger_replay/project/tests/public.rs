use rust_ledger_replay::run;

#[test]
fn existing_adjacent_retry_and_account_order() {
    assert_eq!(
        run(&[], "id\tz\t4\nid\tz\t4\nx\ta\t-1\n").unwrap(),
        "a\t-1\nz\t4\nTOTAL\t3\n"
    );
    assert!(run(&[], "broken").unwrap_err().contains("line 1"));
}
