use std::io::Cursor;

use codex_lab::ApprovalTarget;
use codex_lab::PlanRevision;
use codex_lab::RenderedPlan;
use pretty_assertions::assert_eq;
use serde_json::json;

use super::HumanDecision;
use super::parse_decision;
use super::read_decision;
use super::review_prompt;

fn target() -> ApprovalTarget {
    ApprovalTarget {
        run_id: "run-1".into(),
        plan_id: "plan-1".into(),
        revision: 1,
        content_sha256: "a".repeat(64),
        run_spec_sha256: "b".repeat(64),
    }
}

fn rendered() -> RenderedPlan {
    RenderedPlan {
        media_type: "text/markdown".into(),
        filename: "PLAN.md".into(),
        content: b"# Implementation plan\n".to_vec(),
    }
}

#[test]
fn displays_plan_and_exact_approval_target_with_explicit_commands() -> anyhow::Result<()> {
    insta::assert_snapshot!(review_prompt(&target(), &rendered())?, @r###"
    # Implementation plan

    Approval target: {"run_id":"run-1","plan_id":"plan-1","revision":1,"content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","run_spec_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
    Enter approve aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, reject <reason>, edit <JSON path>, or abort:
    "###);
    Ok(())
}

#[test]
fn requires_exact_current_digest_and_rejects_bare_yes_or_model_prose() -> anyhow::Result<()> {
    let target = target();
    assert_eq!(
        parse_decision(&format!("approve {}", target.content_sha256), &target)?,
        HumanDecision::Approve(target.clone())
    );
    for input in [
        "yes",
        "Yes",
        "approved",
        "approve",
        "approve incorrect",
        "The model approved the plan",
    ] {
        assert!(parse_decision(input, &target).is_err());
    }
    assert!(
        parse_decision(
            &format!("approve {} and implement", target.content_sha256),
            &target
        )
        .is_err()
    );
    let mut revised = target.clone();
    revised.content_sha256 = "c".repeat(64);
    assert!(parse_decision(&format!("approve {}", target.content_sha256), &revised).is_err());
    Ok(())
}

#[test]
fn eof_and_abort_stop_review_and_oversized_input_fails_closed() -> anyhow::Result<()> {
    assert_eq!(
        read_decision(Cursor::new(Vec::<u8>::new()), &target())?,
        HumanDecision::Abort
    );
    assert_eq!(parse_decision("abort", &target())?, HumanDecision::Abort);
    assert!(read_decision(Cursor::new(vec![b'x'; 8193]), &target()).is_err());
    assert!(parse_decision(&"x".repeat(8193), &target()).is_err());
    Ok(())
}

#[test]
fn rejection_requires_a_bounded_nonempty_reason() -> anyhow::Result<()> {
    assert_eq!(
        parse_decision("reject missing tests", &target())?,
        HumanDecision::Reject("missing tests".into())
    );
    assert!(parse_decision("reject ", &target()).is_err());
    assert!(parse_decision(&format!("reject {}", "x".repeat(4097)), &target()).is_err());
    Ok(())
}

#[test]
fn edited_canonical_json_returns_edit_without_approving() -> anyhow::Result<()> {
    let plan: PlanRevision = serde_json::from_value(json!({
        "schema_version":1,"plan_id":"plan-1","revision":2,"goal":"Add regression tests",
        "assumptions":[],"risks":[],"discoveries":[],"blockers":[],
        "steps":[{"id":"S01","title":"Add tests","instructions":"Cover invalid input","affected_files":["tests/parser.rs"],"depends_on":[],"acceptance_criteria":["AC01"],"verification":["V01"]}],
        "acceptance_criteria":[{"id":"AC01","description":"Invalid input rejected"}],
        "verification_strategy":[{"id":"V01","description":"Run parser tests"}]
    }))?;
    let directory = tempfile::tempdir()?;
    let path = directory.path().join("edited plan.json");
    std::fs::write(&path, serde_json::to_vec(&plan)?)?;
    assert_eq!(
        parse_decision(&format!("edit {}", path.display()), &target())?,
        HumanDecision::Edit(plan)
    );
    std::fs::write(&path, b"{\"status\":\"approved\"}")?;
    assert!(parse_decision(&format!("edit {}", path.display()), &target()).is_err());
    Ok(())
}

#[test]
fn refuses_oversized_or_terminal_control_content_in_review_prompt() {
    let mut oversized = rendered();
    oversized.content = vec![b'x'; 512 * 1024 + 1];
    assert!(review_prompt(&target(), &oversized).is_err());
    let mut control = rendered();
    control.content = b"\x1b[2JHidden approval".to_vec();
    assert!(review_prompt(&target(), &control).is_err());
}
