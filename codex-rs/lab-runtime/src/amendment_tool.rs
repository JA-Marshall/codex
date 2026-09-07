use std::collections::BTreeMap;
use std::sync::Arc;

use codex_extension_api::ExtensionData;
use codex_extension_api::ToolContributor;
use codex_tools::AdditionalProperties;
use codex_tools::FunctionCallError;
use codex_tools::JsonSchema;
use codex_tools::JsonToolOutput;
use codex_tools::ResponsesApiTool;
use codex_tools::ToolCall;
use codex_tools::ToolExecutor;
use codex_tools::ToolExecutorFuture;
use codex_tools::ToolName;
use codex_tools::ToolSpec;
use serde::Deserialize;

use crate::PhaseGate;

pub(crate) struct AmendmentTool(pub Arc<PhaseGate>);

impl ToolContributor for AmendmentTool {
    fn tools(
        &self,
        _: &ExtensionData,
        _: &ExtensionData,
    ) -> Vec<Arc<dyn for<'a> ToolExecutor<ToolCall<'a>>>> {
        vec![Arc::new(Self(Arc::clone(&self.0)))]
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    reason: String,
}

impl<'call> ToolExecutor<ToolCall<'call>> for AmendmentTool {
    fn tool_name(&self) -> ToolName {
        ToolName::plain("lab_request_amendment")
    }

    fn spec(&self) -> ToolSpec {
        ToolSpec::Function(ResponsesApiTool {
            name: "lab_request_amendment".into(),
            description: "Stop execution immediately when a discovery materially invalidates the approved plan. Explain the discovery and required change; the host will request an amended plan and fresh human approval.".into(),
            strict: true,
            defer_loading: None,
            parameters: JsonSchema::object(BTreeMap::from([("reason".into(), JsonSchema::string(None))]),
                Some(vec!["reason".into()]), Some(AdditionalProperties::Boolean(false))),
            output_schema: None,
        })
    }

    fn handle<'a>(&'a self, call: ToolCall<'call>) -> ToolExecutorFuture<'a>
    where
        'call: 'a,
    {
        Box::pin(async move {
            let arguments = call.function_arguments()?;
            if arguments.len() > 8192 {
                return Err(FunctionCallError::RespondToModel(
                    "amendment input exceeds limit".into(),
                ));
            }
            let request: Request = serde_json::from_str(arguments).map_err(|_| {
                FunctionCallError::RespondToModel("expected a reason string".into())
            })?;
            self.0
                .request_amendment(&request.reason)
                .map_err(|error| FunctionCallError::RespondToModel(error.to_string()))?;
            Ok(Box::new(JsonToolOutput::new(
                serde_json::json!({"status":"stopping_for_amendment"}),
            )) as Box<dyn codex_tools::ToolOutput>)
        })
    }
}
