use pretty_assertions::assert_eq;

use super::BrowserError;
use super::BrowserStage;
use super::collapse_whitespace;
use super::decode_entities;
use super::extract_text;
use super::extract_title;
use super::extract_title_and_text;
use super::is_supported_content_type;
use super::truncate_chars;
use super::validate_url;

#[test]
fn error_display_names_the_stage() {
    let err = BrowserError::new(BrowserStage::Connection, "connection refused".to_string());
    assert_eq!(
        err.to_string(),
        "browser connection failed: connection refused"
    );
    assert!(
        err.to_string().starts_with("browser connection failed:"),
        "{err}"
    );

    let err = BrowserError::new(BrowserStage::ArgumentParsing, "bad url".to_string());
    assert_eq!(err.to_string(), "browser argument parsing failed: bad url");
}

#[test]
fn validate_url_accepts_http_and_https() {
    assert_eq!(
        validate_url("https://example.com")
            .expect("https url")
            .as_str(),
        "https://example.com/"
    );
    assert_eq!(
        validate_url("http://127.0.0.1:8099/page")
            .expect("http url")
            .as_str(),
        "http://127.0.0.1:8099/page"
    );
}

#[test]
fn validate_url_rejects_non_http_schemes() {
    let err = validate_url("file:///etc/passwd").expect_err("file urls are rejected");
    assert!(
        err.to_string()
            .starts_with("browser argument parsing failed:"),
        "{err}"
    );
    assert!(err.to_string().contains("unsupported scheme"), "{err}");

    let err = validate_url("notaurl").expect_err("relative urls are rejected");
    assert!(
        err.to_string()
            .starts_with("browser argument parsing failed:"),
        "{err}"
    );
}

#[test]
fn supported_content_types_cover_text_pages() {
    assert!(is_supported_content_type("text/html; charset=utf-8"));
    assert!(is_supported_content_type("text/plain"));
    assert!(is_supported_content_type("application/xhtml+xml"));
    assert!(is_supported_content_type(""));
    assert!(!is_supported_content_type("image/png"));
    assert!(!is_supported_content_type("application/pdf"));
}

#[test]
fn extract_title_reads_title_element() {
    assert_eq!(
        extract_title("<html><head><title>Example Domain</title></head></html>"),
        "Example Domain"
    );
    assert_eq!(extract_title("<html><body>no title</body></html>"), "");
}

#[test]
fn extract_text_strips_scripts_styles_comments_and_tags() {
    let body = r#"<html><head><title>T</title><style>.a{color:red}</style><script>alert(1)</script></head><body><!-- hidden --><h1>Hello &amp; welcome</h1><p>Second  line</p></body></html>"#;
    assert_eq!(extract_text(body), "T Hello & welcome Second line");
}

#[test]
fn decode_entities_handles_numeric_references() {
    assert_eq!(decode_entities("A&#65;B&#x42;C"), "AABBC");
}

#[test]
fn collapse_whitespace_joins_tokens() {
    assert_eq!(collapse_whitespace("  a\n\t b   c "), "a b c");
}

#[test]
fn truncate_chars_marks_overflow() {
    let (text, truncated) = truncate_chars("abcdef", 10);
    assert_eq!(text, "abcdef");
    assert!(!truncated);

    let (text, truncated) = truncate_chars("abcdef", 4);
    assert_eq!(text, "abcd");
    assert!(truncated);
}

#[test]
fn extract_title_and_text_bounds_observation_text() {
    let padding = "word ".repeat(3_000);
    let body =
        format!("<html><head><title>Long</title></head><body><p>{padding}</p></body></html>");
    let (title, text, truncated) = extract_title_and_text(&body);
    assert_eq!(title, "Long");
    assert!(truncated);
    assert!(
        text.chars().count() <= 8_000,
        "text exceeds observation cap"
    );
}
