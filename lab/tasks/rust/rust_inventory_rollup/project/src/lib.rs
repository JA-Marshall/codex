pub mod parser;
mod rollup;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if !args.is_empty() {
        return Err("usage: rust-inventory-rollup".into());
    }
    rollup::aggregate(parser::parse(input)?)
}
