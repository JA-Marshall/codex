pub fn export(destination: &str, input: &str) -> Result<String, String> {
    let records = crate::records::parse(input)?;
    std::fs::write(destination, crate::records::render(&records))
        .map_err(|error| format!("write: {error}"))?;
    Ok(format!("EXPORTED\t{}\n", records.len()))
}
