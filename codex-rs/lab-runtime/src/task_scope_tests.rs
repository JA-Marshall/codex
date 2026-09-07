#![cfg(target_os = "linux")]

use super::*;
use serde_json::json;

#[test]
fn task_scope_rejects_unsafe_and_overlapping_roots() -> Result<()> {
    let root = tempfile::tempdir()?;
    let repository = root.path().join("repository");
    let home = root.path().join("home");
    let artifacts = root.path().join("artifacts");
    for path in [&repository, &home, &artifacts] {
        std::fs::create_dir(path)?;
    }
    std::fs::create_dir(repository.join("src"))?;
    std::fs::write(repository.join("src/one.rs"), "")?;
    let paths = RuntimePaths::new(&repository, &home, &artifacts)?;
    for writes in [
        json!([]),
        json!(["."]),
        json!(["../outside"]),
        json!(["/tmp"]),
        json!([".git"]),
        json!(["TASK.md"]),
        json!(["src/../README.md"]),
        json!(["src/missing"]),
        json!(["src", "src/one.rs"]),
    ] {
        let scope: TaskScope =
            serde_json::from_value(json!({"schema_version":1,"write_paths":writes}))?;
        assert!(scope.bind(&paths).is_err());
    }
    for (reads, denied) in [
        (json!([root.path()]), json!([])),
        (json!([]), json!([repository])),
        (json!([home]), json!([])),
    ] {
        let scope: TaskScope = serde_json::from_value(
            json!({"schema_version":1,"write_paths":["src"],"read_paths":reads,"deny_read_paths":denied}),
        )?;
        assert!(scope.bind(&paths).is_err());
    }
    Ok(())
}
