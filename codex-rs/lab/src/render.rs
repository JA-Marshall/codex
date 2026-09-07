use crate::LabError;
use crate::PlanCriterion;
use crate::PlanRevision;
use crate::Result;

/// A pure projection of a validated revision. Implementations must preserve all
/// specification fields, bound output, and perform no synchronization or approval.
/// Rendered content is never an authoritative input to the workflow gate.
pub trait PlanRenderer {
    fn render(&self, plan: &PlanRevision) -> Result<RenderedPlan>;
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RenderedPlan {
    pub media_type: String,
    pub filename: String,
    pub content: Vec<u8>,
}

pub struct JsonRenderer;
pub struct MarkdownRenderer;

impl PlanRenderer for JsonRenderer {
    fn render(&self, plan: &PlanRevision) -> Result<RenderedPlan> {
        Ok(RenderedPlan {
            media_type: "application/json".into(),
            filename: "plan.view.json".into(),
            content: plan.canonical_json()?,
        })
    }
}

impl PlanRenderer for MarkdownRenderer {
    fn render(&self, plan: &PlanRevision) -> Result<RenderedPlan> {
        plan.validate()?;
        let mut output = String::from(
            "# Implementation plan\n\nThis is a projection of the canonical plan; it does not grant approval.\n\nText values use JSON string notation inside code spans to preserve exact content.\n\n",
        );
        output.push_str(&format!(
            "- Schema version: {}\n- Plan ID: {}\n- Revision: {}\n\n## Goal\n\n{}\n",
            plan.schema_version,
            literal(&plan.plan_id)?,
            plan.revision,
            literal(&plan.goal)?
        ));
        string_section(&mut output, "Assumptions", &plan.assumptions)?;
        output.push_str("\n## Implementation steps\n");
        for step in &plan.steps {
            output.push_str(&format!(
                "\n### Step {}\n\n- ID: {}\n- Title: {}\n- Instructions: {}\n",
                literal(&step.id)?,
                literal(&step.id)?,
                literal(&step.title)?,
                literal(&step.instructions)?
            ));
            for (label, values) in [
                ("Affected files", &step.affected_files),
                ("Dependencies", &step.depends_on),
                ("Acceptance criteria", &step.acceptance_criteria),
                ("Verification", &step.verification),
            ] {
                output.push_str(&format!("\n**{label}**\n\n"));
                string_list(&mut output, values)?;
            }
        }
        string_section(&mut output, "Risks", &plan.risks)?;
        for (label, criteria) in [
            ("Acceptance criteria", &plan.acceptance_criteria),
            ("Verification strategy", &plan.verification_strategy),
        ] {
            output.push_str(&format!("\n## {label}\n\n"));
            for PlanCriterion { id, description } in criteria {
                output.push_str(&format!("- {}: {}\n", literal(id)?, literal(description)?));
            }
        }
        string_section(&mut output, "Discoveries", &plan.discoveries)?;
        string_section(&mut output, "Blockers", &plan.blockers)?;
        if output.len() > 524_288 {
            return Err(LabError::Invalid(
                "rendered plan exceeds 524288 bytes".into(),
            ));
        }
        Ok(RenderedPlan {
            media_type: "text/markdown; charset=utf-8".into(),
            filename: "PLAN.md".into(),
            content: output.into_bytes(),
        })
    }
}

fn string_section(output: &mut String, label: &str, values: &[String]) -> Result<()> {
    output.push_str(&format!("\n## {label}\n\n"));
    string_list(output, values)
}

fn string_list(output: &mut String, values: &[String]) -> Result<()> {
    if values.is_empty() {
        output.push_str("_None._\n");
    }
    for value in values {
        output.push_str(&format!("- {}\n", literal(value)?));
    }
    Ok(())
}

fn literal(value: &str) -> Result<String> {
    // JSON escapes line/control characters. Escaping HTML-sensitive characters is
    // additionally defensive for downstream Markdown consumers. A delimiter longer
    // than every embedded backtick run prevents text from escaping its code span.
    let json = serde_json::to_string(value)?
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e");
    let delimiter = "`".repeat(
        json.split(|value| value != '`')
            .map(str::len)
            .max()
            .unwrap_or_default()
            + 1,
    );
    Ok(format!("{delimiter}{json}{delimiter}"))
}
