use anyhow::Result;
use pretty_assertions::assert_eq;
use serde_json::json;

use super::binary_metadata;
use super::redact;
use super::safe_effective_toml;

#[test]
fn only_selected_provider_and_effective_values_are_retained() {
    let snapshot = safe_effective_toml(
        json!({
            "model":"pinned-model", "model_context_window":32768,
            "model_provider":"selected",
            "model_providers":{
                "selected":{"base_url":"https://api.example/v1", "env_key":"MUSE_API_KEY"},
                "unused":{"name":"DO_NOT_RETAIN_UNUSED", "auth":{"command":"DO_NOT_RETAIN_AUTH"}}
            },
            "profiles":{"other":{"api_key":"DO_NOT_RETAIN_PROFILE"}},
            "projects":{"other":{"env":{"TOKEN":"DO_NOT_RETAIN_PROJECT"}}}
        }),
        "selected",
    );
    assert_eq!(
        snapshot,
        json!({
            "model":"pinned-model", "model_context_window":32768,
            "model_provider":"selected",
            "model_providers":{"selected":{"base_url":"https://api.example/v1", "env_key":"MUSE_API_KEY"}}
        })
    );
}

#[test]
fn nested_credentials_headers_and_environment_values_are_redacted() {
    let mut snapshot = json!({
        "provider":{
            "http_headers":{"X-Unusual-Name":"DO_NOT_RETAIN_HEADER"},
            "Authorization":"DO_NOT_RETAIN_AUTHORIZATION",
            "X-Api-Key":"DO_NOT_RETAIN_HYPHEN_KEY",
            "auth":{"command":"DO_NOT_RETAIN_AUTH_COMMAND", "args":["secret"]},
            "credential":{"password":"DO_NOT_RETAIN_PASSWORD"},
            "env":{"ARBITRARY":"DO_NOT_RETAIN_ENV"},
            "query_params":{"arbitrary":"DO_NOT_RETAIN_QUERY"},
            "items":[{"refresh_token":"DO_NOT_RETAIN_TOKEN"}],
            "env_key":"MUSE_API_KEY",
            "env_http_headers":{"Authorization":"MUSE_AUTH_HEADER","X-Bad":"Bearer DO_NOT_RETAIN_REFERENCE"}
        },
        "model_max_output_tokens":4096
    });
    redact(&mut snapshot);
    assert!(!snapshot.to_string().contains("DO_NOT_RETAIN"));
    assert_eq!(snapshot["provider"]["env_key"], "MUSE_API_KEY");
    assert_eq!(
        snapshot["provider"]["env_http_headers"]["Authorization"],
        "MUSE_AUTH_HEADER"
    );
    assert_eq!(snapshot["model_max_output_tokens"], 4096);
}

#[test]
fn url_userinfo_queries_and_fragments_are_never_retained() {
    let mut snapshot = json!({"endpoints":[
        "https://DO_NOT_RETAIN_USER:DO_NOT_RETAIN_PASSWORD@example.test/v1?key=DO_NOT_RETAIN_QUERY#DO_NOT_RETAIN_FRAGMENT",
        "https://example.test/v1?api_key=DO_NOT_RETAIN_KEY",
        "https://[invalid DO_NOT_RETAIN_MALFORMED"
    ]});
    redact(&mut snapshot);
    assert_eq!(
        snapshot,
        json!({"endpoints":[
            "https://example.test/v1", "https://example.test/v1", "<redacted: malformed URL>"
        ]})
    );
}

#[test]
fn helper_binary_fingerprints_are_content_based_and_absence_is_explicit() -> Result<()> {
    let root = tempfile::tempdir()?;
    let first = root.path().join("helper-one");
    let second = root.path().join("helper-two");
    std::fs::write(&first, b"same runtime binary")?;
    std::fs::write(&second, b"same runtime binary")?;
    let first_snapshot = binary_metadata(Some(&first))?;
    let second_snapshot = binary_metadata(Some(&second))?;
    assert_eq!(first_snapshot["sha256"], second_snapshot["sha256"]);
    assert_eq!(first_snapshot["bytes"], 19);
    assert_eq!(binary_metadata(None)?, serde_json::Value::Null);
    Ok(())
}
