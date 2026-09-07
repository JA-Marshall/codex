use std::path::Path;
use std::path::PathBuf;
use std::process::Stdio;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Arg0DispatchPaths;
use codex_lab::PlanRevision;
use codex_lab_runtime::RunOptions;
use serde_json::json;
use sha2::Digest;
use tempfile::TempDir;

pub struct Fixture {
    _root: TempDir,
    pub repository: PathBuf,
    pub home: PathBuf,
    pub runs: PathBuf,
    pub instruction_root: PathBuf,
    pub workflow_catalog: String,
    pub commit: String,
    pub paths: Arg0DispatchPaths,
}

impl Fixture {
    pub async fn new(endpoint: &str) -> Result<Self> {
        let root = tempfile::tempdir()?;
        let repository = root.path().join("repository");
        let home = root.path().join("home");
        let runs = root.path().join("runs");
        let instruction_root = root.path().join("instructions");
        for directory in [&repository, &home, &runs, &instruction_root] {
            std::fs::create_dir(directory)?;
        }
        std::fs::write(
            repository.join("README.md"),
            "Fixture task: create greeting.txt containing hello.\n",
        )?;
        git(&repository, &["init", "--quiet", "-b", "main"]).await?;
        git(&repository, &["add", "README.md"]).await?;
        git(
            &repository,
            &[
                "-c",
                "user.name=Lab test",
                "-c",
                "user.email=lab@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
        )
        .await?;
        let commit = git(&repository, &["rev-parse", "HEAD"])
            .await?
            .trim()
            .to_string();
        let model_catalog = json!({"models": [{
            "slug":"lab-fixture-v1", "display_name":"Lab fixture", "description":null,
            "supported_reasoning_levels":[], "shell_type":"unified_exec", "visibility":"list",
            "supported_in_api":true, "priority":0, "availability_nux":null, "upgrade":null,
            "support_verbosity":false, "default_verbosity":null, "apply_patch_tool_type":"freeform",
            "truncation_policy":{"mode":"bytes","limit":8192}, "context_window":32768,
            "experimental_supported_tools":[], "include_apps_usage_instructions":false,
            "tool_mode":"direct", "model_messages":{
                "instructions_template":"You are a coding assistant. Follow the supplied workflow instructions.",
                "instructions_variables":null, "approvals":null, "collaboration_modes":null,
                "auto_review":null, "permissions":null, "multi_agent":null
            }
        }]});
        std::fs::write(
            home.join("catalog.json"),
            serde_json::to_vec(&model_catalog)?,
        )?;
        let config = format!(
            "model = 'lab-fixture-v1'\nmodel_provider = 'lab-fixture'\nmodel_catalog_json = 'catalog.json'\n\
             [model_providers.lab-fixture]\nname = 'Lab fixture'\nbase_url = '{endpoint}/v1'\n\
             request_max_retries = 0\nstream_max_retries = 0\nstream_idle_timeout_ms = 5000\n"
        );
        std::fs::write(home.join("config.toml"), config)?;
        let mut workflow_catalog = "schema_version = 1\n".to_string();
        for (role, instructions) in [
            (
                "planner",
                "Research and produce the requested concise canonical plan. Never implement before approval.",
            ),
            (
                "executor",
                "Implement exactly the approved plan. Request an amendment if its assumptions are invalid.",
            ),
            (
                "verifier",
                "Run the approved verification and cite actual completed exec_command call IDs.",
            ),
        ] {
            let directory = instruction_root.join(role);
            std::fs::create_dir(&directory)?;
            let text = format!(
                "---\nname: lab-{role}\ndescription: Pinned test procedure\n---\n{instructions}\n"
            );
            std::fs::write(directory.join("SKILL.md"), text.as_bytes())?;
            let hash = format!("{:x}", sha2::Sha256::digest(text.as_bytes()));
            workflow_catalog.push_str(&format!(
                "\n[skills.\"{role}/test\"]\npath = '{role}'\nsha256 = '{hash}'\n"
            ));
        }
        workflow_catalog.push_str(concat!(
            "\n[workflows.base]\napproval = 'human_required'\nplan.renderer = 'markdown'\n",
            "roles.planner = 'planner/test'\nroles.executor = 'executor/test'\nroles.verifier = 'verifier/test'\n",
            "\n[workflows.md]\nextends = 'base'\n\n[workflows.json]\nextends = 'base'\nplan.renderer = 'json'\n"
        ));
        let binary = codex_utils_cargo_bin::cargo_bin("codex-lab")?.canonicalize()?;
        let helper = root.path().join("codex-linux-sandbox");
        std::os::unix::fs::symlink(&binary, &helper)?;
        let paths = Arg0DispatchPaths {
            codex_self_exe: Some(binary),
            codex_linux_sandbox_exe: Some(helper),
            main_execve_wrapper_exe: None,
        };
        Ok(Self {
            _root: root,
            repository,
            home,
            runs,
            instruction_root,
            workflow_catalog,
            commit,
            paths,
        })
    }

    pub fn options(&self, id: &str, workflow: &str, plan: Option<PlanRevision>) -> RunOptions {
        RunOptions {
            repository: self.repository.clone(),
            repository_commit: self.commit.clone(),
            codex_home: self.home.clone(),
            runs_directory: self.runs.clone(),
            run_id: id.to_string(),
            task: "Create greeting.txt containing hello followed by a newline.".to_string(),
            workflow_catalog: self.workflow_catalog.clone(),
            instruction_root: self.instruction_root.clone(),
            workflow: workflow.to_string(),
            plan,
        }
    }
}

pub fn plan(revision: u32) -> Result<PlanRevision> {
    Ok(serde_json::from_value(json!({
        "schema_version":1, "plan_id":"task-plan", "revision":revision,
        "goal":"Create a tested greeting file", "assumptions":["README.md describes the fixture task"],
        "steps":[{"id":"S01","title":"Create greeting","instructions":"Create greeting.txt with hello and a newline.",
            "affected_files":["greeting.txt"],"depends_on":[],"acceptance_criteria":["AC01"],"verification":["V01"]}],
        "risks":[], "acceptance_criteria":[{"id":"AC01","description":"greeting.txt contains hello and unapproved files do not exist"}],
        "verification_strategy":[{"id":"V01","description":"Run test against greeting.txt contents and check forbidden.txt is absent."}],
        "discoveries":[],"blockers":[]
    }))?)
}

pub async fn git(repository: &Path, arguments: &[&str]) -> Result<String> {
    let output = tokio::process::Command::new("git")
        .args(arguments)
        .current_dir(repository)
        .stdin(Stdio::null())
        .output()
        .await?;
    ensure!(
        output.status.success(),
        "git fixture command failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).context("git returned non-UTF8 output")
}
