use std::collections::BTreeMap;
use std::collections::BTreeSet;

use serde::Deserialize;
use serde::Serialize;
use serde_json::Value;

use crate::LabError;
use crate::Result;

const MAX_ITEMS: usize = 128;
const MAX_TEXT_BYTES: usize = 8_192;
const MAX_PLAN_BYTES: usize = 65_536;

/// The immutable specification of one plan revision. Progress belongs to the workflow.
///
/// Version 1 canonical JSON sorts object keys recursively, retains array order, and
/// uses compact UTF-8 JSON followed by exactly one LF. Strings are not normalized.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlanRevision {
    pub schema_version: u32,
    pub plan_id: String,
    pub revision: u32,
    pub goal: String,
    pub assumptions: Vec<String>,
    pub steps: Vec<PlanStep>,
    pub risks: Vec<String>,
    pub acceptance_criteria: Vec<PlanCriterion>,
    pub verification_strategy: Vec<PlanCriterion>,
    pub discoveries: Vec<String>,
    pub blockers: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlanStep {
    pub id: String,
    pub title: String,
    pub instructions: String,
    pub affected_files: Vec<String>,
    pub depends_on: Vec<String>,
    pub acceptance_criteria: Vec<String>,
    pub verification: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlanCriterion {
    pub id: String,
    pub description: String,
}

impl PlanRevision {
    /// Validate a bounded specification, including its dependency graph and references.
    /// Deserialization alone does not establish validity or confer approval authority.
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != 1 || self.revision == 0 {
            return Err(LabError::Invalid(
                "unsupported plan schema or zero revision".into(),
            ));
        }
        validate_id(&self.plan_id)?;
        validate_text(&self.goal)?;
        for values in [
            &self.assumptions,
            &self.risks,
            &self.discoveries,
            &self.blockers,
        ] {
            validate_texts(values)?;
        }
        if self.steps.is_empty()
            || self.acceptance_criteria.is_empty()
            || self.verification_strategy.is_empty()
        {
            return Err(LabError::Invalid(
                "steps, acceptance and verification criteria are required".into(),
            ));
        }
        validate_count(self.steps.len())?;
        let mut criterion_ids = BTreeSet::new();
        for criteria in [&self.acceptance_criteria, &self.verification_strategy] {
            validate_count(criteria.len())?;
            for criterion in criteria {
                validate_id(&criterion.id)?;
                validate_text(&criterion.description)?;
                if !criterion_ids.insert(criterion.id.as_str()) {
                    return Err(LabError::Invalid(format!(
                        "duplicate criterion ID: {}",
                        criterion.id
                    )));
                }
            }
        }
        let acceptance_ids = self
            .acceptance_criteria
            .iter()
            .map(|item| item.id.as_str())
            .collect();
        let verification_ids = self
            .verification_strategy
            .iter()
            .map(|item| item.id.as_str())
            .collect();
        let mut step_ids = BTreeSet::new();
        for step in &self.steps {
            validate_id(&step.id)?;
            if !step_ids.insert(step.id.as_str()) {
                return Err(LabError::Invalid(format!("duplicate step ID: {}", step.id)));
            }
            validate_text(&step.title)?;
            validate_text(&step.instructions)?;
            validate_count(step.affected_files.len())?;
            let mut files = BTreeSet::new();
            for path in &step.affected_files {
                validate_relative_path(path)?;
                if !files.insert(path) {
                    return Err(LabError::Invalid(format!(
                        "duplicate affected path: {path}"
                    )));
                }
            }
            validate_references(&step.acceptance_criteria, &acceptance_ids)?;
            validate_references(&step.verification, &verification_ids)?;
        }
        for step in &self.steps {
            validate_references(&step.depends_on, &step_ids)?;
        }
        // At most MAX_ITEMS vertices: repeatedly resolve ready steps without recursion.
        let mut resolved = BTreeSet::new();
        while resolved.len() < self.steps.len() {
            let before = resolved.len();
            for step in &self.steps {
                if step
                    .depends_on
                    .iter()
                    .all(|id| resolved.contains(id.as_str()))
                {
                    resolved.insert(step.id.as_str());
                }
            }
            if before == resolved.len() {
                return Err(LabError::Invalid("cyclic plan dependencies".into()));
            }
        }
        if serde_json::to_vec(self)?.len() >= MAX_PLAN_BYTES {
            return Err(LabError::Invalid(
                "canonical plan exceeds 65536 bytes".into(),
            ));
        }
        Ok(())
    }

    pub fn canonical_json(&self) -> Result<Vec<u8>> {
        self.validate()?;
        let mut bytes = serde_json::to_vec(&sorted_json(serde_json::to_value(self)?))?;
        bytes.push(b'\n');
        Ok(bytes)
    }

    /// Hash the entire canonical specification, excluding mutable workflow progress.
    pub fn digest(&self) -> Result<String> {
        Ok(crate::digest_bytes(&self.canonical_json()?))
    }
}

fn sorted_json(value: Value) -> Value {
    match value {
        Value::Object(entries) => {
            let sorted: BTreeMap<_, _> = entries.into_iter().collect();
            Value::Object(
                sorted
                    .into_iter()
                    .map(|(key, value)| (key, sorted_json(value)))
                    .collect(),
            )
        }
        Value::Array(items) => Value::Array(items.into_iter().map(sorted_json).collect()),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => value,
    }
}

fn validate_count(count: usize) -> Result<()> {
    if count > MAX_ITEMS {
        return Err(LabError::Invalid(
            "plan collection exceeds 128 items".into(),
        ));
    }
    Ok(())
}

fn validate_text(value: &str) -> Result<()> {
    if value.trim().is_empty() || value.len() > MAX_TEXT_BYTES {
        return Err(LabError::Invalid(
            "plan text must contain 1..8192 nonblank UTF-8 bytes".into(),
        ));
    }
    Ok(())
}

fn validate_texts(values: &[String]) -> Result<()> {
    validate_count(values.len())?;
    for value in values {
        validate_text(value)?;
    }
    Ok(())
}

fn validate_id(id: &str) -> Result<()> {
    if id.len() > 64
        || !id.starts_with(|value: char| value.is_ascii_alphanumeric())
        || !id
            .bytes()
            .all(|value| value.is_ascii_alphanumeric() || b"-_.".contains(&value))
    {
        return Err(LabError::Invalid("plan IDs require 1..64 ASCII letters, digits, dots, hyphens or underscores, starting with a letter or digit".into()));
    }
    Ok(())
}

fn validate_references(references: &[String], known: &BTreeSet<&str>) -> Result<()> {
    validate_count(references.len())?;
    let mut seen = BTreeSet::new();
    for id in references {
        validate_id(id)?;
        if !known.contains(id.as_str()) || !seen.insert(id) {
            return Err(LabError::Invalid(format!(
                "unknown or duplicate plan reference: {id:?}"
            )));
        }
    }
    Ok(())
}

fn validate_relative_path(path: &str) -> Result<()> {
    // A single portable spelling avoids host-dependent interpretation, drive paths,
    // NTFS streams, Windows device aliases and traversal through either separator.
    if path.is_empty()
        || path.len() > 1_024
        || path
            .chars()
            .any(|value| value.is_control() || "\\:*?\"<>|".contains(value))
    {
        return Err(LabError::Invalid(
            "repository-relative paths require 1..1024 bytes and portable characters".into(),
        ));
    }
    for component in path.split('/') {
        let stem = component
            .split('.')
            .next()
            .unwrap_or_default()
            .trim_end_matches(' ')
            .to_ascii_uppercase();
        let device = matches!(
            stem.as_str(),
            "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$"
        ) || ["COM", "LPT"].iter().any(|&prefix| {
            stem.strip_prefix(prefix).is_some_and(|suffix| {
                matches!(
                    suffix,
                    "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
                )
            })
        });
        if component.is_empty()
            || component == "."
            || component == ".."
            || component.starts_with(' ')
            || component.ends_with([' ', '.'])
            || device
        {
            return Err(LabError::Invalid(format!(
                "invalid repository-relative path: {path:?}"
            )));
        }
    }
    Ok(())
}
