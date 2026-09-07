use codex_lab::PlanCriterion;
use codex_lab::PlanRevision;
use codex_lab::PlanStep;

pub fn sample_plan() -> PlanRevision {
    PlanRevision {
        schema_version: 1,
        plan_id: "fixture-plan".into(),
        revision: 1,
        goal: "Implement a bounded parser".into(),
        assumptions: vec!["Input is UTF-8".into()],
        steps: vec![
            PlanStep {
                id: "S01".into(),
                title: "Implement parsing".into(),
                instructions: "Reject malformed input".into(),
                affected_files: vec!["src/parser.rs".into()],
                depends_on: vec![],
                acceptance_criteria: vec!["AC01".into()],
                verification: vec!["V01".into()],
            },
            PlanStep {
                id: "S02".into(),
                title: "Verify parsing".into(),
                instructions: "Exercise accepted and rejected input".into(),
                affected_files: vec!["tests/parser.rs".into()],
                depends_on: vec!["S01".into()],
                acceptance_criteria: vec!["AC01".into()],
                verification: vec!["V01".into()],
            },
        ],
        risks: vec!["Input limits could reject existing files".into()],
        acceptance_criteria: vec![PlanCriterion {
            id: "AC01".into(),
            description: "Reject invalid input without panicking".into(),
        }],
        verification_strategy: vec![PlanCriterion {
            id: "V01".into(),
            description: "Run parser integration tests".into(),
        }],
        discoveries: vec!["Parser has no external callers".into()],
        blockers: vec![],
    }
}
