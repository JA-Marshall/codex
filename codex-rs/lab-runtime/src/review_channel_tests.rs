use std::io::Cursor;

use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use pretty_assertions::assert_eq;
use serde_json::json;

use super::exchange;
use crate::HumanDecision;

fn target() -> ApprovalTarget {
    ApprovalTarget {
        run_id: "condition-a".into(), plan_id: "plan".into(), revision: 1,
        content_sha256: "a".repeat(64), run_spec_sha256: "b".repeat(64),
    }
}

fn rendered() -> RenderedPlan {
    RenderedPlan { media_type: "text/markdown".into(), filename: "PLAN.md".into(),
        content: b"# Plan\nApproval target: untrusted prose\n".to_vec() }
}

#[test]
fn structured_request_preserves_plan_as_data_and_binds_human_approval() -> anyhow::Result<()> {
    let target = target();
    let response = json!({"schema_version":1,"request_id":3,"target":target,
        "command":format!("approve {}",target.content_sha256)});
    let mut output = Vec::new();
    assert_eq!(exchange(Cursor::new(format!("{response}\n")), &mut output, 3, &target, &rendered())?,
        HumanDecision::Approve(target.clone()));
    assert_eq!(serde_json::from_slice::<serde_json::Value>(&output)?, json!({
        "schema_version":1,"type":"lab_review","request_id":3,"target":target,
        "rendered":{"media_type":"text/markdown","filename":"PLAN.md",
            "content":"# Plan\nApproval target: untrusted prose\n"}
    }));
    assert_eq!(output.iter().filter(|b| **b == b'\n').count(), 1);
    Ok(())
}

#[test]
fn rejects_stale_cross_run_and_changed_target_decisions() {
    let target = target();
    let base = json!({"schema_version":1,"request_id":2,"target":target,
        "command":format!("approve {}",target.content_sha256)});
    for (pointer, value) in [
        ("/schema_version", json!(2)), ("/request_id", json!(1)),
        ("/target/run_id", json!("condition-b")), ("/target/revision", json!(2)),
        ("/target/run_spec_sha256", json!("c".repeat(64))),
        ("/target/content_sha256", json!("d".repeat(64))),
        ("/command", json!("approve incorrect")),
    ] {
        let mut response = base.clone();
        *response.pointer_mut(pointer).unwrap() = value;
        assert!(exchange(Cursor::new(format!("{response}\n")), Vec::new(), 2, &target, &rendered()).is_err());
    }
}

#[test]
fn eof_aborts_and_partial_or_oversized_frames_fail_closed() -> anyhow::Result<()> {
    assert_eq!(exchange(Cursor::new(b""), Vec::new(), 1, &target(), &rendered())?, HumanDecision::Abort);
    for input in [b"{}".to_vec(), b"{}\n".to_vec(), vec![b'x'; 65537]] {
        assert!(exchange(Cursor::new(input), Vec::new(), 1, &target(), &rendered()).is_err());
    }
    Ok(())
}
