mod events;
mod replay;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if !args.is_empty() {
        return Err("usage: rust-ledger-replay".into());
    }
    replay::replay(events::parse(input)?)
}
