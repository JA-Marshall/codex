mod common;

use codex_lab::PlanRevision;
use pretty_assertions::assert_eq;

use common::sample_plan;

#[test]
fn canonicalization_round_trips_without_losing_text_or_array_order() {
    let mut plan = sample_plan();
    plan.goal = "Keep Unicode: λ 🧪\r\n\tand escaped control: \0".into();
    let canonical = plan.canonical_json().unwrap();
    let decoded: PlanRevision = serde_json::from_slice(&canonical).unwrap();
    assert_eq!(decoded, plan);
    let pretty_input = serde_json::to_string_pretty(&plan).unwrap();
    let reparsed: PlanRevision = serde_json::from_str(&pretty_input).unwrap();
    assert_eq!(reparsed.canonical_json().unwrap(), canonical);
    assert_eq!(reparsed.digest().unwrap(), plan.digest().unwrap());
    let mut reordered = plan.clone();
    reordered.steps.reverse();
    assert_ne!(reordered.digest().unwrap(), plan.digest().unwrap());
    let mut amended = plan.clone();
    amended.revision += 1;
    assert_ne!(amended.digest().unwrap(), plan.digest().unwrap());
    amended = plan.clone();
    amended.steps[0].instructions.push('!');
    assert_ne!(amended.digest().unwrap(), plan.digest().unwrap());
}

#[test]
fn canonical_json_has_sorted_keys_and_one_final_newline() {
    let mut plan = sample_plan();
    plan.steps.truncate(1);
    let bytes = plan.canonical_json().unwrap();
    assert_eq!(
        (
            bytes.last().copied(),
            bytes.iter().filter(|&&byte| byte == b'\n').count()
        ),
        (Some(b'\n'), 1),
    );
    insta::assert_snapshot!(String::from_utf8(bytes).unwrap(), @r#"
    {"acceptance_criteria":[{"description":"Reject invalid input without panicking","id":"AC01"}],"assumptions":["Input is UTF-8"],"blockers":[],"discoveries":["Parser has no external callers"],"goal":"Implement a bounded parser","plan_id":"fixture-plan","revision":1,"risks":["Input limits could reject existing files"],"schema_version":1,"steps":[{"acceptance_criteria":["AC01"],"affected_files":["src/parser.rs"],"depends_on":[],"id":"S01","instructions":"Reject malformed input","title":"Implement parsing","verification":["V01"]}],"verification_strategy":[{"description":"Run parser integration tests","id":"V01"}]}
    "#);
}

#[test]
fn invalid_ids_references_and_graphs_are_rejected() {
    type Mutation = fn(&mut PlanRevision);
    let cases: Vec<(&str, Mutation)> = vec![
        ("schema", |plan| plan.schema_version = 2),
        ("revision", |plan| plan.revision = 0),
        ("blank goal", |plan| plan.goal = " \n".into()),
        ("plan ID", |plan| plan.plan_id = "../plan".into()),
        ("long ID", |plan| plan.plan_id = "x".repeat(65)),
        ("blank step ID", |plan| plan.steps[0].id.clear()),
        ("duplicate step", |plan| plan.steps[1].id = "S01".into()),
        ("unknown dependency", |plan| {
            plan.steps[0].depends_on.push("missing".into())
        }),
        ("self dependency", |plan| {
            plan.steps[0].depends_on.push("S01".into())
        }),
        ("cycle", |plan| plan.steps[0].depends_on.push("S02".into())),
        ("duplicate dependency", |plan| {
            plan.steps[1].depends_on.push("S01".into())
        }),
        ("wrong criterion category", |plan| {
            plan.steps[0].acceptance_criteria = vec!["V01".into()]
        }),
        ("unknown verification", |plan| {
            plan.steps[0].verification = vec!["V02".into()]
        }),
        ("duplicate criterion", |plan| {
            plan.verification_strategy[0].id = "AC01".into()
        }),
        ("missing steps", |plan| plan.steps.clear()),
        ("missing acceptance", |plan| {
            plan.acceptance_criteria.clear()
        }),
        ("missing verification", |plan| {
            plan.verification_strategy.clear()
        }),
    ];
    for (label, mutate) in cases {
        let mut plan = sample_plan();
        mutate(&mut plan);
        assert!(
            plan.canonical_json().is_err(),
            "accepted invalid case: {label}"
        );
    }
}

#[test]
fn bounds_apply_to_text_collections_and_aggregate_serialization() {
    let mut plan = sample_plan();
    plan.goal = "x".repeat(8_192);
    plan.validate().unwrap();
    plan.goal.push('x');
    assert!(plan.validate().is_err());
    plan = sample_plan();
    plan.assumptions = vec!["bounded".into(); 128];
    plan.validate().unwrap();
    plan.assumptions.push("one too many".into());
    assert!(plan.validate().is_err());
    plan = sample_plan();
    plan.assumptions = vec!["x".repeat(8_192); 8];
    assert!(plan.validate().is_err());
    plan.assumptions = vec!["\0".repeat(8_192); 2];
    assert!(
        plan.validate().is_err(),
        "JSON escaping must count toward the byte bound"
    );
}

#[test]
fn affected_files_have_one_portable_relative_spelling() {
    for path in [
        "",
        "/tmp/a",
        "../a",
        "a/../b",
        "./a",
        "a//b",
        "a/",
        "C:/a",
        "C:a",
        "a\\b",
        "//server/share",
        "a:stream",
        "a\0b",
        "a\nb",
        "a?b",
        "a*b",
        "a|b",
        "a<file>",
        "a\"b",
        "a./b",
        "a /b",
        " a/b",
        "CON",
        "aux.rs",
        "Lpt9.txt",
        "Com¹.txt",
        "nul/file.rs",
        "con .txt",
        "CONIN$",
        "conout$",
    ] {
        let mut plan = sample_plan();
        plan.steps[0].affected_files = vec![path.into()];
        assert!(plan.validate().is_err(), "accepted unsafe path: {path:?}");
    }
    for path in [
        ".github/workflows/test.yml",
        "src/λ.rs",
        "a file.rs",
        "com10.rs",
        "src/conifer.rs",
    ] {
        let mut plan = sample_plan();
        plan.steps[0].affected_files = vec![path.into()];
        plan.validate().unwrap();
    }
}

#[test]
fn unknown_specification_fields_do_not_silently_disappear() {
    let mut encoded = serde_json::to_value(sample_plan()).unwrap();
    encoded["approved"] = true.into();
    assert!(serde_json::from_value::<PlanRevision>(encoded).is_err());
    let mut encoded = serde_json::to_value(sample_plan()).unwrap();
    encoded["steps"][0]["status"] = "completed".into();
    assert!(serde_json::from_value::<PlanRevision>(encoded).is_err());
}
