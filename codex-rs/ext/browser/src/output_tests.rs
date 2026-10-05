use pretty_assertions::assert_eq;

use super::BrowserOutput;
use super::ToolOutput;
use codex_extension_api::ToolPayload;
use codex_protocol::models::FunctionCallOutputContentItem;
use codex_protocol::models::FunctionCallOutputPayload;
use codex_protocol::models::ResponseInputItem;

#[test]
fn emits_plaintext_function_call_output() {
    let output = BrowserOutput::new("browser observation for https://example.com".to_string());

    assert_eq!(
        output.to_response_item(
            "call-1",
            &ToolPayload::Function {
                arguments: "{}".to_string(),
            },
        ),
        ResponseInputItem::FunctionCallOutput {
            call_id: "call-1".to_string(),
            output: FunctionCallOutputPayload::from_content_items(vec![
                FunctionCallOutputContentItem::InputText {
                    text: "browser observation for https://example.com".to_string(),
                },
            ]),
        }
    );
    assert!(output.success_for_logging());
    assert!(output.contains_external_context());
}
