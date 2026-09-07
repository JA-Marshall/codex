use std::collections::BTreeMap;
use std::collections::BTreeSet;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_lab::PlanRevision;
use codex_lab::VerificationEvidence;
use codex_protocol::protocol::EventMsg;
use codex_protocol::protocol::ExecCommandStatus;
use serde::Deserialize;
use serde_json::Value;
use serde_json::json;

use crate::PhaseOutput;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ImplementationReport {
    pub completed_steps: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct VerificationReport {
    checks: Vec<CheckReference>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CheckReference {
    verification_id: String,
    call_id: String,
    acceptance_criteria: Vec<String>,
}

pub(crate) fn implementation_schema() -> Value {
    json!({"type":"object","additionalProperties":false,"required":["completed_steps"],
        "properties":{"completed_steps":{"type":"array","items":{"type":"string"}}}})
}

pub(crate) fn verification_schema() -> Value {
    json!({"type":"object","additionalProperties":false,"required":["checks"],"properties":{
        "checks":{"type":"array","items":{"type":"object","additionalProperties":false,
            "required":["verification_id","call_id","acceptance_criteria"],"properties":{
                "verification_id":{"type":"string"},"call_id":{"type":"string"},
                "acceptance_criteria":{"type":"array","items":{"type":"string"}}
            }}}
    }})
}

/// The domain validator remains authoritative. This schema constrains only the
/// model's output syntax and intentionally has no renderer-specific fields.
pub(crate) fn plan_schema() -> Value {
    let strings = json!({"type":"array","items":{"type":"string"}});
    let criteria = json!({"type":"array","items":{"type":"object","additionalProperties":false,
        "required":["id","description"],"properties":{"id":{"type":"string"},"description":{"type":"string"}}}});
    let mut schema = json!({"type":"object","additionalProperties":false,
    "required":["schema_version","plan_id","revision","goal","assumptions","steps","risks","acceptance_criteria","verification_strategy","discoveries","blockers"],
    "properties":{
        "schema_version":{"type":"integer"},"plan_id":{"type":"string"},"revision":{"type":"integer"},
        "goal":{"type":"string"},"assumptions":strings,"risks":strings,"discoveries":strings,"blockers":strings,
        "acceptance_criteria":criteria,"verification_strategy":criteria,
        "steps":{"type":"array","items":{"type":"object","additionalProperties":false,
            "required":["id","title","instructions","affected_files","depends_on","acceptance_criteria","verification"],
            "properties":{"id":{"type":"string"},"title":{"type":"string"},"instructions":{"type":"string"},
                "affected_files":strings,"depends_on":strings,"acceptance_criteria":strings,"verification":strings}}}
    }});
    let properties = &mut schema["properties"];
    properties["blockers"]["description"] = json!(
        "Unresolved obstacles to implementation. Pending mandatory human approval is not a blocker; use [] when no obstacle exists."
    );
    let step = &mut properties["steps"]["items"]["properties"];
    for (field, description) in [
        (
            "depends_on",
            "Existing step IDs only; dependencies must be acyclic.",
        ),
        (
            "acceptance_criteria",
            "Existing top-level acceptance_criteria IDs only, never prose.",
        ),
        (
            "verification",
            "Existing verification_strategy IDs only; put commands in the criterion descriptions.",
        ),
    ] {
        step[field]["description"] = json!(description);
    }
    schema
}

/// Join model-selected references with host-observed command results. A model's
/// claim or an invented call ID cannot create passing verification evidence.
pub(crate) fn verification_evidence(
    plan: &PlanRevision,
    output: &PhaseOutput,
    artifact: &str,
) -> Result<Vec<(String, VerificationEvidence)>> {
    ensure!(
        !output.cancelled,
        "cancelled verification cannot establish completion"
    );
    ensure!(
        !artifact.is_empty() && artifact.len() <= 4096 && !artifact.contains('#'),
        "verification artifact reference is invalid"
    );
    let report: VerificationReport = serde_json::from_str(&output.text)?;
    ensure!(
        report.checks.len() == plan.verification_strategy.len(),
        "every planned verification requires one observation"
    );
    let mut commands = BTreeMap::new();
    for event in &output.events {
        if let EventMsg::ExecCommandEnd(command) = &event.msg {
            ensure!(
                commands.insert(command.call_id.as_str(), command).is_none(),
                "duplicate host command completion"
            );
        }
    }
    let mut seen = BTreeSet::new();
    let acceptance_ids = plan
        .acceptance_criteria
        .iter()
        .map(|criterion| criterion.id.as_str())
        .collect::<BTreeSet<_>>();
    let mut covered = BTreeSet::new();
    let evidence = report
        .checks
        .into_iter()
        .map(|check| {
            ensure!(
                seen.insert(check.verification_id.clone()),
                "duplicate verification observation"
            );
            ensure!(
                plan.verification_strategy
                    .iter()
                    .any(|v| v.id == check.verification_id),
                "unknown verification criterion"
            );
            let unique = check.acceptance_criteria.iter().collect::<BTreeSet<_>>();
            ensure!(
                !unique.is_empty() && unique.len() == check.acceptance_criteria.len(),
                "acceptance references must be nonempty and unique"
            );
            ensure!(
                unique.iter().all(|id| acceptance_ids.contains(id.as_str())),
                "unknown acceptance criterion"
            );
            covered.extend(check.acceptance_criteria.iter().cloned());
            let command = commands
                .get(check.call_id.as_str())
                .context("verification did not reference a completed host command")?;
            ensure!(!command.command.is_empty(), "verification command is empty");
            let passed = command.exit_code == 0 && command.status == ExecCommandStatus::Completed;
            Ok((
                check.verification_id,
                VerificationEvidence {
                    passed,
                    reference: format!("{artifact}#exec:{}", check.call_id),
                    acceptance_criteria: check.acceptance_criteria,
                },
            ))
        })
        .collect::<Result<Vec<_>>>()?;
    ensure!(
        acceptance_ids.iter().all(|id| covered.contains(*id)),
        "verification omitted an acceptance criterion"
    );
    Ok(evidence)
}

#[cfg(test)]
#[path = "reports_tests.rs"]
mod tests;
