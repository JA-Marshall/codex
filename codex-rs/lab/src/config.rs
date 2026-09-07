use std::collections::BTreeMap;
use std::path::Path;

use serde::Deserialize;
use serde::Serialize;

use crate::LabError;
use crate::Result;
use crate::instructions::RoleInstructions;
use crate::instructions::SkillSource;

const MAX_CONFIG_BYTES: usize = 64 * 1024;
const MAX_INHERITANCE_DEPTH: usize = 16;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Renderer {
    Markdown,
    Json,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalPolicy {
    HumanRequired,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PlanConfig {
    pub renderer: Renderer,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RoleSelection {
    pub planner: String,
    pub executor: String,
    pub verifier: String,
}

/// Fully resolved behavioral settings, independent of model and provider settings.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ResolvedWorkflow {
    pub approval: ApprovalPolicy,
    pub plan: PlanConfig,
    pub roles: RoleSelection,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct PlanPatch {
    renderer: Option<Renderer>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct RolePatch {
    planner: Option<String>,
    executor: Option<String>,
    verifier: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct WorkflowPatch {
    extends: Option<String>,
    approval: Option<ApprovalPolicy>,
    plan: PlanPatch,
    roles: RolePatch,
}

/// Version-one local catalog. Nested tables merge field by field; a child scalar
/// replaces its parent's value. Version one has no list-valued behavior fields.
#[derive(Debug)]
pub struct WorkflowCatalog {
    source: String,
    workflows: BTreeMap<String, WorkflowPatch>,
    skills: BTreeMap<String, SkillSource>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogData {
    schema_version: u32,
    workflows: BTreeMap<String, WorkflowPatch>,
    skills: BTreeMap<String, SkillSource>,
}

impl WorkflowCatalog {
    pub fn parse(source: &str) -> Result<Self> {
        if source.len() > MAX_CONFIG_BYTES {
            return Err(LabError::Invalid("workflow catalog exceeds 64 KiB".into()));
        }
        let data: CatalogData = toml::from_str(source)?;
        if data.schema_version != 1 || data.workflows.is_empty() {
            return Err(LabError::Invalid(
                "expected schema_version = 1 and at least one workflow".into(),
            ));
        }
        let catalog = Self {
            source: source.to_owned(),
            workflows: data.workflows,
            skills: data.skills,
        };
        for name in catalog.workflows.keys().chain(catalog.skills.keys()) {
            if name.is_empty() || name.len() > 128 || name.chars().any(char::is_whitespace) {
                return Err(LabError::Invalid(format!("invalid catalog name: {name}")));
            }
        }
        for skill in catalog.skills.values() {
            skill.validate()?;
        }
        for name in catalog.workflows.keys() {
            catalog.inheritance_chain(name)?;
        }
        Ok(catalog)
    }

    pub fn source(&self) -> &str {
        &self.source
    }

    /// Returns parent-first provenance, including the selected workflow.
    pub fn inheritance_chain(&self, name: &str) -> Result<Vec<String>> {
        let mut chain = Vec::new();
        let mut current = name;
        loop {
            if chain.len() >= MAX_INHERITANCE_DEPTH || chain.iter().any(|item| item == current) {
                return Err(LabError::Invalid(format!(
                    "workflow inheritance cycle or depth over 16 at {current}"
                )));
            }
            let workflow = self.workflows.get(current).ok_or_else(|| {
                LabError::Invalid(format!("workflow or parent does not exist: {current}"))
            })?;
            chain.push(current.to_owned());
            match &workflow.extends {
                Some(parent) => current = parent,
                None => break,
            }
        }
        chain.reverse();
        Ok(chain)
    }

    pub fn resolve(&self, name: &str) -> Result<ResolvedWorkflow> {
        let mut merged = WorkflowPatch::default();
        for ancestor in self.inheritance_chain(name)? {
            let local = &self.workflows[&ancestor];
            merged.approval = local.approval.or(merged.approval);
            merged.plan.renderer = local.plan.renderer.or(merged.plan.renderer);
            merged.roles.planner = local.roles.planner.clone().or(merged.roles.planner);
            merged.roles.executor = local.roles.executor.clone().or(merged.roles.executor);
            merged.roles.verifier = local.roles.verifier.clone().or(merged.roles.verifier);
        }
        let missing = || LabError::Invalid(format!("workflow {name} is missing required settings"));
        let resolved = ResolvedWorkflow {
            approval: merged.approval.ok_or_else(missing)?,
            plan: PlanConfig {
                renderer: merged.plan.renderer.ok_or_else(missing)?,
            },
            roles: RoleSelection {
                planner: merged.roles.planner.ok_or_else(missing)?,
                executor: merged.roles.executor.ok_or_else(missing)?,
                verifier: merged.roles.verifier.ok_or_else(missing)?,
            },
        };
        for selector in [
            &resolved.roles.planner,
            &resolved.roles.executor,
            &resolved.roles.verifier,
        ] {
            if !self.skills.contains_key(selector) {
                return Err(LabError::Invalid(format!(
                    "required skill is absent from the catalog: {selector}"
                )));
            }
        }
        Ok(resolved)
    }

    /// Freeze explicitly selected SKILL.md bytes relative to a trusted catalog
    /// base. This is preflight, not upstream discovery or model-context injection.
    pub fn resolve_instructions(
        &self,
        base: &Path,
        workflow: &ResolvedWorkflow,
    ) -> Result<RoleInstructions> {
        let snapshot = |selector: &str| {
            self.skills
                .get(selector)
                .ok_or_else(|| LabError::Invalid(format!("unknown skill: {selector}")))?
                .snapshot(base, selector)
        };
        Ok(RoleInstructions {
            planner: snapshot(&workflow.roles.planner)?,
            executor: snapshot(&workflow.roles.executor)?,
            verifier: snapshot(&workflow.roles.verifier)?,
        })
    }
}
