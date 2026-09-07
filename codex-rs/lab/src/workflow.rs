use std::collections::BTreeMap;
use std::collections::BTreeSet;

use serde::Serialize;

use crate::LabError;
use crate::PlanRevision;
use crate::Result;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowState {
    Researching,
    Planning,
    AwaitingPlanApproval,
    Implementing,
    AwaitingPlanAmendment,
    Verifying,
    Completed,
    Failed,
}

/// Exact subject of a human decision. Possession alone does not grant authority.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ApprovalTarget {
    pub run_id: String,
    pub plan_id: String,
    pub revision: u32,
    pub content_sha256: String,
    pub run_spec_sha256: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionKind {
    Implementation,
    Verification,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum StepStatus {
    Pending,
    InProgress,
    Completed,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct StepProgress {
    pub status: StepStatus,
    pub evidence: Option<String>,
}

/// Host-supplied observation, not a model's assertion that a test passed.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct VerificationEvidence {
    pub passed: bool,
    pub reference: String,
    pub acceptance_criteria: Vec<String>,
}

/// Read-only exported state. There is deliberately no deserialization/resume API.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct WorkflowSnapshot {
    pub state: WorkflowState,
    pub target: Option<ApprovalTarget>,
    pub approved: Option<ApprovalTarget>,
    pub progress: BTreeMap<String, StepProgress>,
    pub verification: BTreeMap<String, VerificationEvidence>,
}

#[derive(Clone)]
pub(crate) struct Workflow {
    pub(crate) snapshot: WorkflowSnapshot,
    pub(crate) plan: Option<PlanRevision>,
    run_id: String,
    spec_digest: String,
    retired_ids: BTreeSet<String>,
    repairs: u8,
}

pub(crate) enum Command {
    BeginPlanning,
    SubmitPlan(PlanRevision),
    EditPlan {
        plan: PlanRevision,
        editor: String,
        reason: String,
    },
    Approve {
        target: ApprovalTarget,
        reviewer: String,
    },
    Reject {
        target: ApprovalTarget,
        reviewer: String,
        reason: String,
    },
    RequestAmendment(String),
    RecordStep {
        id: String,
        progress: StepProgress,
    },
    BeginVerification,
    BeginRepair { limit: u8 },
    RecordVerification {
        id: String,
        evidence: VerificationEvidence,
    },
    Complete,
    Fail(String),
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub(crate) enum Change {
    RunStarted,
    PlanningStarted,
    PlanSubmitted {
        target: ApprovalTarget,
    },
    PlanEdited {
        target: ApprovalTarget,
        editor: String,
        reason: String,
    },
    HumanApproved {
        target: ApprovalTarget,
        reviewer: String,
    },
    HumanRejected {
        target: ApprovalTarget,
        reviewer: String,
        reason: String,
    },
    AmendmentRequested {
        reason: String,
    },
    StepUpdated {
        id: String,
        progress: StepProgress,
    },
    VerificationStarted,
    RepairStarted { attempt: u8 },
    VerificationRecorded {
        id: String,
        evidence: VerificationEvidence,
    },
    Completed,
    Failed {
        reason: String,
    },
    ActionAdmitted {
        target: ApprovalTarget,
        kind: ActionKind,
    },
    ActionFinished {
        kind: ActionKind,
        success: bool,
    },
}

impl Workflow {
    pub(crate) fn new(run_id: String, spec_digest: String) -> Self {
        Self {
            snapshot: WorkflowSnapshot {
                state: WorkflowState::Researching,
                target: None,
                approved: None,
                progress: BTreeMap::new(),
                verification: BTreeMap::new(),
            },
            plan: None,
            run_id,
            spec_digest,
            retired_ids: BTreeSet::new(),
            repairs: 0,
        }
    }

    pub(crate) fn apply(&mut self, command: Command) -> Result<Change> {
        if matches!(
            self.snapshot.state,
            WorkflowState::Completed | WorkflowState::Failed
        ) {
            return Err(LabError::Invalid("workflow is terminal".into()));
        }
        match command {
            Command::BeginRepair { limit } => {
                self.require_state(WorkflowState::Verifying)?;
                if self.snapshot.approved.is_none()
                    || self.snapshot.approved != self.snapshot.target
                    || self.repairs >= limit
                    || !self.snapshot.verification.values().any(|e| !e.passed)
                {
                    return Err(LabError::Invalid("repair requires approved failed verification and remaining budget".into()));
                }
                self.repairs += 1;
                self.snapshot.verification.clear();
                for progress in self.snapshot.progress.values_mut() {
                    *progress = StepProgress { status: StepStatus::Pending, evidence: None };
                }
                self.snapshot.state = WorkflowState::Implementing;
                Ok(Change::RepairStarted { attempt: self.repairs })
            }
            Command::BeginPlanning => {
                self.require_state(WorkflowState::Researching)?;
                self.snapshot.state = WorkflowState::Planning;
                Ok(Change::PlanningStarted)
            }
            Command::SubmitPlan(plan) => {
                if !matches!(
                    self.snapshot.state,
                    WorkflowState::Planning | WorkflowState::AwaitingPlanAmendment
                ) {
                    return Err(LabError::Invalid(
                        "plan submission requires planning or amendment".into(),
                    ));
                }
                let target = self.replace_plan(plan)?;
                Ok(Change::PlanSubmitted { target })
            }
            Command::EditPlan {
                plan,
                editor,
                reason,
            } => {
                self.require_review()?;
                bounded_text(&editor)?;
                bounded_text(&reason)?;
                let target = self.replace_plan(plan)?;
                Ok(Change::PlanEdited {
                    target,
                    editor,
                    reason,
                })
            }
            Command::Approve { target, reviewer } => {
                self.require_review()?;
                self.require_target(&target)?;
                bounded_text(&reviewer)?;
                let plan = self.current_plan()?;
                if !plan.blockers.is_empty() {
                    return Err(LabError::Invalid(
                        "resolve plan blockers before approval".into(),
                    ));
                }
                self.snapshot.approved = Some(target.clone());
                self.snapshot.state = WorkflowState::Implementing;
                Ok(Change::HumanApproved { target, reviewer })
            }
            Command::Reject {
                target,
                reviewer,
                reason,
            } => {
                self.require_review()?;
                self.require_target(&target)?;
                bounded_text(&reviewer)?;
                bounded_text(&reason)?;
                self.snapshot.approved = None;
                if self.snapshot.state == WorkflowState::AwaitingPlanApproval {
                    self.snapshot.state = WorkflowState::Planning;
                }
                Ok(Change::HumanRejected {
                    target,
                    reviewer,
                    reason,
                })
            }
            Command::RequestAmendment(reason) => {
                if !matches!(
                    self.snapshot.state,
                    WorkflowState::Implementing | WorkflowState::Verifying
                ) {
                    return Err(LabError::Invalid("amendment requires approved work".into()));
                }
                bounded_text(&reason)?;
                self.snapshot.approved = None;
                // No pending target exists until a new revision is submitted.
                self.snapshot.target = None;
                self.snapshot.state = WorkflowState::AwaitingPlanAmendment;
                Ok(Change::AmendmentRequested { reason })
            }
            Command::RecordStep { id, progress } => {
                self.require_state(WorkflowState::Implementing)?;
                let step = self
                    .current_plan()?
                    .steps
                    .iter()
                    .find(|step| step.id == id)
                    .ok_or_else(|| LabError::Invalid("unknown step".into()))?;
                let previous = self
                    .snapshot
                    .progress
                    .get(&id)
                    .ok_or_else(|| LabError::Invalid("missing step progress".into()))?;
                if previous.status == StepStatus::Completed
                    || progress.status == StepStatus::Pending
                {
                    return Err(LabError::Invalid(
                        "step progress cannot move backwards or rewrite completion".into(),
                    ));
                }
                if step.depends_on.iter().any(|dependency| {
                    self.snapshot
                        .progress
                        .get(dependency)
                        .is_none_or(|p| p.status != StepStatus::Completed)
                }) {
                    return Err(LabError::Invalid("step dependencies are incomplete".into()));
                }
                if let Some(evidence) = &progress.evidence {
                    bounded_text(evidence)?;
                } else if progress.status == StepStatus::Completed {
                    return Err(LabError::Invalid("completed step requires evidence".into()));
                }
                self.snapshot.progress.insert(id.clone(), progress.clone());
                Ok(Change::StepUpdated { id, progress })
            }
            Command::BeginVerification => {
                self.require_state(WorkflowState::Implementing)?;
                if self
                    .snapshot
                    .progress
                    .values()
                    .any(|p| p.status != StepStatus::Completed)
                {
                    return Err(LabError::Invalid(
                        "implementation steps are incomplete".into(),
                    ));
                }
                self.snapshot.state = WorkflowState::Verifying;
                Ok(Change::VerificationStarted)
            }
            Command::RecordVerification { id, evidence } => {
                self.require_state(WorkflowState::Verifying)?;
                let plan = self.current_plan()?;
                bounded_text(&evidence.reference)?;
                if !plan
                    .verification_strategy
                    .iter()
                    .any(|check| check.id == id)
                    || evidence.acceptance_criteria.len() > plan.acceptance_criteria.len()
                    || evidence.acceptance_criteria.iter().any(|id| {
                        !plan
                            .acceptance_criteria
                            .iter()
                            .any(|criterion| &criterion.id == id)
                    })
                {
                    return Err(LabError::Invalid(
                        "unknown verification or acceptance criterion".into(),
                    ));
                }
                self.snapshot
                    .verification
                    .insert(id.clone(), evidence.clone());
                Ok(Change::VerificationRecorded { id, evidence })
            }
            Command::Complete => {
                self.require_state(WorkflowState::Verifying)?;
                let plan = self.current_plan()?;
                let evidence = &self.snapshot.verification;
                if plan
                    .verification_strategy
                    .iter()
                    .any(|check| evidence.get(&check.id).is_none_or(|e| !e.passed))
                    || plan.acceptance_criteria.iter().any(|criterion| {
                        !evidence
                            .values()
                            .any(|e| e.passed && e.acceptance_criteria.contains(&criterion.id))
                    })
                {
                    return Err(LabError::Invalid(
                        "passing verification and acceptance evidence required".into(),
                    ));
                }
                self.snapshot.state = WorkflowState::Completed;
                self.snapshot.approved = None;
                Ok(Change::Completed)
            }
            Command::Fail(reason) => {
                bounded_text(&reason)?;
                self.fail_closed();
                Ok(Change::Failed { reason })
            }
        }
    }

    pub(crate) fn admit(&self, target: &ApprovalTarget, kind: ActionKind) -> Result<()> {
        self.require_target(target)?;
        if self.snapshot.approved.as_ref() != Some(target) {
            return Err(LabError::Invalid(
                "current explicit human approval required".into(),
            ));
        }
        self.require_state(match kind {
            ActionKind::Implementation => WorkflowState::Implementing,
            ActionKind::Verification => WorkflowState::Verifying,
        })
    }

    pub(crate) fn fail_closed(&mut self) {
        self.snapshot.state = WorkflowState::Failed;
        self.snapshot.approved = None;
    }

    fn replace_plan(&mut self, plan: PlanRevision) -> Result<ApprovalTarget> {
        plan.validate()?;
        if let Some(previous) = &self.plan {
            if plan.plan_id != previous.plan_id
                || previous.revision.checked_add(1) != Some(plan.revision)
            {
                return Err(LabError::Invalid(
                    "replacement must retain plan ID and increment revision by one".into(),
                ));
            }
            if plan
                .steps
                .iter()
                .any(|step| self.retired_ids.contains(&step.id))
            {
                return Err(LabError::Invalid(
                    "retired step IDs cannot be reused".into(),
                ));
            }
            self.retired_ids.extend(
                previous
                    .steps
                    .iter()
                    .filter(|step| !plan.steps.iter().any(|new| new.id == step.id))
                    .map(|step| step.id.clone()),
            );
        } else if plan.revision != 1 {
            return Err(LabError::Invalid(
                "initial plan revision must be one".into(),
            ));
        }
        let target = ApprovalTarget {
            run_id: self.run_id.clone(),
            plan_id: plan.plan_id.clone(),
            revision: plan.revision,
            content_sha256: plan.digest()?,
            run_spec_sha256: self.spec_digest.clone(),
        };
        self.snapshot.progress = plan
            .steps
            .iter()
            .map(|step| {
                (
                    step.id.clone(),
                    StepProgress {
                        status: StepStatus::Pending,
                        evidence: None,
                    },
                )
            })
            .collect();
        self.snapshot.verification.clear();
        self.snapshot.approved = None;
        self.snapshot.target = Some(target.clone());
        if self.snapshot.state != WorkflowState::AwaitingPlanAmendment {
            self.snapshot.state = WorkflowState::AwaitingPlanApproval;
        }
        self.plan = Some(plan);
        Ok(target)
    }

    fn current_plan(&self) -> Result<&PlanRevision> {
        self.plan
            .as_ref()
            .ok_or_else(|| LabError::Invalid("no plan submitted".into()))
    }

    fn require_state(&self, state: WorkflowState) -> Result<()> {
        if self.snapshot.state != state {
            return Err(LabError::Invalid(format!("operation requires {state:?}")));
        }
        Ok(())
    }

    fn require_review(&self) -> Result<()> {
        if !matches!(
            self.snapshot.state,
            WorkflowState::AwaitingPlanApproval | WorkflowState::AwaitingPlanAmendment
        ) {
            return Err(LabError::Invalid(
                "human decision requires pending review".into(),
            ));
        }
        Ok(())
    }

    fn require_target(&self, target: &ApprovalTarget) -> Result<()> {
        if self.snapshot.target.as_ref() != Some(target) {
            return Err(LabError::Invalid(
                "approval target does not match this run and pending revision".into(),
            ));
        }
        Ok(())
    }
}

pub(crate) fn bounded_text(value: &str) -> Result<()> {
    if value.trim().is_empty() || value.len() > 8192 {
        return Err(LabError::Invalid(
            "text must be nonempty and at most 8192 bytes".into(),
        ));
    }
    Ok(())
}
