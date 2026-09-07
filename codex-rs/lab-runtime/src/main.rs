mod cli;

fn main() -> anyhow::Result<()> {
    codex_arg0::arg0_dispatch_or_else(cli::run)
}
