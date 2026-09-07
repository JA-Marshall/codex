use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::AskForApproval;
use codex_core_api::Config;
use codex_core_api::Feature;
use codex_core_api::WebSearchMode;
use codex_protocol::config_types::ShellEnvironmentPolicyInherit;
use codex_protocol::models::PermissionProfile;
use codex_protocol::openai_models::ConfigShellToolType;
use codex_protocol::openai_models::ModelInfo;
use codex_protocol::openai_models::ToolMode;
use codex_protocol::protocol::MultiAgentVersion;
use codex_protocol::protocol::SandboxPolicy;

use crate::context::MAX_PHASE_FRAGMENT_BYTES;

/// Filesystem authority is held outside the repository in the host process.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuntimePaths {
    repository: PathBuf,
    codex_home: PathBuf,
    artifacts: PathBuf,
}

impl RuntimePaths {
    pub fn new(repository: &Path, codex_home: &Path, artifacts: &Path) -> Result<Self> {
        let paths = Self {
            repository: repository
                .canonicalize()
                .context("canonicalize repository")?,
            codex_home: codex_home
                .canonicalize()
                .context("canonicalize runtime home")?,
            artifacts: artifacts.canonicalize().context("canonicalize artifacts")?,
        };
        for path in [&paths.repository, &paths.codex_home, &paths.artifacts] {
            ensure!(path.is_dir(), "runtime paths must be existing directories");
        }
        for protected in [&paths.codex_home, &paths.artifacts] {
            ensure!(
                !protected.starts_with(&paths.repository)
                    && !paths.repository.starts_with(protected),
                "repository and authority directories must not overlap"
            );
        }
        Ok(paths)
    }

    pub fn repository(&self) -> &Path {
        &self.repository
    }

    pub fn codex_home(&self) -> &Path {
        &self.codex_home
    }

    pub fn artifacts(&self) -> &Path {
        &self.artifacts
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PhaseAccess {
    ReadOnly,
    WorkspaceWrite,
}

impl PhaseAccess {
    pub(crate) fn policy(self) -> SandboxPolicy {
        match self {
            Self::ReadOnly => SandboxPolicy::ReadOnly {
                network_access: false,
            },
            Self::WorkspaceWrite => SandboxPolicy::WorkspaceWrite {
                writable_roots: Vec::new(),
                network_access: false,
                exclude_tmpdir_env_var: true,
                exclude_slash_tmp: true,
            },
        }
    }
}

/// Validate the effective configuration, including constrained permissions.
/// This is deliberately a restricted profile, not a best-effort compatibility
/// layer for arbitrary Codex configurations.
pub fn validate_runtime_config(
    config: &Config,
    paths: &RuntimePaths,
    access: PhaseAccess,
) -> Result<()> {
    ensure!(
        cfg!(target_os = "linux"),
        "lab runtime currently requires Linux"
    );
    ensure!(
        config.cwd.as_path() == paths.repository(),
        "unexpected runtime cwd"
    );
    ensure!(
        config.codex_home.as_path() == paths.codex_home(),
        "unexpected runtime home"
    );
    ensure!(
        matches!(
            config.permissions.permission_profile(),
            PermissionProfile::Managed { .. }
        ),
        "lab runtime requires mechanically enforced managed permissions"
    );
    ensure!(
        config.legacy_sandbox_policy() == access.policy(),
        "effective permissions differ from the restricted phase policy"
    );
    ensure!(
        *config.permissions.approval_policy.get() == AskForApproval::Never,
        "lab profile does not support tool permission escalation"
    );
    ensure!(
        !config.permissions.network_sandbox_policy().is_enabled(),
        "tool networking is unsupported"
    );
    ensure!(
        config.permissions.network.is_none(),
        "managed network proxies are unsupported"
    );
    let filesystem = config.permissions.file_system_sandbox_policy();
    ensure!(
        !filesystem.has_full_disk_write_access(),
        "unrestricted filesystem access is unsupported"
    );
    for root in filesystem.get_writable_roots_with_cwd(paths.repository()) {
        let canonical = root.root.as_path().canonicalize()?;
        ensure!(
            canonical == paths.repository(),
            "unexpected effective writable root"
        );
        for protected in [paths.codex_home(), paths.artifacts()] {
            ensure!(
                !protected.starts_with(&canonical),
                "authority is model-writable"
            );
        }
    }
    for feature in config.features.get().enabled_features() {
        let allowed = match feature {
            Feature::SkipHostSkillDiscovery => true,
            Feature::ShellTool => access == PhaseAccess::WorkspaceWrite,
            _ => false,
        };
        ensure!(allowed, "unsupported effective feature: {}", feature.key());
    }
    ensure!(
        config.features.enabled(Feature::SkipHostSkillDiscovery),
        "ambient skill discovery must be disabled"
    );
    ensure!(!config.agents_enabled, "subagents are unsupported");
    ensure!(
        config.mcp_servers.get().is_empty(),
        "MCP servers are unsupported"
    );
    ensure!(
        !config.orchestrator_mcp_enabled && !config.orchestrator_skills_enabled,
        "orchestrator capabilities are unsupported"
    );
    ensure!(
        !config.include_skill_instructions && !config.bundled_skills_enabled(),
        "ambient skills are unsupported"
    );
    ensure!(
        config.project_doc_max_bytes == 0,
        "ambient project instruction loading must be disabled"
    );
    ensure!(
        config.notify.is_none(),
        "notification commands are unsupported"
    );
    let effective = config.config_layer_stack.effective_config();
    ensure!(
        effective.get("hooks").is_none(),
        "configured lifecycle hooks are unsupported"
    );
    ensure!(
        config
            .config_layer_stack
            .requirements()
            .managed_hooks
            .is_none(),
        "managed lifecycle hooks are unsupported"
    );
    ensure!(
        effective
            .get("plugins")
            .and_then(toml::Value::as_table)
            .is_none_or(toml::map::Map::is_empty),
        "configured plugins are unsupported"
    );
    ensure!(
        !config.bypass_hook_trust,
        "hook trust bypass is unsupported"
    );
    ensure!(
        !config.memories.generate_memories && !config.memories.use_memories,
        "memory workflows are unsupported"
    );
    ensure!(
        *config.web_search_mode.get() == WebSearchMode::Disabled,
        "provider web tools are unsupported"
    );
    ensure!(
        !config.update_plan_enabled && !config.experimental_request_user_input_enabled,
        "upstream planning and input tools are not lab authority"
    );
    ensure!(
        !config.permissions.allow_login_shell
            && !config.permissions.shell_environment_policy.use_profile,
        "shell profiles are unsupported"
    );
    ensure!(
        config.permissions.shell_environment_policy.inherit == ShellEnvironmentPolicyInherit::None,
        "shell environment inheritance is unsupported"
    );
    ensure!(
        config
            .permissions
            .shell_environment_policy
            .r#set
            .keys()
            .all(|key| key == "PATH"),
        "only a pinned PATH may be provided to model shell commands"
    );
    let provider = &config.model_provider;
    ensure!(
        !provider.is_openai() && !provider.requires_openai_auth,
        "select a distinct custom Responses provider"
    );
    let endpoint = url::Url::parse(
        provider
            .base_url
            .as_deref()
            .context("custom provider base_url is required")?,
    )
    .map_err(|_| anyhow::anyhow!("custom provider base_url must be an absolute URL"))?;
    ensure!(
        endpoint.username().is_empty()
            && endpoint.password().is_none()
            && endpoint.query().is_none()
            && endpoint.fragment().is_none(),
        "provider URL credentials, query parameters and fragments are unsupported"
    );
    let loopback = endpoint.host_str().is_some_and(|host| {
        host == "localhost"
            || host
                .parse::<std::net::IpAddr>()
                .is_ok_and(|address| address.is_loopback())
            || host == "[::1]"
    });
    ensure!(
        endpoint.scheme() == "https" || (endpoint.scheme() == "http" && loopback),
        "provider requires HTTPS except for local mock servers"
    );
    ensure!(
        provider.auth.is_none() && provider.aws.is_none(),
        "command-backed and AWS provider authentication are unsupported"
    );
    ensure!(
        provider.experimental_bearer_token.is_none(),
        "use an environment key instead of an inline credential"
    );
    ensure!(
        provider
            .http_headers
            .as_ref()
            .is_none_or(std::collections::HashMap::is_empty),
        "inline provider headers are unsupported"
    );
    ensure!(
        provider
            .query_params
            .as_ref()
            .is_none_or(std::collections::HashMap::is_empty),
        "provider query parameters are unsupported"
    );
    ensure!(
        !provider.supports_websockets && !provider.supports_standalone_web_search,
        "optional provider transports/tools are unsupported"
    );
    validate_model_catalog(config)?;
    Ok(())
}

/// Require exact catalog identity so unknown-model GPT fallback cannot silently
/// change tool shape, instructions, or context limits in an experiment.
pub fn validate_model_catalog(config: &Config) -> Result<&ModelInfo> {
    let model = config
        .model
        .as_deref()
        .context("pin an explicit model ID")?;
    let catalog = config
        .model_catalog
        .as_ref()
        .context("pin model_catalog_json")?;
    ensure!(
        catalog.models.len() == 1,
        "restricted profile requires a single-model catalog"
    );
    let entry = &catalog.models[0];
    ensure!(
        entry.slug == model,
        "catalog model must match the model ID exactly"
    );
    ensure!(
        !entry.used_fallback_model_metadata,
        "fallback model metadata is unsupported"
    );
    ensure!(
        entry
            .resolved_context_window()
            .is_some_and(|limit| limit > 0),
        "catalog requires a positive context window"
    );
    ensure!(
        entry.shell_type == ConfigShellToolType::UnifiedExec,
        "catalog must enable command tools for verification evidence"
    );
    ensure!(
        entry.experimental_supported_tools.is_empty(),
        "experimental provider tools are unsupported"
    );
    ensure!(
        matches!(entry.tool_mode, None | Some(ToolMode::Direct)),
        "code mode is unsupported"
    );
    ensure!(
        matches!(
            entry.multi_agent_version,
            None | Some(MultiAgentVersion::Disabled)
        ),
        "model-selected subagents are unsupported"
    );
    ensure!(
        !entry.supports_search_tool
            && !entry.supports_experimental_context
            && !entry.use_responses_lite,
        "experimental model capabilities are unsupported"
    );
    ensure!(
        entry.auto_review_model_override.is_none(),
        "auxiliary model overrides are unsupported"
    );
    ensure!(
        !entry.include_skills_usage_instructions
            && !entry.include_plugin_usage_instructions
            && !entry.include_apps_usage_instructions,
        "catalog ambient capability instructions are unsupported"
    );
    // Fresh threads have no historical base instructions. Match upstream's
    // override precedence and its actual personality-template expansion.
    let base_instructions = config
        .base_instructions
        .clone()
        .unwrap_or_else(|| entry.get_model_instructions(config.personality));
    ensure!(
        base_instructions.len() <= MAX_PHASE_FRAGMENT_BYTES,
        "resolved model instructions exceed the context byte limit"
    );
    ensure!(
        config
            .compact_prompt
            .as_ref()
            .is_none_or(|prompt| prompt.len() <= MAX_PHASE_FRAGMENT_BYTES),
        "custom compaction prompt exceeds the context byte limit"
    );
    if let Some(messages) = &entry.model_messages {
        let approval = messages
            .approvals
            .as_ref()
            .and_then(|messages| messages.never.as_deref());
        let read_only = messages
            .permissions
            .as_ref()
            .and_then(|messages| messages.read_only.as_deref());
        let workspace_write = messages
            .permissions
            .as_ref()
            .and_then(|messages| messages.workspace_write.as_deref());
        let permission_bytes = [approval, read_only, workspace_write]
            .into_iter()
            .flatten()
            .fold(0_usize, |total, text| total.saturating_add(text.len()));
        ensure!(
            permission_bytes <= MAX_PHASE_FRAGMENT_BYTES,
            "custom phase permission instructions exceed the context byte limit"
        );
    }
    Ok(entry)
}
