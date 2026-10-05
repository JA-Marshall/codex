use std::sync::Arc;

use codex_extension_api::ConversationHistory;
use codex_extension_api::FunctionCallError;
use codex_extension_api::NoopTurnItemEmitter;
use codex_extension_api::ToolCall;
use codex_extension_api::ToolCallSource;
use codex_extension_api::ToolExecutor;
use codex_extension_api::ToolName;
use codex_extension_api::ToolPayload;
use codex_extension_api::ToolSpec;
use codex_utils_output_truncation::TruncationPolicy;
use pretty_assertions::assert_eq;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpListener;

use super::BROWSER_NAVIGATE_TOOL_NAME;
use super::BrowserNavigateTool;
use super::render_observation;
use crate::backend::BrowserBackend;
use crate::backend::BrowserObservation;

fn tool_call_with_arguments(arguments: &str) -> ToolCall<'_> {
    ToolCall {
        turn_id: "turn-1".to_string(),
        call_id: "call-1".to_string(),
        tool_name: ToolName::plain(BROWSER_NAVIGATE_TOOL_NAME),
        model: "test-model".to_string(),
        codex_turn_metadata: None,
        truncation_policy: TruncationPolicy::Bytes(1024),
        source: ToolCallSource::Direct,
        conversation_history: ConversationHistory::default(),
        turn_item_emitter: Arc::new(NoopTurnItemEmitter),
        environments: Vec::new(),
        payload: ToolPayload::Function {
            arguments: arguments.to_string(),
        },
    }
}

async fn handle_to_err(tool: &BrowserNavigateTool, call: ToolCall<'_>) -> FunctionCallError {
    match tool.handle(call).await {
        Ok(_) => panic!("expected the browser call to fail"),
        Err(err) => err,
    }
}

#[test]
fn tool_name_is_plain_browser_navigate() {
    assert_eq!(BROWSER_NAVIGATE_TOOL_NAME, "browser_navigate");
}

#[test]
fn spec_advertises_plain_function_with_required_url() {
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);

    assert_eq!(
        tool.tool_name(),
        ToolName::plain(BROWSER_NAVIGATE_TOOL_NAME)
    );
    let ToolSpec::Function(spec) = tool.spec() else {
        panic!("browser_navigate must be a plain function tool");
    };
    assert_eq!(spec.name, BROWSER_NAVIGATE_TOOL_NAME);
    assert!(!spec.strict);
    let parameters = serde_json::to_value(&spec.parameters).expect("parameters serialize");
    assert_eq!(
        parameters["required"],
        serde_json::json!(["url"]),
        "{parameters}"
    );
    assert_eq!(parameters["properties"]["url"]["type"], "string");
}

#[tokio::test]
async fn handle_rejects_missing_url_at_argument_parsing_stage() {
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);
    let call = tool_call_with_arguments(r#"{"other": 1}"#);

    let err = handle_to_err(&tool, call).await;
    let FunctionCallError::RespondToModel(message) = err else {
        panic!("argument errors must be returned to the model");
    };
    assert!(
        message.starts_with("browser argument parsing failed:"),
        "{message}"
    );
}

#[tokio::test]
async fn handle_rejects_empty_arguments_at_argument_parsing_stage() {
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);
    let call = tool_call_with_arguments("   ");

    let err = handle_to_err(&tool, call).await;
    assert!(
        err.to_string()
            .starts_with("browser argument parsing failed:"),
        "{err}"
    );
}

#[tokio::test]
async fn handle_rejects_non_http_url_at_argument_parsing_stage() {
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);
    let call = tool_call_with_arguments(r#"{"url": "file:///etc/passwd"}"#);

    let err = handle_to_err(&tool, call).await;
    assert!(
        err.to_string()
            .starts_with("browser argument parsing failed:"),
        "{err}"
    );
}

/// Serves one canned HTML page over loopback without touching external networks.
async fn serve_single_page(body: &'static str, content_type: &'static str) -> String {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("loopback listener binds");
    let addr = listener.local_addr().expect("listener has an address");
    tokio::spawn(async move {
        let Ok((mut socket, _)) = listener.accept().await else {
            return;
        };
        let mut request = vec![0u8; 1024];
        let _ = tokio::io::AsyncReadExt::read(&mut socket, &mut request).await;
        let response = format!(
            "HTTP/1.1 200 OK\r\ncontent-type: {content_type}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
            body.len()
        );
        let _ = socket.write_all(response.as_bytes()).await;
    });
    format!("http://127.0.0.1:{}/", addr.port())
}

#[tokio::test]
async fn handle_returns_page_observation_as_tool_result() {
    let page_url = serve_single_page(
        "<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1></body></html>",
        "text/html",
    )
    .await;
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);
    let arguments = format!(r#"{{"url": "{page_url}"}}"#);
    let call = tool_call_with_arguments(&arguments);

    let output = match tool.handle(call).await {
        Ok(output) => output,
        Err(err) => panic!("loopback fetch works: {err}"),
    };
    let item = output.to_response_item(
        "call-1",
        &ToolPayload::Function {
            arguments: "{}".to_string(),
        },
    );
    let rendered = serde_json::to_string(&item).expect("result serializes");
    assert!(rendered.contains("Example Domain"), "{rendered}");
    assert!(rendered.contains("status: 200"), "{rendered}");
}

#[tokio::test]
async fn handle_reports_unreachable_backend_at_connection_stage() {
    // Port 1 is reserved and never serves TCP, so connecting fails deterministically.
    let backend = BrowserBackend::new(codex_login::default_client::create_client());
    let tool = BrowserNavigateTool::new(backend);
    let call = tool_call_with_arguments(r#"{"url": "http://127.0.0.1:1/"}"#);

    let err = handle_to_err(&tool, call).await;
    assert!(
        err.to_string().starts_with("browser connection failed:"),
        "{err}"
    );
}

#[test]
fn render_observation_shape() {
    let rendered = render_observation(&BrowserObservation {
        url: "https://example.com/".to_string(),
        redirected: false,
        status: 200,
        title: "Example Domain".to_string(),
        text: "Example Domain".to_string(),
        truncated: false,
    });

    assert_eq!(
        rendered,
        "browser observation for https://example.com/\nstatus: 200\ntitle: Example Domain\ntext:\nExample Domain"
    );
}

#[test]
fn render_observation_marks_redirects_truncation_and_empty_pages() {
    let rendered = render_observation(&BrowserObservation {
        url: "https://example.com/other".to_string(),
        redirected: true,
        status: 200,
        title: String::new(),
        text: String::new(),
        truncated: true,
    });

    assert_eq!(
        rendered,
        "browser observation for https://example.com/other\nstatus: 200\nredirected: true\ntitle: (none)\ntext:\n(no readable text)\n[truncated: page text exceeds the observation limit]"
    );
}
