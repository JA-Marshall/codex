//! Local execution backend for `browser_navigate`.
//!
//! The backend fetches the requested page over HTTP(S) from the Codex host and renders a
//! bounded plaintext observation (final URL, status, title, readable text). Fetching from
//! the host keeps loopback semantics aligned with WSL servers started from the same
//! environment and avoids any helper executable, child process, or IPC channel.

use codex_http_client::HttpClient;
use std::fmt;
use std::time::Duration;
use url::Url;

/// Total request timeout (connect + read) for a single navigation.
const NAVIGATE_TIMEOUT: Duration = Duration::from_secs(20);
/// Maximum response body kept in memory before extraction.
const MAX_BODY_BYTES: usize = 512 * 1024;
/// Maximum extracted page text kept in the model-facing observation.
const MAX_TEXT_CHARS: usize = 8_000;

/// Pipeline stage where a browser failure occurred.
///
/// Every stage renders into the error returned to the model so Muse can tell tool
/// registration, argument parsing, browser startup, connection, and execution apart.
/// (Tool registration failures surface as an unknown tool before this backend runs.)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BrowserStage {
    ArgumentParsing,
    Startup,
    Connection,
    Execution,
}

impl fmt::Display for BrowserStage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let stage = match self {
            Self::ArgumentParsing => "argument parsing",
            Self::Startup => "startup",
            Self::Connection => "connection",
            Self::Execution => "execution",
        };
        f.write_str(stage)
    }
}

/// Staged browser backend failure.
///
/// The `Display` form is returned to the model verbatim, so it always carries the stage
/// (`browser connection failed: ...`) alongside the backend detail.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BrowserError {
    stage: BrowserStage,
    detail: String,
}

impl BrowserError {
    fn new(stage: BrowserStage, detail: impl Into<String>) -> Self {
        Self {
            stage,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for BrowserError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "browser {stage} failed: {detail}",
            stage = self.stage,
            detail = self.detail
        )
    }
}

impl std::error::Error for BrowserError {}

/// Model-facing result of a successful navigation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BrowserObservation {
    /// URL after following redirects.
    pub(crate) url: String,
    /// True when at least one redirect was followed.
    pub(crate) redirected: bool,
    pub(crate) status: u16,
    pub(crate) title: String,
    pub(crate) text: String,
    pub(crate) truncated: bool,
}

/// Local page-fetch backend for `browser_navigate`.
#[derive(Clone)]
pub(crate) struct BrowserBackend {
    client: HttpClient,
}

impl BrowserBackend {
    pub(crate) fn new(client: HttpClient) -> Self {
        Self { client }
    }

    /// Builds the backend from the shared default HTTP client.
    ///
    /// This is the startup stage: only client construction can fail here, so a failure
    /// reports `browser startup failed` rather than a connection or execution problem.
    pub(crate) fn with_default_client() -> Result<Self, BrowserError> {
        Ok(Self::new(codex_login::default_client::create_client()))
    }

    /// Navigate to `url` and return the page observation.
    pub(crate) async fn navigate(&self, raw_url: &str) -> Result<BrowserObservation, BrowserError> {
        let url = validate_url(raw_url)?;
        let response = self
            .client
            .get(url.clone())
            .timeout(NAVIGATE_TIMEOUT)
            .send()
            .await
            .map_err(|err| classify_fetch_error(&url, &err))?;
        let final_url = response.url().to_string();
        let redirected = final_url != url.as_str();
        let status = response.status().as_u16();
        if !response.status().is_success() {
            return Err(BrowserError::new(
                BrowserStage::Execution,
                format!("{url} returned HTTP status {status}"),
            ));
        }
        let content_type = response
            .headers()
            .get(http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        if !is_supported_content_type(&content_type) {
            return Err(BrowserError::new(
                BrowserStage::Execution,
                format!("{url} returned unsupported content type {content_type:?}"),
            ));
        }
        if let Some(declared) = response.content_length()
            && declared > MAX_BODY_BYTES as u64
        {
            return Err(BrowserError::new(
                BrowserStage::Execution,
                format!(
                    "{url} declared {declared} bytes, exceeding the {MAX_BODY_BYTES} byte limit"
                ),
            ));
        }
        let bytes = read_body_capped(response, &url).await?;
        let body = String::from_utf8_lossy(&bytes);
        let (title, text, truncated) = extract_title_and_text(&body);
        Ok(BrowserObservation {
            url: final_url,
            redirected,
            status,
            title,
            text,
            truncated,
        })
    }
}

/// Streams the response body, stopping past [`MAX_BODY_BYTES`] plus one byte.
async fn read_body_capped(
    response: codex_http_client::HttpResponse,
    url: &Url,
) -> Result<Vec<u8>, BrowserError> {
    use futures::StreamExt;

    let mut body = Vec::new();
    let mut stream = response.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|err| classify_fetch_error(url, &err))?;
        body.extend_from_slice(&chunk);
        if body.len() > MAX_BODY_BYTES {
            return Err(BrowserError::new(
                BrowserStage::Execution,
                format!(
                    "{url} returned more than {MAX_BODY_BYTES} bytes, exceeding the body limit"
                ),
            ));
        }
    }
    Ok(body)
}

/// Returns the failure stage for an HTTP client error.
///
/// Request construction failures are startup failures; DNS, connect, TLS, proxy, and
/// timeout failures happen before any HTTP exchange, so they are connection failures;
/// redirect loops, status, body, and decode failures happen mid-exchange, so they are
/// execution failures.
fn classify_fetch_error(url: &Url, err: &codex_http_client::HttpError) -> BrowserError {
    let stage = if err.is_builder() {
        BrowserStage::Startup
    } else if err.is_timeout() || err.is_connect() {
        BrowserStage::Connection
    } else {
        BrowserStage::Execution
    };
    BrowserError::new(stage, format!("{url}: {err}"))
}

/// Rejects non-http(s) and unparseable URLs at the argument-parsing stage.
fn validate_url(raw_url: &str) -> Result<Url, BrowserError> {
    let url = Url::parse(raw_url.trim()).map_err(|err| {
        BrowserError::new(
            BrowserStage::ArgumentParsing,
            format!("{raw_url:?} is not a valid URL: {err}"),
        )
    })?;
    match url.scheme() {
        "http" | "https" => Ok(url),
        scheme => Err(BrowserError::new(
            BrowserStage::ArgumentParsing,
            format!(
                "{raw_url:?} uses unsupported scheme {scheme:?}; only http and https navigation is supported"
            ),
        )),
    }
}

fn is_supported_content_type(content_type: &str) -> bool {
    // Empty (unspecified) content types are treated as text, matching curl-like behavior.
    let media_type = content_type
        .split(';')
        .next()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    media_type.is_empty()
        || media_type.starts_with("text/")
        || media_type == "application/xhtml+xml"
}

/// Extracts the page title and readable text, bounded to [`MAX_TEXT_CHARS`] characters.
fn extract_title_and_text(body: &str) -> (String, String, bool) {
    let title = extract_title(body);
    let text = extract_text(body);
    let (text, truncated) = truncate_chars(&text, MAX_TEXT_CHARS);
    (title, text, truncated)
}

fn extract_title(body: &str) -> String {
    let lowered = body.to_ascii_lowercase();
    let Some(start) = lowered.find("<title") else {
        return String::new();
    };
    let Some(tag_end) = lowered[start..].find('>') else {
        return String::new();
    };
    let content_start = start + tag_end + 1;
    let Some(end) = lowered[content_start..].find("</title>") else {
        return String::new();
    };
    collapse_whitespace(&decode_entities(&body[content_start..content_start + end]))
}

/// Strips scripts, styles, comments, and tags, then collapses whitespace.
fn extract_text(body: &str) -> String {
    let without_scripts = strip_element(body, "script");
    let without_styles = strip_element(&without_scripts, "style");
    let without_comments = strip_comments(&without_styles);
    let mut text = String::with_capacity(without_comments.len());
    let mut in_tag = false;
    for ch in without_comments.chars() {
        match ch {
            '<' => in_tag = true,
            '>' => {
                in_tag = false;
                text.push(' ');
            }
            _ if !in_tag => text.push(ch),
            _ => {}
        }
    }
    collapse_whitespace(&decode_entities(&text))
}

/// Removes `<name ...>...</name>` ranges case-insensitively.
fn strip_element(body: &str, name: &str) -> String {
    let lowered = body.to_ascii_lowercase();
    let open = format!("<{name}");
    let close = format!("</{name}>");
    let mut out = String::with_capacity(body.len());
    let mut rest = body;
    let mut rest_lowered = lowered.as_str();
    while let Some(start) = rest_lowered.find(open.as_str()) {
        out.push_str(&rest[..start]);
        let after_open = &rest_lowered[start..];
        let Some(tag_end) = after_open.find('>') else {
            break;
        };
        let content_start = start + tag_end + 1;
        if let Some(end) = rest_lowered[content_start..].find(close.as_str()) {
            let skip_to = content_start + end + close.len();
            rest = &rest[skip_to..];
            rest_lowered = &rest_lowered[skip_to..];
        } else {
            rest = &rest[content_start..];
            break;
        }
    }
    out.push_str(rest);
    out
}

fn strip_comments(body: &str) -> String {
    let mut out = String::with_capacity(body.len());
    let mut rest = body;
    while let Some(start) = rest.find("<!--") {
        out.push_str(&rest[..start]);
        if let Some(end) = rest[start..].find("-->") {
            rest = &rest[start + end + 3..];
        } else {
            break;
        }
    }
    out.push_str(rest);
    out
}

fn decode_entities(text: &str) -> String {
    let mut out = text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&nbsp;", " ");
    // Decode numeric character references (&#65; and &#x41;).
    while let Some(start) = out.find("&#") {
        let Some(semi) = out[start..].find(';') else {
            break;
        };
        let entity = &out[start + 2..start + semi];
        let codepoint = entity
            .strip_prefix('x')
            .or_else(|| entity.strip_prefix('X'))
            .and_then(|hex| u32::from_str_radix(hex, 16).ok())
            .or_else(|| entity.parse::<u32>().ok())
            .and_then(char::from_u32);
        if let Some(ch) = codepoint {
            out.replace_range(start..start + semi + 1, &ch.to_string());
        } else {
            break;
        }
    }
    out
}

fn collapse_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn truncate_chars(text: &str, max_chars: usize) -> (String, bool) {
    if text.chars().count() <= max_chars {
        return (text.to_string(), false);
    }
    let truncated: String = text.chars().take(max_chars).collect();
    (truncated, true)
}

#[cfg(test)]
#[path = "backend_tests.rs"]
mod tests;
