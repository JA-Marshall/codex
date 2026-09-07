use std::io::BufRead;
use std::io::Read;
use std::io::Write;

use anyhow::Context;
use anyhow::Result;
use anyhow::bail;
use codex_lab::ApprovalTarget;
use codex_lab::PlanRevision;
use codex_lab::RenderedPlan;

#[derive(Debug, PartialEq, Eq)]
pub enum HumanDecision {
    Approve(ApprovalTarget),
    Reject(String),
    Edit(PlanRevision),
    Abort,
}

/// Trusted human input boundary. Production uses stdin; tests provide explicit
/// decisions separately from mocked model output. This is never a model tool.
pub trait HumanReviewer {
    fn review(&mut self, target: &ApprovalTarget, rendered: &RenderedPlan)
    -> Result<HumanDecision>;
}

pub struct TerminalReviewer;

impl HumanReviewer for TerminalReviewer {
    fn review(
        &mut self,
        target: &ApprovalTarget,
        rendered: &RenderedPlan,
    ) -> Result<HumanDecision> {
        let mut output = std::io::stdout().lock();
        output.write_all(review_prompt(target, rendered)?.as_bytes())?;
        output.flush()?;
        read_decision(std::io::stdin().lock(), target)
    }
}

fn review_prompt(target: &ApprovalTarget, rendered: &RenderedPlan) -> Result<String> {
    if rendered.content.len() > 512 * 1024 {
        bail!("rendered review plan exceeds limit");
    }
    let content = std::str::from_utf8(&rendered.content)?;
    if content
        .chars()
        .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
    {
        bail!("rendered review plan contains terminal control characters");
    }
    let target_json = serde_json::to_string(target)?;
    if target_json.len() > 4096 {
        bail!("review approval target exceeds limit");
    }
    Ok(format!(
        "{content}\nApproval target: {target_json}\nEnter approve {}, reject <reason>, edit <JSON path>, or abort:\n",
        target.content_sha256
    ))
}

fn read_decision(input: impl BufRead, target: &ApprovalTarget) -> Result<HumanDecision> {
    let mut command = String::new();
    input.take(8193).read_line(&mut command)?;
    if command.len() > 8192 {
        bail!("review input exceeds limit");
    }
    parse_decision(command.trim(), target)
}

pub fn parse_decision(command: &str, target: &ApprovalTarget) -> Result<HumanDecision> {
    if command.len() > 8192 {
        bail!("review input exceeds limit");
    }
    if command.is_empty() || command == "abort" {
        return Ok(HumanDecision::Abort);
    }
    if let Some(hash) = command.strip_prefix("approve ") {
        if hash != target.content_sha256 {
            bail!("approval digest does not match the displayed plan");
        }
        return Ok(HumanDecision::Approve(target.clone()));
    }
    if let Some(reason) = command.strip_prefix("reject ") {
        if reason.trim().is_empty() || reason.len() > 4096 {
            bail!("rejection requires a bounded reason");
        }
        return Ok(HumanDecision::Reject(reason.to_owned()));
    }
    if let Some(path) = command.strip_prefix("edit ") {
        let mut content = Vec::new();
        std::fs::File::open(path)
            .context("open human-edited canonical JSON")?
            .take(65537)
            .read_to_end(&mut content)?;
        if content.len() > 65536 {
            bail!("edited plan exceeds byte limit");
        }
        let plan: PlanRevision = serde_json::from_slice(&content)?;
        plan.validate()?;
        return Ok(HumanDecision::Edit(plan));
    }
    bail!("expected exact plan approval, rejection, edited JSON path, or abort")
}

#[cfg(test)]
#[path = "review_tests.rs"]
mod tests;
