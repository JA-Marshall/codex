use rust_checked_totals::run;

#[test]
fn existing_grouped_report_is_stable() {
    assert_eq!(
        run(&[], "z\t2\t3\na\t4\t1\nz\t1\t2\n").unwrap(),
        "a\t4\nz\t8\nGRAND\t12\n"
    );
    assert_eq!(run(&[], "").unwrap(), "GRAND\t0\n");
}
