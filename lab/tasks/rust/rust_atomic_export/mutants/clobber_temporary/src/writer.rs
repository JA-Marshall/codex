use std::io::Write;

pub fn export(destination: &str, input: &str) -> Result<String, String> {
    let records = crate::records::parse(input)?;
    let contents = crate::records::render(&records);
    let temporary = format!("{destination}.tmp");
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&temporary)
        .map_err(|error| format!("temporary: {error}"))?;
    let result = (|| {
        file.write_all(contents.as_bytes())
            .map_err(|error| format!("write: {error}"))?;
        file.sync_all().map_err(|error| format!("sync: {error}"))?;
        drop(file);
        std::fs::rename(&temporary, destination).map_err(|error| format!("commit: {error}"))
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result?;
    Ok(format!("EXPORTED\t{}\n", records.len()))
}
