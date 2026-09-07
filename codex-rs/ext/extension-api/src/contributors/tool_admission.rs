use std::fmt;

use codex_tools::ToolCallSource;
use codex_tools::ToolName;

use crate::ExtensionData;
use crate::ExtensionFuture;

/// Host-owned identity supplied before tool hooks or the tool handler execute.
///
/// This boundary controls admission of a tool capability, not its arguments.
/// Arguments may subsequently be rewritten by upstream hooks. It does not cover
/// provider-side tools, process startup, or host operations outside tool dispatch.
#[derive(Clone)]
pub struct ToolAdmissionInput<'a> {
    pub session_store: &'a ExtensionData,
    pub thread_store: &'a ExtensionData,
    pub turn_store: &'a ExtensionData,
    pub thread_id: &'a str,
    pub turn_id: &'a str,
    pub call_id: &'a str,
    pub tool_name: &'a ToolName,
    pub source: ToolCallSource,
}

/// One contributor's dispatch-lifetime accounting guard.
///
/// The host retains this permit until dispatch returns or is cancelled. Dropping
/// it must release accounting synchronously and must not panic. It is not proof
/// that subprocesses or other work spawned by a tool have terminated.
pub struct ToolAdmissionPermit {
    _guard: Box<dyn Send + Sync>,
}

impl ToolAdmissionPermit {
    /// Retains extension-owned accounting until this dispatch ends.
    pub fn new<T: Send + Sync + 'static>(guard: T) -> Self {
        Self {
            _guard: Box::new(guard),
        }
    }
}

/// Bounded, model-visible explanation of a tool admission denial.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ToolAdmissionError {
    reason: String,
}

impl ToolAdmissionError {
    /// Creates a denial. Reasons must not contain secrets or tool arguments.
    pub fn new(reason: impl AsRef<str>) -> Self {
        Self {
            reason: reason.as_ref().chars().take(512).collect(),
        }
    }
}

impl fmt::Display for ToolAdmissionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.reason)
    }
}

impl std::error::Error for ToolAdmissionError {}

/// Host policy that must admit every tool before its hooks or handler execute.
///
/// All registered contributors must return a permit. Implementations should
/// atomically check authority and acquire accounting, deny on unavailable state,
/// and release accounting if their future is cancelled before returning a permit.
/// No contributor can override another contributor's denial.
pub trait ToolAdmissionContributor: Send + Sync {
    fn admit<'a>(
        &'a self,
        input: ToolAdmissionInput<'a>,
    ) -> ExtensionFuture<'a, Result<ToolAdmissionPermit, ToolAdmissionError>>;
}
