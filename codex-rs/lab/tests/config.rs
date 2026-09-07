use codex_lab::ApprovalPolicy;
use codex_lab::PlanConfig;
use codex_lab::Renderer;
use codex_lab::ResolvedWorkflow;
use codex_lab::RoleSelection;
use codex_lab::WorkflowCatalog;
use pretty_assertions::assert_eq;

fn catalog_source() -> String {
    let hash = "0".repeat(64);
    format!(
        r#"schema_version = 1
[skills.p]
path = "planner"
sha256 = "{hash}"
[skills.e]
path = "executor"
sha256 = "{hash}"
[skills.v]
path = "verifier"
sha256 = "{hash}"
[workflows.base]
approval = "human_required"
plan.renderer = "markdown"
roles.planner = "p"
roles.executor = "e"
roles.verifier = "v"
[workflows.markdown]
extends = "base"
[workflows.json]
extends = "markdown"
plan.renderer = "json"
"#
    )
}

#[test]
fn inheritance_changes_only_the_selected_dimension() {
    let source = catalog_source();
    let catalog = WorkflowCatalog::parse(&source).unwrap();
    let mut expected = ResolvedWorkflow {
        max_repairs: 0,
        approval: ApprovalPolicy::HumanRequired,
        plan: PlanConfig {
            renderer: Renderer::Markdown,
        },
        roles: RoleSelection {
            planner: "p".into(),
            executor: "e".into(),
            verifier: "v".into(),
        },
    };
    assert_eq!(catalog.resolve("markdown").unwrap(), expected);
    expected.plan.renderer = Renderer::Json;
    assert_eq!(catalog.resolve("json").unwrap(), expected);
    assert_eq!(
        catalog.inheritance_chain("json").unwrap(),
        vec!["base", "markdown", "json"]
    );
    assert_eq!(catalog.source(), source);
}

#[test]
fn repair_policy_is_inherited_bounded_and_omitted_when_disabled() {
    let source = catalog_source().replace("[workflows.base]", "[workflows.base]\nmax_repairs = 2");
    let catalog = WorkflowCatalog::parse(&source).unwrap();
    assert_eq!(catalog.resolve("json").unwrap().max_repairs, 2);
    let disabled = source.replace("[workflows.json]", "[workflows.json]\nmax_repairs = 0");
    let workflow = WorkflowCatalog::parse(&disabled)
        .unwrap()
        .resolve("json")
        .unwrap();
    assert!(
        serde_json::to_value(workflow)
            .unwrap()
            .get("max_repairs")
            .is_none()
    );
    let invalid = source.replace("max_repairs = 2", "max_repairs = 5");
    assert!(
        WorkflowCatalog::parse(&invalid)
            .unwrap()
            .resolve("json")
            .is_err()
    );
}

#[test]
fn nested_role_overlay_preserves_siblings() {
    let source = catalog_source().replace(
        "[workflows.markdown]\nextends = \"base\"",
        "[workflows.markdown]\nextends = \"base\"\nroles.executor = \"p\"",
    );
    let catalog = WorkflowCatalog::parse(&source).unwrap();
    let mut expected = catalog.resolve("base").unwrap();
    expected.roles.executor = "p".into();
    assert_eq!(catalog.resolve("json").unwrap().roles, expected.roles);
}

#[test]
fn rejects_invalid_schema_unknown_fields_and_unsafe_overrides() {
    let source = catalog_source();
    for invalid in [
        source.replace("schema_version = 1", "schema_version = 2"),
        source.replace("schema_version = 1", "schema_version = 1\nmodel = \"muse\""),
        source.replace("human_required", "none"),
        source.replace("plan.renderer = \"json\"", "plan.renderer = \"xml\""),
        source.replace("plan.renderer = \"json\"", "plan.typo = \"json\""),
        source.replace("roles.verifier = \"v\"", "roles.evaluator = \"v\""),
        source.replace("path = \"planner\"", "path = \"planner\"\nextra = true"),
        source.replace("extends = \"base\"", "extends = [\"base\"]"),
        source.replace("extends = \"base\"", "extends = \"missing\""),
        source.replace("extends = \"base\"", "extends = \"json\""),
    ] {
        assert!(WorkflowCatalog::parse(&invalid).is_err(), "{invalid}");
    }
}

#[test]
fn rejects_missing_role_catalog_entries_and_incomplete_workflows() {
    let source = catalog_source();
    for invalid in [
        source.replace("roles.planner = \"p\"", "roles.planner = \"missing\""),
        source.replace("roles.planner = \"p\"", ""),
        source.replace("approval = \"human_required\"", ""),
    ] {
        let catalog = WorkflowCatalog::parse(&invalid).unwrap();
        assert!(catalog.resolve("json").is_err());
    }
    assert!(
        WorkflowCatalog::parse(&source)
            .unwrap()
            .resolve("absent")
            .is_err()
    );
}

#[test]
fn bounds_input_size_and_inheritance_depth() {
    assert!(WorkflowCatalog::parse(&" ".repeat(64 * 1024 + 1)).is_err());
    let mut source = catalog_source();
    let mut parent = "base".to_string();
    for index in 0..15 {
        source.push_str(&format!("\n[workflows.w{index}]\nextends = \"{parent}\"\n"));
        parent = format!("w{index}");
    }
    assert!(WorkflowCatalog::parse(&source).is_ok());
    source.push_str("\n[workflows.too_deep]\nextends = \"w14\"\n");
    assert!(WorkflowCatalog::parse(&source).is_err());
}
