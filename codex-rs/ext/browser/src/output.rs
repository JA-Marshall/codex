use codex_extension_api::ToolOutput;
use codex_extension_api::ToolPayload;
use codex_protocol::models::FunctionCallOutputContentItem;
use codex_protocol::models::FunctionCallOutputPayload;
use codex_protocol::models::ResponseInputItem;

/// Model-facing output for a successful `browser_navigate` call.
///
/// The observation is serialized as plaintext `function_call_output`, the same result
/// channel every function tool uses, so Muse receives it as a normal tool result.
pub(crate) struct BrowserOutput {
    observation: String,
}

impl BrowserOutput {
    pub(crate) fn new(observation: String) -> Self {
        Self { observation }
    }
}

impl ToolOutput for BrowserOutput {
    fn log_output(&self) -> String {
        "[browser_navigate output]".to_string()
    }

    fn success_for_logging(&self) -> bool {
        true
    }

    fn contains_external_context(&self) -> bool {
        true
    }

    fn to_response_item(&self, call_id: &str, _payload: &ToolPayload) -> ResponseInputItem {
        ResponseInputItem::FunctionCallOutput {
            call_id: call_id.to_string(),
            output: FunctionCallOutputPayload::from_content_items(vec![
                FunctionCallOutputContentItem::InputText {
                    text: self.observation.clone(),
                },
            ]),
        }
    }
}

#[cfg(test)]
#[path = "output_tests.rs"]
mod tests;
