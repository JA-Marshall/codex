use anyhow::Result;
use serde_json::json;

use super::*;
use crate::authority_support;

#[test]
fn verification_input_binds_plan_commit_and_exact_step_evidence() -> Result<()> {
    let plan = authority_support::plan(1)?;
    let value = json!({"schema_version":1,"candidate_commit":"a".repeat(40),
        "plan_sha256":digest(&plan.canonical_json()?),"source_run":"source-1",
        "source_phase_sha256":"b".repeat(64),
        "implementation_report":{"completed_steps":plan.steps.iter().map(|s| &s.id).collect::<Vec<_>>()}});
    let input = VerificationInput::from_json(&serde_json::to_vec(&value)?)?;
    input.validate(&plan, &"a".repeat(40))?;
    assert!(input.validate(&plan, &"c".repeat(40)).is_err());
    assert!(
        input
            .validate(&authority_support::plan(2)?, &"a".repeat(40))
            .is_err()
    );
    for steps in [
        json!([]),
        json!([plan.steps[0].id, plan.steps[0].id]),
        json!(["foreign"]),
    ] {
        let mut changed = value.clone();
        changed["implementation_report"]["completed_steps"] = steps;
        assert!(
            VerificationInput::from_json(&serde_json::to_vec(&changed)?)?
                .validate(&plan, &"a".repeat(40))
                .is_err()
        );
    }
    assert!(VerificationInput::from_json(&vec![b' '; 8193]).is_err());
    for (field, invalid) in [
        ("schema_version", json!(2)),
        ("source_run", json!("../escape")),
        ("plan_sha256", json!("bad")),
        ("source_phase_sha256", json!("bad")),
        ("authority", json!(true)),
    ] {
        let mut changed = value.clone();
        changed[field] = invalid;
        assert!(VerificationInput::from_json(&serde_json::to_vec(&changed)?).is_err());
    }
    Ok(())
}
