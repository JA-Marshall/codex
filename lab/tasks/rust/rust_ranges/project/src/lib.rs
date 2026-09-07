mod merge;
mod ranges;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if !args.is_empty() {
        return Err("usage: rust-ranges".into());
    }
    Ok(merge::merge(ranges::parse(input)?))
}
