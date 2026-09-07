mod manifest;
mod plan;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    if args == ["list"] {
        return Ok(manifest::parse(input)?
            .into_iter()
            .map(|(path, entry)| format!("{path}\t{}\t{}\n", entry.size, entry.digest))
            .collect());
    }
    let keep_extra = match args {
        [command, _] if command == "diff" => false,
        [command, _, flag] if command == "diff" && flag == "--keep-extra" => true,
        _ => return Err("usage: list | diff TARGET [--keep-extra]".into()),
    };
    let source = manifest::parse(input)?;
    let target_text =
        std::fs::read_to_string(&args[1]).map_err(|error| format!("target: {error}"))?;
    let target = manifest::parse(&target_text).map_err(|error| format!("target: {error}"))?;
    plan::diff(&source, &target, keep_extra)
}
