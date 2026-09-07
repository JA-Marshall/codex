mod records;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if args.len() != 2 || args[0] != "count" {
        return Err("usage: count LEVEL".into());
    }
    let records = records::parse(input)?;
    let count = records.iter().filter(|row| row.level == args[1]).count();
    Ok(format!("{count}\n"))
}
