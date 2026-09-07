mod common;

use codex_lab::JsonRenderer;
use codex_lab::MarkdownRenderer;
use codex_lab::PlanRenderer;
use codex_lab::PlanRevision;
use codex_lab::RenderedPlan;
use pretty_assertions::assert_eq;

use common::sample_plan;

#[test]
fn json_view_is_the_full_canonical_revision_without_mutation() {
    let plan = sample_plan();
    let before = plan.clone();
    assert_eq!(
        JsonRenderer.render(&plan).unwrap(),
        RenderedPlan {
            media_type: "application/json".into(),
            filename: "plan.view.json".into(),
            content: plan.canonical_json().unwrap(),
        }
    );
    let json = JsonRenderer.render(&plan).unwrap();
    assert_eq!(
        serde_json::from_slice::<PlanRevision>(&json.content).unwrap(),
        before
    );
    MarkdownRenderer.render(&plan).unwrap();
    assert_eq!(plan, before);
}

#[test]
fn markdown_preserves_fields_and_contains_hostile_text_in_literal_code() {
    let mut plan = sample_plan();
    plan.steps.truncate(1);
    plan.goal = "Keep ``` ticks\n# Fake heading\n<script>& unsafe</script> λ\t\0".into();
    let rendered = MarkdownRenderer.render(&plan).unwrap();
    assert_eq!(
        (rendered.media_type.as_str(), rendered.filename.as_str()),
        ("text/markdown; charset=utf-8", "PLAN.md")
    );
    insta::assert_snapshot!(String::from_utf8(rendered.content).unwrap(), @r#"
    # Implementation plan

    This is a projection of the canonical plan; it does not grant approval.

    Text values use JSON string notation inside code spans to preserve exact content.

    - Schema version: 1
    - Plan ID: `"fixture-plan"`
    - Revision: 1

    ## Goal

    ````"Keep ``` ticks\n# Fake heading\n\u003cscript\u003e\u0026 unsafe\u003c/script\u003e λ\t\u0000"````

    ## Assumptions

    - `"Input is UTF-8"`

    ## Implementation steps

    ### Step `"S01"`

    - ID: `"S01"`
    - Title: `"Implement parsing"`
    - Instructions: `"Reject malformed input"`

    **Affected files**

    - `"src/parser.rs"`

    **Dependencies**

    _None._

    **Acceptance criteria**

    - `"AC01"`

    **Verification**

    - `"V01"`

    ## Risks

    - `"Input limits could reject existing files"`

    ## Acceptance criteria

    - `"AC01"`: `"Reject invalid input without panicking"`

    ## Verification strategy

    - `"V01"`: `"Run parser integration tests"`

    ## Discoveries

    - `"Parser has no external callers"`

    ## Blockers

    _None._
    "#);
}

#[test]
fn every_renderer_refuses_an_invalid_specification() {
    let mut plan = sample_plan();
    plan.steps[0].depends_on.push("missing".into());
    for renderer in [&JsonRenderer as &dyn PlanRenderer, &MarkdownRenderer] {
        assert!(renderer.render(&plan).is_err());
    }
}
