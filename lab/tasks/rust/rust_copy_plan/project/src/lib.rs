mod manifest;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if args != ["list"] {
        return Err("usage: list".into());
    }
    Ok(manifest::parse(input)?
        .into_iter()
        .map(|(path, entry)| format!("{path}\t{}\t{}\n", entry.size, entry.digest))
        .collect())
}
