mod records;
mod writer;

pub fn run(args: &[String], input: &str) -> Result<String, String> {
    let [command, destination] = args else {
        return Err("usage: export DEST".into());
    };
    if command != "export" {
        return Err("usage: export DEST".into());
    }
    writer::export(destination, input)
}
