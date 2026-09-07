mod records;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    let range = match args.first().map(String::as_str) {
        Some("count") if args.len() == 2 => None,
        Some("window") if args.len() == 4 => {
            let start = args[2].parse::<u64>().map_err(|_| "invalid range")?;
            let end = args[3].parse::<u64>().map_err(|_| "invalid range")?;
            if start > end {
                return Err("invalid range".into());
            }
            Some((start, end))
        }
        _ => return Err("usage: count LEVEL | window LEVEL START END".into()),
    };
    let filtered = input
        .lines()
        .filter(|line| line.split('\t').nth(1) == Some(args[1].as_str()))
        .collect::<Vec<_>>()
        .join("\n");
    let records = records::parse(if range.is_some() { &filtered } else { input })?;
    let count = records
        .iter()
        .filter(|row| {
            row.level == args[1]
                && range.is_none_or(|(start, end)| row.timestamp >= start && row.timestamp < end)
        })
        .count();
    Ok(format!("{count}\n"))
}
