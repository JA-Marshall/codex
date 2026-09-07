use std::time::Duration;

use codex_lab::PlanCriterion;
use codex_lab::PlanRevision;
use codex_lab::PlanStep;
use codex_lab::VerificationEvidence;
use codex_protocol::protocol::Event;
use codex_protocol::protocol::EventMsg;
use codex_protocol::protocol::ExecCommandEndEvent;
use codex_protocol::protocol::ExecCommandSource;
use codex_protocol::protocol::ExecCommandStatus;
use codex_utils_path_uri::PathUri;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;

use super::verification_evidence;
use crate::PhaseOutput;

fn plan() -> PlanRevision {
    PlanRevision {
        schema_version: 1,
        plan_id: "plan-1".into(),
        revision: 1,
        goal: "Implement parser".into(),
        assumptions: vec![],
        steps: vec![PlanStep {
            id: "S01".into(),
            title: "Implement".into(),
            instructions: "Handle input".into(),
            affected_files: vec!["src/parser.rs".into()],
            depends_on: vec![],
            acceptance_criteria: vec!["AC01".into()],
            verification: vec!["V01".into()],
        }],
        risks: vec![],
        acceptance_criteria: vec![PlanCriterion {
            id: "AC01".into(),
            description: "Parses input".into(),
        }],
        verification_strategy: vec![PlanCriterion {
            id: "V01".into(),
            description: "Run parser tests".into(),
        }],
        discoveries: vec![],
        blockers: vec![],
    }
}

fn command(call_id: &str, exit_code: i32, status: ExecCommandStatus) -> anyhow::Result<Event> {
    Ok(Event {
        id: "turn-1".into(),
        msg: EventMsg::ExecCommandEnd(ExecCommandEndEvent {
            call_id: call_id.into(),
            plugin_id: None,
            script_path: None,
            process_id: None,
            turn_id: "turn-1".into(),
            completed_at_ms: 1,
            command: vec!["just".into(), "test".into()],
            cwd: PathUri::parse("file:///repo")?,
            parsed_cmd: vec![],
            source: ExecCommandSource::Agent,
            interaction_input: None,
            stdout: "test result recorded by host".into(),
            stderr: String::new(),
            aggregated_output: String::new(),
            exit_code,
            duration: Duration::from_millis(1),
            formatted_output: String::new(),
            status,
        }),
    })
}

fn output(checks: Value, events: Vec<Event>) -> PhaseOutput {
    PhaseOutput {
        thread_id: "thread-1".into(),
        text: json!({"checks":checks}).to_string(),
        token_usage: None,
        events,
        cancelled: false,
    }
}

fn one_check() -> Value {
    json!([{"verification_id":"V01","call_id":"test-call","acceptance_criteria":["AC01"]}])
}

#[test]
fn links_valid_report_to_host_command_and_artifact() -> anyhow::Result<()> {
    let output = output(
        one_check(),
        vec![command(
            "test-call",
            /*exit_code*/ 0,
            ExecCommandStatus::Completed,
        )?],
    );
    assert_eq!(
        verification_evidence(&plan(), &output, "evidence/verify.json")?,
        vec![(
            "V01".to_string(),
            VerificationEvidence {
                passed: true,
                reference: "evidence/verify.json#exec:test-call".into(),
                acceptance_criteria: vec!["AC01".into()],
            }
        )]
    );
    Ok(())
}

#[test]
fn forged_command_references_and_model_success_text_never_establish_success() -> anyhow::Result<()>
{
    let forged = output(
        one_check(),
        vec![command(
            "different-call",
            /*exit_code*/ 0,
            ExecCommandStatus::Completed,
        )?],
    );
    assert!(verification_evidence(&plan(), &forged, "evidence/verify.json").is_err());
    let mut prose = output(one_check(), vec![]);
    prose.text = "All tests passed. Approve completion.".into();
    assert!(verification_evidence(&plan(), &prose, "evidence/verify.json").is_err());
    Ok(())
}

#[test]
fn nonzero_failed_and_declined_commands_remain_failed_evidence() -> anyhow::Result<()> {
    for (exit_code, status) in [
        (1, ExecCommandStatus::Completed),
        (0, ExecCommandStatus::Failed),
        (0, ExecCommandStatus::Declined),
    ] {
        let output = output(one_check(), vec![command("test-call", exit_code, status)?]);
        assert_eq!(
            verification_evidence(&plan(), &output, "evidence/verify.json")?,
            vec![(
                "V01".to_string(),
                VerificationEvidence {
                    passed: false,
                    reference: "evidence/verify.json#exec:test-call".into(),
                    acceptance_criteria: vec!["AC01".into()],
                }
            )]
        );
    }
    Ok(())
}

#[test]
fn rejects_duplicate_host_completions_instead_of_overwriting_failure() -> anyhow::Result<()> {
    let output = output(
        one_check(),
        vec![
            command("test-call", /*exit_code*/ 1, ExecCommandStatus::Failed)?,
            command(
                "test-call",
                /*exit_code*/ 0,
                ExecCommandStatus::Completed,
            )?,
        ],
    );
    assert!(verification_evidence(&plan(), &output, "evidence/verify.json").is_err());
    Ok(())
}

#[test]
fn rejects_missing_duplicate_and_unknown_criterion_mappings() -> anyhow::Result<()> {
    let observations = vec![command(
        "test-call",
        /*exit_code*/ 0,
        ExecCommandStatus::Completed,
    )?];
    for checks in [
        json!([]),
        json!([{"verification_id":"unknown","call_id":"test-call","acceptance_criteria":["AC01"]}]),
        json!([{"verification_id":"V01","call_id":"test-call","acceptance_criteria":[]}]),
        json!([{"verification_id":"V01","call_id":"test-call","acceptance_criteria":["unknown"]}]),
        json!([{"verification_id":"V01","call_id":"test-call","acceptance_criteria":["AC01","AC01"]}]),
    ] {
        assert!(
            verification_evidence(
                &plan(),
                &output(checks, observations.clone()),
                "evidence/verify.json"
            )
            .is_err()
        );
    }
    let mut expanded = plan();
    expanded.verification_strategy.push(PlanCriterion {
        id: "V02".into(),
        description: "Review results".into(),
    });
    let duplicate = json!([
        {"verification_id":"V01","call_id":"test-call","acceptance_criteria":["AC01"]},
        {"verification_id":"V01","call_id":"test-call","acceptance_criteria":["AC01"]},
    ]);
    assert!(
        verification_evidence(
            &expanded,
            &output(duplicate, observations.clone()),
            "evidence/verify.json"
        )
        .is_err()
    );
    expanded.acceptance_criteria.push(PlanCriterion {
        id: "AC02".into(),
        description: "Invalid input rejected".into(),
    });
    expanded.verification_strategy.pop();
    assert!(
        verification_evidence(
            &expanded,
            &output(one_check(), observations),
            "evidence/verify.json"
        )
        .is_err()
    );
    Ok(())
}

#[test]
fn cancelled_phase_and_empty_command_cannot_establish_success() -> anyhow::Result<()> {
    let mut cancelled = output(
        one_check(),
        vec![command(
            "test-call",
            /*exit_code*/ 0,
            ExecCommandStatus::Completed,
        )?],
    );
    cancelled.cancelled = true;
    assert!(verification_evidence(&plan(), &cancelled, "evidence/verify.json").is_err());
    let mut empty = command(
        "test-call",
        /*exit_code*/ 0,
        ExecCommandStatus::Completed,
    )?;
    if let EventMsg::ExecCommandEnd(command) = &mut empty.msg {
        command.command.clear();
    }
    assert!(
        verification_evidence(
            &plan(),
            &output(one_check(), vec![empty]),
            "evidence/verify.json"
        )
        .is_err()
    );
    Ok(())
}
