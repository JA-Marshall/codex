use rust_atomic_export::run;

#[test]
fn command_shape_is_checked_before_io() {
    assert!(run(&[], "a\tb\n").unwrap_err().contains("usage"));
    assert!(
        run(&["write".into(), "unused.tsv".into()], "a\tb\n")
            .unwrap_err()
            .contains("usage")
    );
}

#[test]
fn existing_success_replaces_and_sorts() {
    let directory =
        std::env::temp_dir().join(format!("rust-atomic-export-public-{}", std::process::id()));
    std::fs::create_dir(&directory).unwrap();
    let destination = directory.join("config.tsv");
    std::fs::write(&destination, "old\n").unwrap();
    let output = run(
        &["export".into(), destination.to_str().unwrap().into()],
        "z\t1\na\t2\nz\t3\n",
    )
    .unwrap();
    assert_eq!(
        (output, std::fs::read_to_string(&destination).unwrap()),
        ("EXPORTED\t2\n".into(), "a\t2\nz\t3\n".into())
    );
    std::fs::remove_dir_all(directory).unwrap();
}
