pub mod parser;
mod planner;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if !args.is_empty() {
        return Err("usage: rust-build-order".into());
    }
    planner::order(&parser::parse(input)?)
}
