use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolAdmissionPermit;

use crate::function_tool::FunctionCallError;
use crate::tools::context::ToolInvocation;
use crate::tools::lifecycle::extension_tool_call_source;

pub(crate) async fn admit_tool(
    invocation: &ToolInvocation,
) -> Result<Vec<ToolAdmissionPermit>, FunctionCallError> {
    let thread_id = invocation.session.thread_id.to_string();
    invocation
        .session
        .services
        .extensions
        .admit_tool(ToolAdmissionInput {
            session_store: &invocation.session.services.session_extension_data,
            thread_store: &invocation.session.services.thread_extension_data,
            turn_store: invocation.turn.extension_data.as_ref(),
            thread_id: &thread_id,
            turn_id: &invocation.turn.sub_id,
            call_id: &invocation.call_id,
            tool_name: &invocation.tool_name,
            source: extension_tool_call_source(invocation.source.clone()),
        })
        .await
        .map_err(|error| {
            FunctionCallError::RespondToModel(format!(
                "Tool blocked by host admission policy: {error}"
            ))
        })
}
