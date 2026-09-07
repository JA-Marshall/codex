use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::io::Write;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_config::CloudConfigBundle;
use codex_config::CloudConfigBundleLoader;
use codex_config::CloudRequirementsFragment;
use codex_config::CloudRequirementsTomlBundle;
use codex_config::LoaderOverrides;
use codex_core::config::ConfigBuilder;
use codex_core::config::ConfigOverrides;
use codex_core_api::Arg0DispatchPaths;
use codex_core_api::AuthManager;
use codex_core_api::Config;
use codex_core_api::EnvironmentManager;
use codex_core_api::ExecServerRuntimePaths;
use codex_core_api::Feature;
use codex_features::FEATURES;
use codex_features::Features;
use tokio::process::Command;
use toml::Value;

use crate::preflight::PhaseAccess;
use crate::preflight::RuntimePaths;
use crate::preflight::validate_runtime_config;

/// Validated host inputs. Configuration is immutable after preparation; phase
/// access changes are constrained, revalidated clones of this base.
pub struct PreparedRuntime {
    pub(crate) config: Config,
    pub(crate) paths: RuntimePaths,
    pub(crate) environments: Arc<EnvironmentManager>,
    pub(crate) auth: Arc<AuthManager>,
}

impl PreparedRuntime {
    pub async fn load(
        config_home: &Path,
        repository: &Path,
        artifacts: &Path,
        mut cli_overrides: Vec<(String, Value)>,
        arg0_paths: Arg0DispatchPaths,
    ) -> Result<Self> {
        let paths = RuntimePaths::new(repository, config_home, artifacts)?;
        // This host owns a fixed restricted capability profile. Provider and
        // model settings still use the normal configuration loader.
        cli_overrides.extend(restricted_overrides());
        let builder = ConfigBuilder::default()
            .codex_home(paths.codex_home().to_path_buf())
            .cli_overrides(cli_overrides)
            .harness_overrides(ConfigOverrides {
                cwd: Some(paths.repository().to_path_buf()),
                codex_self_exe: arg0_paths.codex_self_exe,
                codex_linux_sandbox_exe: arg0_paths.codex_linux_sandbox_exe,
                main_execve_wrapper_exe: arg0_paths.main_execve_wrapper_exe,
                ..Default::default()
            })
            .loader_overrides(LoaderOverrides {
                ignore_project_config: true,
                ignore_user_and_project_exec_policy_rules: true,
                ..Default::default()
            })
            .strict_config(true);
        // First retain and inspect existing managed requirements. The local lab
        // requirement may only add restrictions, never overturn an existing
        // requirement selecting a capability the restricted host disables.
        let inherited = builder.clone().build().await?;
        let required_off = host_required_off_features();
        ensure!(
            inherited
                .config_layer_stack
                .requirements_toml()
                .feature_requirements
                .as_ref()
                .is_none_or(
                    |requirements| requirements.entries.iter().all(|(key, enabled)| {
                        !enabled
                            || codex_features::feature_for_key(key)
                                .is_none_or(|feature| !required_off.contains(&feature))
                    })
                ),
            "managed requirements conflict with restricted lab capabilities"
        );
        let config = builder
            .cloud_config_bundle(restricted_requirements())
            .build()
            .await?;
        validate_runtime_config(&config, &paths, PhaseAccess::ReadOnly)?;
        ensure!(
            config
                .developer_instructions
                .as_deref()
                .is_none_or(str::is_empty),
            "role instructions must come from the frozen workflow"
        );
        for executable in [
            config.codex_self_exe.as_deref(),
            config.codex_linux_sandbox_exe.as_deref(),
            config.main_execve_wrapper_exe.as_deref(),
        ]
        .into_iter()
        .flatten()
        {
            ensure!(
                !executable.canonicalize()?.starts_with(paths.repository()),
                "Codex runtime helpers must be outside the model-writable repository"
            );
        }
        let runtime_paths = ExecServerRuntimePaths::from_optional_paths(
            config.codex_self_exe.clone(),
            config.codex_linux_sandbox_exe.clone(),
        )?;
        let environments = Arc::new(
            EnvironmentManager::from_codex_home(
                &config.codex_home,
                Some(runtime_paths),
                config.http_client_factory(),
            )
            .await?,
        );
        ensure!(
            environments.default_environment_ids() == ["local"],
            "only the local execution environment is supported"
        );
        ensure!(
            environments.try_local_environment().is_some(),
            "local executor is unavailable"
        );
        verify_sandbox(&config, &paths, PhaseAccess::ReadOnly).await?;
        let mut writable = config.clone();
        writable.set_legacy_sandbox_policy(PhaseAccess::WorkspaceWrite.policy())?;
        writable.features.enable(Feature::ShellTool)?;
        validate_runtime_config(&writable, &paths, PhaseAccess::WorkspaceWrite)?;
        verify_sandbox(&writable, &paths, PhaseAccess::WorkspaceWrite).await?;
        let auth =
            AuthManager::shared_from_config(&config, /*enable_codex_api_key_env*/ false).await?;
        Ok(Self {
            config,
            paths,
            environments,
            auth,
        })
    }

    pub fn config(&self) -> &Config {
        &self.config
    }

    pub fn paths(&self) -> &RuntimePaths {
        &self.paths
    }
}

/// Reuses the existing requirements transport for a local host constraint. This
/// bundle is constructed in memory and never fetched from a cloud service. Its
/// explicit provenance identifies the lab, not an administrator or provider.
pub fn restricted_requirements() -> CloudConfigBundleLoader {
    CloudConfigBundleLoader::new(async {
        let mut contents = "[features]\n".to_string();
        for feature in host_required_off_features() {
            contents.push_str(&format!("{} = false\n", feature.key()));
        }
        Ok(Some(CloudConfigBundle {
            requirements_toml: CloudRequirementsTomlBundle {
                enterprise_managed: vec![CloudRequirementsFragment {
                    id: "codex-lab-local-host-v1".to_string(),
                    name:
                        "Codex Lab local host: one-shot execution and disabled compatibility flags"
                            .to_string(),
                    contents,
                }],
            },
            ..Default::default()
        }))
    })
}

/// Upstream deliberately ignores ordinary overrides for some compatibility
/// flags. Derive the residual set from its feature machinery instead of copying
/// that evolving list. Managed constraints also select one-shot execution.
fn host_required_off_features() -> BTreeSet<Feature> {
    let overrides = FEATURES
        .iter()
        .map(|feature| (feature.key.to_string(), false))
        .collect::<BTreeMap<_, _>>();
    let mut configured = Features::with_defaults();
    configured.apply_map(&overrides);
    let mut residual = configured
        .enabled_features()
        .into_iter()
        .collect::<BTreeSet<_>>();
    residual.insert(Feature::UnifiedExec);
    residual
}

/// The resolved overrides are retained in the upstream configuration stack.
/// Unknown future features remain off because the complete upstream registry is
/// enumerated; managed requirements that force capabilities on fail validation.
pub fn restricted_overrides() -> Vec<(String, Value)> {
    let mut overrides = FEATURES
        .iter()
        .map(|feature| {
            (
                format!("features.{}", feature.key),
                Value::Boolean(feature.id == Feature::SkipHostSkillDiscovery),
            )
        })
        .collect::<Vec<_>>();
    for (key, value) in [
        ("approval_policy", Value::String("never".into())),
        ("sandbox_mode", Value::String("read-only".into())),
        ("web_search", Value::String("disabled".into())),
        ("agents.enabled", Value::Boolean(false)),
        ("skills.include_instructions", Value::Boolean(false)),
        ("skills.bundled.enabled", Value::Boolean(false)),
        ("orchestrator.skills.enabled", Value::Boolean(false)),
        ("orchestrator.mcp.enabled", Value::Boolean(false)),
        ("project_doc_max_bytes", Value::Integer(0)),
        ("memories.generate_memories", Value::Boolean(false)),
        ("memories.use_memories", Value::Boolean(false)),
        ("tools.update_plan.enabled", Value::Boolean(false)),
        (
            "tools.experimental_request_user_input.enabled",
            Value::Boolean(false),
        ),
        (
            "shell_environment_policy.inherit",
            Value::String("none".into()),
        ),
        (
            "shell_environment_policy.ignore_default_excludes",
            Value::Boolean(false),
        ),
        (
            "shell_environment_policy.experimental_use_profile",
            Value::Boolean(false),
        ),
        ("allow_login_shell", Value::Boolean(false)),
        ("include_apps_instructions", Value::Boolean(false)),
        (
            "include_collaboration_mode_instructions",
            Value::Boolean(false),
        ),
    ] {
        overrides.push((key.to_string(), value));
    }
    overrides.push((
        "shell_environment_policy.set".to_string(),
        Value::Table(toml::map::Map::from_iter([(
            "PATH".to_string(),
            Value::String("/usr/local/bin:/usr/bin:/bin".to_string()),
        )])),
    ));
    overrides
}

/// Exercise the same upstream Linux helper and effective permission profile
/// used by model commands. This verifies protected roots are mounted read-only
/// and the requested repository access is available; it writes no repository
/// files and never degrades to unsandboxed execution.
pub(crate) async fn verify_sandbox(
    config: &Config,
    paths: &RuntimePaths,
    access: PhaseAccess,
) -> Result<()> {
    let helper = config
        .codex_linux_sandbox_exe
        .as_deref()
        .context("Linux sandbox helper is not configured; initialize arg0 dispatch")?;
    ensure!(helper.is_file(), "Linux sandbox helper does not exist");
    let mut home_probe = tempfile::NamedTempFile::new_in(paths.codex_home())?;
    let mut artifact_probe = tempfile::NamedTempFile::new_in(paths.artifacts())?;
    let sentinel = b"codex-lab-authority-probe\n";
    home_probe.write_all(sentinel)?;
    artifact_probe.write_all(sentinel)?;
    home_probe.as_file().sync_all()?;
    artifact_probe.as_file().sync_all()?;
    // All interpolated inputs are argv values, never shell source. The fixed
    // script must run successfully while both real write syscalls are denied.
    let script = concat!(
        "if { printf changed >> \"$1\"; } 2>/dev/null; then exit 91; fi; ",
        "if { printf changed >> \"$2\"; } 2>/dev/null; then exit 92; fi; ",
        "test ! -w \"$1\" && test ! -w \"$2\" || exit 93; ",
        "if [ \"$4\" = readonly ]; then test ! -w \"$3\"; else test -w \"$3\"; fi"
    );
    let mut command = Command::new(helper);
    command
        .arg("--sandbox-policy-cwd")
        .arg(paths.repository())
        .arg("--permission-profile")
        .arg(serde_json::to_string(
            &config.permissions.effective_permission_profile(),
        )?)
        .arg("--")
        .arg("/bin/sh")
        .arg("-c")
        .arg(script)
        .arg("lab-sandbox-preflight")
        .arg(home_probe.path())
        .arg(artifact_probe.path())
        .arg(paths.repository())
        .arg(match access {
            PhaseAccess::ReadOnly => "readonly",
            PhaseAccess::WorkspaceWrite => "write",
        })
        .current_dir(paths.repository())
        .env_clear()
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    let output = tokio::time::timeout(Duration::from_secs(30), command.output())
        .await
        .context("sandbox preflight timed out")??;
    ensure!(
        std::fs::read(home_probe.path())? == sentinel
            && std::fs::read(artifact_probe.path())? == sentinel,
        "sandbox failed to protect authoritative files"
    );
    ensure!(
        output.status.success(),
        "Linux sandbox preflight failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}
