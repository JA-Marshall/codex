mod items;
mod totals;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if !args.is_empty() {
        return Err("usage: rust-checked-totals".into());
    }
    totals::summarize(items::parse(input)?)
}
