//! Versioned metadata projection of prepared, non-secret experimental inputs.

use std::fs::File;
use std::io::Read;
use std::path::Path;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Config;
use serde_json::Value;
use serde_json::json;
use sha2::Digest;
use sha2::Sha256;

use crate::PhaseAccess;
use crate::context::MAX_PHASE_CONTEXT_BYTES;
use crate::context::MAX_PHASE_FRAGMENT_BYTES;

pub(crate) fn effective_settings(config: &Config) -> Result<Value> {
    let toml = safe_effective_toml(
        serde_json::to_value(config.config_layer_stack.effective_config())?,
        &config.model_provider_id,
    );
    let provider = &config.model_provider;
    // Deliberately project provider fields instead of serializing auth material.
    let mut selected_provider = json!({
        "id":config.model_provider_id,"name":provider.name,"base_url":provider.base_url,
        "wire_api":provider.wire_api,"env_key":provider.env_key,
        "env_http_headers":provider.env_http_headers,
        "request_max_retries":provider.request_max_retries(),
        "stream_max_retries":provider.stream_max_retries(),
        "stream_idle_timeout_ms":provider.stream_idle_timeout().as_millis(),
        "websocket_connect_timeout_ms":provider.websocket_connect_timeout().as_millis(),
        "supports_websockets":provider.supports_websockets,
        "supports_standalone_web_search":provider.supports_standalone_web_search,
        "requires_openai_auth":provider.requires_openai_auth
    });
    redact(&mut selected_provider);
    Ok(json!({
        "schema_version":1,"effective_toml":toml,"selected_provider":selected_provider,
        "lab_report_contracts":{"planner":"canonical-id-references-v2","verification":"indexed-command-receipt-v1"},
        "model":config.model,"model_catalog":config.model_catalog,"service_tier":config.service_tier,
        "context_window":config.model_context_window,
        "auto_compact_token_limit":config.model_auto_compact_token_limit,
        "auto_compact_token_limit_scope":config.model_auto_compact_token_limit_scope,
        "reasoning_effort":config.model_reasoning_effort,"reasoning_summary":config.model_reasoning_summary,
        "verbosity":config.model_verbosity,"base_instructions":config.base_instructions,
        "compact_prompt":config.compact_prompt,
        "base_enabled_features":config.features.get().enabled_features().into_iter().map(codex_features::Feature::key).collect::<Vec<_>>(),
        "phase_transformations":{
            "research_planning":{"sandbox":PhaseAccess::ReadOnly.policy(),"shell_tool":false},
            "implementation_verification":{"sandbox":PhaseAccess::WorkspaceWrite.policy(),"shell_tool":true},
            "thread_lifecycle":"fresh thread per phase; upstream shutdown before phase acknowledgement",
            "role_instructions":"exact frozen RunSpec instruction bytes replace developer_instructions",
            "ambient_skills":"disabled by ProceduralInstructionsOnly and restricted configuration",
            "context_fragment_byte_limit":MAX_PHASE_FRAGMENT_BYTES,
            "combined_context_byte_limit":MAX_PHASE_CONTEXT_BYTES,
            "context_truncation":"reject oversized input; no truncation"
        },
        "runtime_binaries":{
            "codex_self":binary_metadata(config.codex_self_exe.as_deref())?,
            "linux_sandbox":binary_metadata(config.codex_linux_sandbox_exe.as_deref())?,
            "execve_wrapper":binary_metadata(config.main_execve_wrapper_exe.as_deref())?
        },
        "excluded": [
            "credential values and literal HTTP/query/environment maps",
            "inactive profile/project definitions and unselected provider definitions",
            "URL userinfo, queries and fragments",
            "resolved environment values; environment reference names are retained",
            "system package versions and model-provider internal serving configuration"
        ]
    }))
}

fn safe_effective_toml(mut value: Value, selected_provider: &str) -> Value {
    if let Some(config) = value.as_object_mut() {
        // Active profile values have already contributed to effective settings.
        // Definitions for other profiles/projects are unrelated to this run.
        config.remove("profiles");
        config.remove("projects");
        if let Some(providers) = config
            .get_mut("model_providers")
            .and_then(Value::as_object_mut)
        {
            providers.retain(|name, _| name == selected_provider);
        }
    }
    redact(&mut value);
    value
}

fn redact(value: &mut Value) {
    match value {
        Value::Object(map) => {
            for (key, value) in map {
                let normalized = key.to_ascii_lowercase().replace('-', "_");
                if normalized == "env_key" {
                    if !value.is_null() && !value.as_str().is_some_and(environment_reference) {
                        *value = "<redacted: invalid environment reference>".into();
                    }
                } else if normalized == "env_http_headers" {
                    if let Some(headers) = value.as_object_mut() {
                        for reference in headers.values_mut() {
                            if !reference.as_str().is_some_and(environment_reference) {
                                *reference = "<redacted: invalid environment reference>".into();
                            }
                        }
                    } else if !value.is_null() {
                        *value = "<redacted: invalid environment references>".into();
                    }
                } else {
                    let credential_key = [
                        "password",
                        "secret",
                        "bearer",
                        "credential",
                        "api_key",
                        "authorization",
                        "cookie",
                    ]
                    .iter()
                    .any(|part| normalized.contains(part))
                        || normalized == "auth"
                        || normalized.starts_with("auth_")
                        || normalized.ends_with("_auth")
                        || (normalized.contains("token") && !value.is_number())
                        || matches!(
                            normalized.as_str(),
                            "http_headers" | "headers" | "query_params" | "env" | "environment"
                        );
                    if credential_key && !value.is_null() && !value.is_boolean() {
                        *value = "<redacted>".into();
                    } else {
                        redact(value);
                    }
                }
            }
        }
        Value::Array(values) => {
            for value in values {
                redact(value);
            }
        }
        Value::String(text) if text.contains("://") => {
            if let Ok(mut url) = url::Url::parse(text) {
                let _ = url.set_username("");
                let _ = url.set_password(None);
                url.set_query(None);
                url.set_fragment(None);
                *text = url.to_string();
            } else {
                *text = "<redacted: malformed URL>".into();
            }
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
}

fn environment_reference(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(byte) if byte.is_ascii_alphabetic() || byte == b'_')
        && value.len() <= 256
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn binary_metadata(path: Option<&Path>) -> Result<Value> {
    let Some(path) = path else {
        return Ok(Value::Null);
    };
    let path = path.canonicalize().context("resolve runtime binary")?;
    let mut file = File::open(&path)?;
    let before = file.metadata()?;
    ensure!(
        before.is_file() && before.len() <= 2 * 1024 * 1024 * 1024,
        "runtime binary is not a bounded regular file"
    );
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut bytes_read = 0_u64;
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes_read += count as u64;
        ensure!(
            bytes_read <= before.len(),
            "runtime binary grew while hashing"
        );
        hasher.update(&buffer[..count]);
    }
    let after = file.metadata()?;
    ensure!(
        bytes_read == before.len()
            && before.len() == after.len()
            && before.modified()? == after.modified()?,
        "runtime binary changed while hashing"
    );
    Ok(json!({"path":path,"bytes":bytes_read,"sha256":format!("{:x}",hasher.finalize())}))
}

#[cfg(test)]
#[path = "settings_tests.rs"]
mod tests;
