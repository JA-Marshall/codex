use std::sync::Arc;

use anyhow::Result;
use codex_browser_extension::install as install_browser_extension;
use codex_core::config::Config;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_features::Feature;
use codex_login::CodexAuth;
use core_test_support::responses;
use core_test_support::test_codex::test_codex;
use pretty_assertions::assert_eq;
use serde_json::Value;
use tokio::io::AsyncReadExt;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpListener;

/// Serves one canned HTML page over loopback without touching external networks.
async fn serve_single_page(body: &'static str) -> String {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("loopback listener binds");
    let addr = listener.local_addr().expect("listener has an address");
    tokio::spawn(async move {
        let Ok((mut socket, _)) = listener.accept().await else {
            return;
        };
        let mut request = vec![0u8; 1024];
        let _ = socket.read(&mut request).await;
        let response = format!(
            "HTTP/1.1 200 OK\r\ncontent-type: text/html\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
            body.len()
        );
        let _ = socket.write_all(response.as_bytes()).await;
    });
    format!("http://127.0.0.1:{addr}/", addr = addr.port())
}

fn has_browser_navigate_tool(body: &Value) -> bool {
    body["tools"].as_array().is_some_and(|tools| {
        tools.iter().any(|tool| {
            tool.get("type").and_then(Value::as_str) == Some("function")
                && tool.get("name").and_then(Value::as_str) == Some("browser_navigate")
        })
    })
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn browser_navigate_round_trip_returns_page_observation() -> Result<()> {
    let page_url = serve_single_page(
        "<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1></body></html>",
    )
    .await;

    let server = responses::start_mock_server().await;
    let first_mock = responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_response_created("resp-1"),
            responses::ev_function_call(
                "call-1",
                "browser_navigate",
                &serde_json::json!({ "url": page_url }).to_string(),
            ),
            responses::ev_completed("resp-1"),
        ]),
    )
    .await;
    let follow_up_mock = responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_assistant_message("msg-1", "done"),
            responses::ev_completed("resp-2"),
        ]),
    )
    .await;

    let auth = CodexAuth::from_api_key("dummy");
    let mut extension_builder = ExtensionRegistryBuilder::<Config>::new();
    install_browser_extension(&mut extension_builder);
    let builder = test_codex()
        .with_auth(auth)
        .with_extensions(Arc::new(extension_builder.build()))
        .with_config(|config| {
            config
                .features
                .enable(Feature::BrowserNavigate)
                .expect("browser_navigate feature should be enabled");
        });
    let test = builder.build(&server).await?;

    test.submit_turn("Navigate to the page").await?;

    assert!(
        has_browser_navigate_tool(&first_mock.single_request().body_json()),
        "browser_navigate must be advertised as a plain function tool"
    );
    let output = follow_up_mock
        .function_call_output_text("call-1")
        .expect("browser result must flow back into model context");
    assert!(output.contains("browser observation for"), "{output}");
    assert!(output.contains("status: 200"), "{output}");
    assert!(output.contains("Example Domain"), "{output}");
    assert_eq!(first_mock.requests().len(), 1);
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn browser_navigate_stays_hidden_without_feature() -> Result<()> {
    let server = responses::start_mock_server().await;
    let first_mock = responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_response_created("resp-1"),
            responses::ev_completed("resp-1"),
        ]),
    )
    .await;

    let auth = CodexAuth::from_api_key("dummy");
    let mut extension_builder = ExtensionRegistryBuilder::<Config>::new();
    install_browser_extension(&mut extension_builder);
    let builder = test_codex()
        .with_auth(auth)
        .with_extensions(Arc::new(extension_builder.build()));
    let test = builder.build(&server).await?;

    test.submit_turn("hello").await?;

    assert!(
        !has_browser_navigate_tool(&first_mock.single_request().body_json()),
        "browser_navigate must not leak to models when the feature is off"
    );
    Ok(())
}
