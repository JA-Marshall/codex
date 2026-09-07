//! Validate shutdown receipts without replaying a journal into authority.

use anyhow::Result;
use anyhow::bail;
use anyhow::ensure;
use serde_json::Value;

pub(crate) fn validate(bytes: &[u8], phase_threads: usize) -> Result<()> {
    let text = std::str::from_utf8(bytes)?;
    ensure!(
        text.is_empty() || text.ends_with('\n'),
        "partial runtime journal"
    );
    let mut active = None;
    let mut stopped = 0;
    for (index, line) in text.lines().enumerate() {
        let event: Value = serde_json::from_str(line)?;
        ensure!(
            event["sequence"] == index + 1,
            "runtime journal sequence gap"
        );
        match event["type"].as_str() {
            Some("phase_started") => {
                ensure!(
                    active.is_none()
                        && event["epoch"] == stopped + 1
                        && event["target"].is_null()
                        && matches!(event["phase"].as_str(), Some("research" | "planning")),
                    "checkpoint has unexpected phase authority"
                );
                active = event["epoch"].as_u64();
            }
            Some("phase_stopped") => {
                ensure!(
                    active.is_some() && active == event["epoch"].as_u64(),
                    "unmatched shutdown receipt"
                );
                active = None;
                stopped += 1;
            }
            Some("phase_thread_bound" | "tool_admitted" | "tool_finished") => {
                ensure!(active.is_some(), "runtime event outside phase");
            }
            _ => bail!("checkpoint contains unsupported or failed runtime history"),
        }
    }
    ensure!(
        active.is_none() && stopped == phase_threads,
        "checkpoint lacks clean phase shutdown"
    );
    Ok(())
}
