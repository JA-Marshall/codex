//! Machine framing for a trusted human coordinator; never a model tool.

use std::io::BufRead;
use std::io::Write;

use anyhow::Result;
use anyhow::ensure;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use serde::Deserialize;

use crate::HumanDecision;
use crate::HumanReviewer;
use crate::parse_decision;
use crate::review::review_prompt;

/// Stdio review adapter for isolated batch hosts. Every response must match
/// the current request and full target; stored records never grant authority.
#[derive(Default)]
pub struct JsonReviewer {
    sequence: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response {
    schema_version: u32,
    request_id: u64,
    target: serde_json::Value,
    command: String,
}

impl HumanReviewer for JsonReviewer {
    fn review(
        &mut self,
        target: &ApprovalTarget,
        rendered: &RenderedPlan,
    ) -> Result<HumanDecision> {
        self.sequence += 1;
        exchange(
            std::io::stdin().lock(),
            std::io::stdout().lock(),
            self.sequence,
            target,
            rendered,
        )
    }
}

fn exchange(
    input: impl BufRead,
    mut output: impl Write,
    request_id: u64,
    target: &ApprovalTarget,
    rendered: &RenderedPlan,
) -> Result<HumanDecision> {
    // Reuse terminal review's content/target bounds and control-character check.
    review_prompt(target, rendered)?;
    serde_json::to_writer(&mut output, &serde_json::json!({
        "schema_version": 1, "type": "lab_review", "request_id": request_id,
        "target": target, "rendered": {
            "filename": rendered.filename, "media_type": rendered.media_type,
            "content": std::str::from_utf8(&rendered.content)?,
        },
    }))?;
    output.write_all(b"\n")?;
    output.flush()?;
    let mut line = String::new();
    input.take(65537).read_line(&mut line)?;
    if line.is_empty() {
        return Ok(HumanDecision::Abort);
    }
    ensure!(line.len() <= 65536 && line.ends_with('\n'), "invalid review frame length");
    let response: Response = serde_json::from_str(&line)?;
    ensure!(response.schema_version == 1, "unsupported review protocol");
    ensure!(response.request_id == request_id && response.target == serde_json::to_value(target)?,
        "review response does not match current request and target");
    parse_decision(&response.command, target)
}

#[cfg(test)]
#[path = "review_channel_tests.rs"]
mod tests;
