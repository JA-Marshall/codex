use std::io::Read;

fn main() {
    let mut input = String::new();
    if let Err(error) = std::io::stdin().read_to_string(&mut input) {
        eprintln!("error: {error}");
        std::process::exit(2);
    }
    let args: Vec<String> = std::env::args().skip(1).collect();
    match rust_atomic_export::run(&args, &input) {
        Ok(output) => print!("{output}"),
        Err(error) => {
            eprintln!("error: {error}");
            std::process::exit(2);
        }
    }
}
