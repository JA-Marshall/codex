//! Thin adapter exposing the browser capability as a plain Responses function tool.
//!
//! Muse lab providers accept plain `function` tools but have no proven support for the
//! `namespace` or `custom` tool shapes, so the adapter advertises `browser_navigate` in
//! the default `functions` namespace with the same `{"url"}` argument schema as the
//! backend-served Playwright `browser_navigate` tool. Incoming calls are parsed here and
//! delegated unchanged to [`crate::backend::BrowserBackend`]; this module never fetches
//! pages itself.

use codex_extension_api::FunctionCallError;
use codex_extension_api::ResponsesApiTool;
use codex_extension_api::ToolCall;
use codex_extension_api::ToolExecutor;
use codex_extension_api::ToolName;
use codex_extension_api::ToolOutput;
use codex_extension_api::ToolSpec;
use codex_tools::JsonSchema;
use codex_tools::ToolExposure;
use serde::Deserialize;
use std::collections::BTreeMap;

use crate::backend::BrowserBackend;
use crate::backend::BrowserObservation;
use crate::output::BrowserOutput;

/// Plain function name advertised to the model.
///
/// This intentionally mirrors the leaf name of the backend-served Playwright tool so the
/// same `browser_navigate({"url"})` invocation shape works through either surface.
pub const BROWSER_NAVIGATE_TOOL_NAME: &str = "browser_navigate";

const BROWSER_NAVIGATE_DESCRIPTION: &str = "Navigate to a URL and return the page observation (final URL, HTTP status, title, and readable text). Use this to browse or verify web pages, including pages served on the local network. Only http and https URLs are supported; page content is fetched without executing scripts.";

/// Arguments accepted from the model.
///
/// Unknown fields are ignored so forward-compatible callers keep working; only `url`
/// drives execution, matching the backend-served browser tool schema.
#[derive(Debug, Deserialize, PartialEq)]
struct NavigateArgs {
    url: String,
}

fn navigate_parameters_schema() -> JsonSchema {
    JsonSchema::object(
        BTreeMap::from([(
            "url".to_string(),
            JsonSchema::string(Some(
                "Fully-qualified http or https URL to navigate to.".to_string(),
            )),
        )]),
        Some(vec!["url".to_string()]),
        Some(false.into()),
    )
}

/// Adapter from Muse's plain function-call schema to the browser backend.
pub(crate) struct BrowserNavigateTool {
    backend: BrowserBackend,
}

impl BrowserNavigateTool {
    pub(crate) fn new(backend: BrowserBackend) -> Self {
        Self { backend }
    }

    pub(crate) fn with_default_backend() -> Result<Self, FunctionCallError> {
        BrowserBackend::with_default_client()
            .map(Self::new)
            .map_err(|err| FunctionCallError::Fatal(err.to_string()))
    }
}

impl<'call> ToolExecutor<ToolCall<'call>> for BrowserNavigateTool {
    fn tool_name(&self) -> ToolName {
        ToolName::plain(BROWSER_NAVIGATE_TOOL_NAME)
    }

    fn spec(&self) -> ToolSpec {
        ToolSpec::Function(ResponsesApiTool {
            name: BROWSER_NAVIGATE_TOOL_NAME.to_string(),
            description: BROWSER_NAVIGATE_DESCRIPTION.to_string(),
            strict: false,
            parameters: navigate_parameters_schema(),
            output_schema: None,
            defer_loading: None,
        })
    }

    fn exposure(&self) -> ToolExposure {
        ToolExposure::Direct
    }

    fn supports_parallel_tool_calls(&self) -> bool {
        true
    }

    fn handle<'a>(&'a self, call: ToolCall<'call>) -> codex_extension_api::ToolExecutorFuture<'a>
    where
        'call: 'a,
    {
        Box::pin(self.handle_call(call))
    }
}

impl BrowserNavigateTool {
    async fn handle_call(
        &self,
        call: ToolCall<'_>,
    ) -> Result<Box<dyn ToolOutput>, FunctionCallError> {
        let args = parse_navigate_args(&call)?;
        let observation = self
            .backend
            .navigate(&args.url)
            .await
            .map_err(|err| FunctionCallError::RespondToModel(err.to_string()))?;
        Ok(Box::new(BrowserOutput::new(render_observation(
            &observation,
        ))))
    }
}

/// Parses Muse's plain function-call arguments at the argument-parsing stage.
fn parse_navigate_args(call: &ToolCall<'_>) -> Result<NavigateArgs, FunctionCallError> {
    let arguments = call.function_arguments()?;
    if arguments.trim().is_empty() {
        return Err(FunctionCallError::RespondToModel(
            "browser argument parsing failed: arguments must be a JSON object with an http or https \"url\" field".to_string(),
        ));
    }
    let args: NavigateArgs = serde_json::from_str(arguments).map_err(|err| {
        FunctionCallError::RespondToModel(format!(
            "browser argument parsing failed: arguments must be a JSON object with an http or https \"url\" field: {err}"
        ))
    })?;
    if args.url.trim().is_empty() {
        return Err(FunctionCallError::RespondToModel(
            "browser argument parsing failed: \"url\" must not be empty".to_string(),
        ));
    }
    Ok(args)
}

/// Renders the model-facing browser observation returned as the tool result.
fn render_observation(observation: &BrowserObservation) -> String {
    let url = &observation.url;
    let status = observation.status;
    let mut lines = vec![
        format!("browser observation for {url}"),
        format!("status: {status}"),
    ];
    if observation.redirected {
        lines.push("redirected: true".to_string());
    }
    if observation.title.is_empty() {
        lines.push("title: (none)".to_string());
    } else {
        let title = &observation.title;
        lines.push(format!("title: {title}"));
    }
    lines.push("text:".to_string());
    if observation.text.is_empty() {
        lines.push("(no readable text)".to_string());
    } else {
        lines.push(observation.text.clone());
    }
    if observation.truncated {
        lines.push("[truncated: page text exceeds the observation limit]".to_string());
    }
    lines.join("\n")
}

#[cfg(test)]
#[path = "tool_tests.rs"]
mod tests;
