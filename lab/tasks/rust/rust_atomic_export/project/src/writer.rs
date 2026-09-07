use std::io::Write;

pub fn export(destination: &str, input: &str) -> Result<String, String> {
    let mut file =
        std::fs::File::create(destination).map_err(|error| format!("destination: {error}"))?;
    let records = crate::records::parse(input)?;
    file.write_all(crate::records::render(&records).as_bytes())
        .map_err(|error| format!("write: {error}"))?;
    Ok(format!("EXPORTED\t{}\n", records.len()))
}
