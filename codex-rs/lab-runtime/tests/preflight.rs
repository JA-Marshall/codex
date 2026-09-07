use std::path::Path;

use anyhow::Context;
use anyhow::Result;
use codex_core::config::ConfigBuilder;
use codex_core::config::ConfigOverrides;
use codex_core_api::Config;
use codex_core_api::Feature;
use codex_lab_runtime::PhaseAccess;
use codex_lab_runtime::RuntimePaths;
use codex_lab_runtime::restricted_overrides;
use codex_lab_runtime::restricted_requirements;
use codex_lab_runtime::validate_model_catalog;
use codex_lab_runtime::validate_phase_context;
use codex_lab_runtime::validate_runtime_config;
use codex_protocol::config_types::Personality;
use codex_protocol::openai_models::ApprovalMessages;
use codex_protocol::openai_models::ConfigShellToolType;
use codex_protocol::openai_models::ModelInstructionsVariables;
use codex_protocol::openai_models::PermissionMessages;
use codex_protocol::openai_models::ToolMode;
use codex_protocol::protocol::SandboxPolicy;
use pretty_assertions::assert_eq;
use serde_json::json;

async fn fixture(root: &Path) -> Result<(Config, RuntimePaths)> {
    let repository = root.join("repo");
    let home = root.join("home");
    let artifacts = root.join("artifacts");
    for directory in [&repository, &home, &artifacts] {
        std::fs::create_dir(directory)?;
    }
    std::fs::write(
        home.join("catalog.json"),
        serde_json::to_vec(&json!({
            "models": [{
                "slug": "lab-fixture-v1", "display_name": "Lab fixture",
                "description": null, "supported_reasoning_levels": [],
                "shell_type": "unified_exec", "visibility": "list",
                "supported_in_api": true, "priority": 0,
                "availability_nux": null, "upgrade": null,
                "support_verbosity": false, "default_verbosity": null,
                "apply_patch_tool_type": "freeform",
                "truncation_policy": { "mode": "bytes", "limit": 8192 },
                "context_window": 32768,
                "experimental_supported_tools": [],
                "include_apps_usage_instructions": false,
                "base_instructions": "Follow the selected workflow instructions.",
                "tool_mode": "direct"
            }]
        }))?,
    )?;
    std::fs::write(
        home.join("config.toml"),
        concat!(
            "model = 'lab-fixture-v1'\n",
            "model_provider = 'lab-fixture'\n",
            "model_catalog_json = 'catalog.json'\n",
            "[model_providers.lab-fixture]\n",
            "name = 'Lab fixture'\n",
            "base_url = 'http://127.0.0.1:1/v1'\n"
        ),
    )?;
    let config = ConfigBuilder::default()
        .codex_home(home.clone())
        .cli_overrides(restricted_overrides())
        .cloud_config_bundle(restricted_requirements())
        .harness_overrides(ConfigOverrides {
            cwd: Some(repository.clone()),
            ..Default::default()
        })
        .loader_overrides(codex_config::LoaderOverrides {
            ignore_project_config: true,
            ignore_user_and_project_exec_policy_rules: true,
            ..codex_config::LoaderOverrides::without_managed_config_for_tests()
        })
        .strict_config(true)
        .build()
        .await?;
    Ok((config, RuntimePaths::new(&repository, &home, &artifacts)?))
}

#[tokio::test]
#[cfg(target_os = "linux")]
async fn resolved_profile_rejects_unsafe_capabilities_and_writable_authority() -> Result<()> {
    let root = tempfile::tempdir()?;
    let (config, paths) = fixture(root.path()).await?;
    validate_runtime_config(&config, &paths, PhaseAccess::ReadOnly)?;
    let mut unsupported = config.clone();
    unsupported.features.enable(Feature::CodeMode)?;
    assert!(validate_runtime_config(&unsupported, &paths, PhaseAccess::ReadOnly).is_err());
    let mut unsafe_permissions = config.clone();
    unsafe_permissions.set_legacy_sandbox_policy(SandboxPolicy::DangerFullAccess)?;
    assert!(validate_runtime_config(&unsafe_permissions, &paths, PhaseAccess::ReadOnly).is_err());
    let mut widened = config;
    widened.set_legacy_sandbox_policy(SandboxPolicy::WorkspaceWrite {
        writable_roots: vec![codex_core_api::AbsolutePathBuf::from_absolute_path(
            paths.artifacts(),
        )?],
        network_access: false,
        exclude_tmpdir_env_var: true,
        exclude_slash_tmp: true,
    })?;
    assert!(validate_runtime_config(&widened, &paths, PhaseAccess::WorkspaceWrite).is_err());
    Ok(())
}

#[tokio::test]
#[cfg(target_os = "linux")]
async fn phase_write_profile_keeps_resumable_execution_disabled() -> Result<()> {
    let root = tempfile::tempdir()?;
    let (mut config, paths) = fixture(root.path()).await?;
    config.set_legacy_sandbox_policy(SandboxPolicy::WorkspaceWrite {
        writable_roots: Vec::new(),
        network_access: false,
        exclude_tmpdir_env_var: true,
        exclude_slash_tmp: true,
    })?;
    config.features.enable(Feature::ShellTool)?;
    validate_runtime_config(&config, &paths, PhaseAccess::WorkspaceWrite)?;
    // Normalization must retain the lab requirement after unrelated changes.
    config.features.enable(Feature::ViewImage)?;
    config.features.disable(Feature::ViewImage)?;
    assert_eq!(
        config.features.get().enabled_features(),
        vec![Feature::ShellTool, Feature::SkipHostSkillDiscovery]
    );
    assert!(validate_runtime_config(&config, &paths, PhaseAccess::ReadOnly).is_err());
    Ok(())
}

#[tokio::test]
#[cfg(target_os = "linux")]
async fn provider_endpoint_refuses_inline_secrets_and_insecure_remote_transport() -> Result<()> {
    let root = tempfile::tempdir()?;
    let (mut config, paths) = fixture(root.path()).await?;
    for endpoint in [
        "https://username:fixture-password@example.invalid/v1",
        "https://example.invalid/v1?api_key=fixture-secret",
        "https://example.invalid/v1#fragment",
        "http://example.invalid/v1",
        "file:///tmp/responses",
    ] {
        config.model_provider.base_url = Some(endpoint.to_string());
        assert!(validate_runtime_config(&config, &paths, PhaseAccess::ReadOnly).is_err());
    }
    for endpoint in [
        "https://example.invalid/v1",
        "http://localhost:1234/v1",
        "http://[::1]:1234/v1",
    ] {
        config.model_provider.base_url = Some(endpoint.to_string());
        validate_runtime_config(&config, &paths, PhaseAccess::ReadOnly)?;
    }
    Ok(())
}

#[tokio::test]
async fn pinned_catalog_rejects_prefix_fallback_and_extra_execution_modes() -> Result<()> {
    let root = tempfile::tempdir()?;
    let (config, _) = fixture(root.path()).await?;
    validate_model_catalog(&config)?;
    let mut renamed = config.clone();
    renamed.model = Some("lab-fixture-v1-latest".to_string());
    assert!(validate_model_catalog(&renamed).is_err());
    let mut code_mode = config.clone();
    code_mode
        .model_catalog
        .as_mut()
        .context("fixture catalog")?
        .models[0]
        .tool_mode = Some(ToolMode::CodeMode);
    assert!(validate_model_catalog(&code_mode).is_err());
    let mut no_commands = config.clone();
    no_commands
        .model_catalog
        .as_mut()
        .context("fixture catalog")?
        .models[0]
        .shell_type = ConfigShellToolType::Disabled;
    assert_eq!(
        validate_model_catalog(&no_commands)
            .unwrap_err()
            .to_string(),
        "catalog must enable command tools for verification evidence"
    );
    let mut ambiguous = config;
    let catalog = ambiguous
        .model_catalog
        .as_mut()
        .context("fixture catalog")?;
    catalog.models.push(catalog.models[0].clone());
    assert!(validate_model_catalog(&ambiguous).is_err());
    Ok(())
}

#[tokio::test]
async fn context_caps_use_selected_expanded_model_instructions_and_custom_compaction() -> Result<()>
{
    let root = tempfile::tempdir()?;
    let (mut config, _) = fixture(root.path()).await?;
    let messages = config
        .model_catalog
        .as_mut()
        .context("fixture catalog")?
        .models[0]
        .model_messages
        .as_mut()
        .context("fixture model messages")?;
    messages.instructions_template = Some("{{ personality }}{{ personality }}".to_string());
    messages.instructions_variables = Some(ModelInstructionsVariables {
        personality_default: Some("é".repeat(2049)),
        personality_friendly: Some("friendly".to_string()),
        personality_pragmatic: None,
    });
    config.personality = None;
    assert!(
        validate_model_catalog(&config)
            .unwrap_err()
            .to_string()
            .contains("resolved model instructions")
    );
    config.personality = Some(Personality::Friendly);
    validate_model_catalog(&config)?;
    // The configured override wins over even an oversized selected template.
    config.personality = None;
    config.base_instructions = Some("x".repeat(8192));
    validate_model_catalog(&config)?;
    config.base_instructions = Some("x".repeat(8193));
    assert!(
        validate_model_catalog(&config)
            .unwrap_err()
            .to_string()
            .contains("resolved model instructions")
    );
    config.base_instructions = Some("bounded override".to_string());
    config.compact_prompt = Some("x".repeat(8193));
    assert!(
        validate_model_catalog(&config)
            .unwrap_err()
            .to_string()
            .contains("custom compaction prompt")
    );
    config.compact_prompt = Some("x".repeat(8192));
    validate_model_catalog(&config)?;
    Ok(())
}

#[tokio::test]
async fn custom_phase_permission_messages_share_a_bounded_budget() -> Result<()> {
    let root = tempfile::tempdir()?;
    let (mut config, _) = fixture(root.path()).await?;
    let messages = config
        .model_catalog
        .as_mut()
        .context("fixture catalog")?
        .models[0]
        .model_messages
        .as_mut()
        .context("fixture model messages")?;
    messages.permissions = Some(PermissionMessages {
        read_only: Some("x".repeat(4096)),
        workspace_write: None,
        danger_full_access: None,
    });
    messages.approvals = Some(ApprovalMessages {
        never: Some("x".repeat(4097)),
        on_request: None,
        on_request_auto_review: None,
        unless_trusted: None,
    });
    assert!(
        validate_model_catalog(&config)
            .unwrap_err()
            .to_string()
            .contains("custom phase permission instructions")
    );
    config
        .model_catalog
        .as_mut()
        .context("fixture catalog")?
        .models[0]
        .model_messages
        .as_mut()
        .context("fixture model messages")?
        .approvals
        .as_mut()
        .context("fixture approval messages")?
        .never = Some("x".repeat(4096));
    validate_model_catalog(&config)?;
    Ok(())
}

#[test]
fn canonical_paths_reject_authority_inside_repository_and_symlink_aliases() -> Result<()> {
    let root = tempfile::tempdir()?;
    let repository = root.path().join("repo");
    let home = root.path().join("home");
    let artifacts = repository.join("runs");
    std::fs::create_dir_all(&artifacts)?;
    std::fs::create_dir(&home)?;
    assert!(RuntimePaths::new(&repository, &home, &artifacts).is_err());
    #[cfg(unix)]
    {
        let alias = root.path().join("alias");
        std::os::unix::fs::symlink(&artifacts, &alias)?;
        assert!(RuntimePaths::new(&repository, &home, &alias).is_err());
    }
    Ok(())
}

#[test]
fn context_validation_refuses_lossy_oversize_delivery() -> Result<()> {
    validate_phase_context("frozen role instructions", "task")?;
    assert!(validate_phase_context("", "task").is_err());
    assert!(validate_phase_context("instructions", &"é".repeat(4097)).is_err());
    assert!(validate_phase_context(&"x".repeat(8193), "task").is_err());
    Ok(())
}
