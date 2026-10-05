//! Local `browser_navigate` tool for models that cannot reach the backend-served browser.
//!
//! Codex's backend-served browser capability is the Playwright `browser_navigate` tool
//! exposed through the ChatGPT `codex_apps` MCP server (`{"url": ...}`). Sessions that
//! authenticate without ChatGPT/codex-backend credentials (for example Muse lab providers)
//! cannot connect to that backend, so the tool is never registered for them and the model
//! receives no browser capability at all.
//!
//! This extension is a thin adapter over the same tool shape: it advertises a plain
//! Responses `function` tool named `browser_navigate` with the same `{"url"}` argument
//! schema, executes the navigation locally by fetching the page, and returns the page
//! title and readable text as a normal `function_call_output` result.
//!
//! Tool-call path:
//! ```text
//! Muse (function_call name=browser_navigate)
//!   -> ToolRouter::build_tool_call (plain name defaults to the `functions` namespace)
//!   -> ToolRegistry dispatch to BrowserNavigateTool (registered by BrowserExtension)
//!   -> BrowserBackend::navigate (fetch, extract, render observation)
//!   -> BrowserOutput::to_response_item (function_call_output)
//!   -> Muse
//! ```
//!
//! Failure taxonomy (every stage names itself in the error returned to the model):
//! - tool registration: the tool is absent from the request when
//!   `features.browser_navigate` is disabled; enable it to advertise the tool.
//! - argument parsing: the call arguments are not a JSON object with an http(s) `url`.
//! - browser startup: the local HTTP backend (fetch client) cannot be constructed.
//! - browser connection: DNS, TCP, TLS, or timeout failures while reaching the URL.
//! - browser execution: HTTP error statuses, oversized/unsupported bodies, read failures.
//!
//! WSL notes: the fetch backend runs inside the Linux environment, so `localhost` URLs
//! resolve to the WSL host (correct for servers started from WSL, unlike a
//! Windows-native browser backend where loopback would mean Windows). No helper
//! executable, child process, or IPC channel is required. The shared default HTTP
//! client is used so configured proxy behavior is preserved.

mod backend;
mod extension;
mod output;
mod tool;

pub use extension::install;
pub use tool::BROWSER_NAVIGATE_TOOL_NAME;
