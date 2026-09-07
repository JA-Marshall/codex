use std::collections::BTreeMap;
use std::marker::PhantomData;
use std::sync::Arc;

use codex_exec_server::LocalFileSystem;
use codex_extension_api::ExtensionData;
use codex_extension_api::ToolContributor;
use codex_file_system::FileSystemSandboxContext;
use codex_lab_runtime::RepositoryTools;
use codex_protocol::models::PermissionProfile;
use codex_protocol::protocol::SandboxPolicy;
use codex_protocol::protocol::TruncationPolicy;
use codex_tools::ConversationHistory;
use codex_tools::FunctionCallError;
use codex_tools::NoopTurnItemEmitter;
use codex_tools::ToolCall;
use codex_tools::ToolCallSource;
use codex_tools::ToolEnvironment;
use codex_tools::ToolExecutor;
use codex_tools::ToolName;
use codex_tools::ToolPayload;
use codex_utils_absolute_path::AbsolutePathBuf;
use codex_utils_path_uri::PathUri;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use tempfile::TempDir;

type TestResult = Result<(), Box<dyn std::error::Error>>;

struct Fixture {
    directory: TempDir,
    root: AbsolutePathBuf,
    tools: Vec<Arc<dyn for<'call> ToolExecutor<ToolCall<'call>>>>,
}

impl Fixture {
    fn new() -> Result<Self, Box<dyn std::error::Error>> {
        let directory = tempfile::tempdir()?;
        let root = AbsolutePathBuf::from_absolute_path(directory.path())?;
        let tools = RepositoryTools::new(root.clone()).tools(
            &ExtensionData::new("session"),
            &ExtensionData::new("thread"),
        );
        Ok(Self {
            directory,
            root,
            tools,
        })
    }

    fn call(&self, name: &str, arguments: Value) -> ToolCall<'static> {
        ToolCall {
            turn_id: "turn-1".to_string(),
            call_id: "call-1".to_string(),
            tool_name: ToolName::plain(name),
            model: "mock".to_string(),
            codex_turn_metadata: None,
            truncation_policy: TruncationPolicy::Bytes(64 * 1024),
            source: ToolCallSource::Direct,
            conversation_history: ConversationHistory::default(),
            turn_item_emitter: Arc::new(NoopTurnItemEmitter),
            environments: vec![ToolEnvironment {
                environment_id: "local".to_string(),
                cwd: self.root.clone(),
                file_system: Arc::new(LocalFileSystem::unsandboxed()),
                file_system_sandbox_context: FileSystemSandboxContext::from_permission_profile(
                    PermissionProfile::Disabled,
                ),
                _lifetime: PhantomData,
            }],
            payload: ToolPayload::Function {
                arguments: arguments.to_string(),
            },
        }
    }

    async fn invoke(&self, call: ToolCall<'static>) -> Result<Value, FunctionCallError> {
        let tool = self
            .tools
            .iter()
            .find(|tool| tool.tool_name() == call.tool_name)
            .ok_or_else(|| FunctionCallError::Fatal("missing fixture tool".to_string()))?;
        let payload = call.payload.clone();
        Ok(tool.handle(call).await?.code_mode_result(&payload))
    }
}

#[tokio::test]
async fn reads_utf8_and_lists_only_immediate_entries() -> TestResult {
    let fixture = Fixture::new()?;
    std::fs::create_dir(fixture.directory.path().join("src"))?;
    std::fs::write(
        fixture.directory.path().join("src/main.rs"),
        "fn main() {}\n",
    )?;
    std::fs::write(fixture.directory.path().join("README.md"), "# Café\n")?;
    let read = fixture
        .invoke(fixture.call("lab_repo_read", json!({"path": "README.md"})))
        .await?;
    let list = fixture
        .invoke(fixture.call("lab_repo_list", json!({"path": "."})))
        .await?;
    insta::assert_json_snapshot!(BTreeMap::from([("read", read), ("list", list)]), @r###"
    {
      "list": {
        "entries": [
          {
            "kind": "file",
            "name": "README.md"
          },
          {
            "kind": "directory",
            "name": "src"
          }
        ],
        "path": ".",
        "truncated": false
      },
      "read": {
        "content": "# Café\n",
        "path": "README.md"
      }
    }
    "###);
    assert_eq!(
        fixture
            .invoke(fixture.call("lab_repo_list", json!({"path": "src"})))
            .await?,
        json!({"path": "src", "entries": [{"name": "main.rs", "kind": "file"}], "truncated": false})
    );
    Ok(())
}

#[tokio::test]
async fn rejects_escape_paths_and_unknown_arguments_before_filesystem_access() -> TestResult {
    let fixture = Fixture::new()?;
    for path in [
        "",
        "/etc/passwd",
        "../secret",
        "src/../../secret",
        "./README.md",
        "a//b",
        "C:/secret",
        "a\\b",
        "a\0b",
    ] {
        let mut call = fixture.call("lab_repo_read", json!({"path": path}));
        call.environments.clear();
        assert_eq!(
            fixture.invoke(call).await,
            Err(FunctionCallError::RespondToModel(
                "invalid repository-relative path".to_string()
            ))
        );
    }
    assert_eq!(
        fixture
            .invoke(fixture.call("lab_repo_read", json!({"path": "x", "execute": "command"})))
            .await,
        Err(FunctionCallError::RespondToModel(
            "expected an object containing only a string path".to_string()
        ))
    );
    Ok(())
}

#[tokio::test]
async fn rejects_missing_or_ambiguous_executor_and_changed_working_directory() -> TestResult {
    let fixture = Fixture::new()?;
    let mut missing = fixture.call("lab_repo_list", json!({"path": "."}));
    missing.environments.clear();
    let mut ambiguous = fixture.call("lab_repo_list", json!({"path": "."}));
    ambiguous
        .environments
        .push(ambiguous.environments[0].clone());
    for call in [missing, ambiguous] {
        assert_eq!(
            fixture.invoke(call).await,
            Err(FunctionCallError::RespondToModel(
                "repository tools require exactly one executor environment".to_string()
            ))
        );
    }
    let other = tempfile::tempdir()?;
    let mut changed = fixture.call("lab_repo_list", json!({"path": "."}));
    changed.environments[0].cwd = AbsolutePathBuf::from_absolute_path(other.path())?;
    assert_eq!(
        fixture.invoke(changed).await,
        Err(FunctionCallError::RespondToModel(
            "executor working directory differs from the bound repository".to_string()
        ))
    );
    Ok(())
}

#[tokio::test]
async fn forwards_effective_sandbox_instead_of_using_unsandboxed_fallback() -> TestResult {
    let fixture = Fixture::new()?;
    std::fs::write(fixture.directory.path().join("file.txt"), "text")?;
    let mut call = fixture.call("lab_repo_read", json!({"path": "file.txt"}));
    call.environments[0].file_system_sandbox_context =
        FileSystemSandboxContext::from_legacy_sandbox_policy(
            SandboxPolicy::new_read_only_policy(),
            PathUri::from_abs_path(&fixture.root),
        )?;
    // This executor has no sandbox runtime. Passing the context must fail; dropping
    // it would incorrectly make the read succeed with its unsandboxed backend.
    assert_eq!(
        fixture.invoke(call).await,
        Err(FunctionCallError::RespondToModel(
            "repository filesystem operation failed: InvalidInput".to_string()
        ))
    );
    Ok(())
}

#[tokio::test]
async fn rejects_oversized_non_utf8_and_wrong_entry_kinds() -> TestResult {
    let fixture = Fixture::new()?;
    std::fs::write(
        fixture.directory.path().join("large.txt"),
        vec![b'x'; 32 * 1024 + 1],
    )?;
    std::fs::write(fixture.directory.path().join("binary"), [0xff, 0xfe])?;
    for (name, path, expected) in [
        (
            "lab_repo_read",
            "large.txt",
            "repository file exceeds the 32 KiB read limit",
        ),
        (
            "lab_repo_read",
            "binary",
            "repository file is not valid UTF-8",
        ),
        ("lab_repo_read", ".", "requested path is not a regular file"),
        (
            "lab_repo_list",
            "binary",
            "requested path is not a directory",
        ),
    ] {
        assert_eq!(
            fixture
                .invoke(fixture.call(name, json!({"path": path})))
                .await,
            Err(FunctionCallError::RespondToModel(expected.to_string()))
        );
    }
    Ok(())
}

#[tokio::test]
async fn caps_listing_and_reports_partial_result() -> TestResult {
    let fixture = Fixture::new()?;
    for index in 0..130 {
        std::fs::write(
            fixture.directory.path().join(format!("file-{index:03}")),
            [],
        )?;
    }
    let actual = fixture
        .invoke(fixture.call("lab_repo_list", json!({"path": "."})))
        .await?;
    let expected_entries: Vec<Value> = (0..128)
        .map(|index| json!({"name": format!("file-{index:03}"), "kind": "file"}))
        .collect();
    assert_eq!(
        actual,
        json!({"path": ".", "entries": expected_entries, "truncated": true})
    );
    Ok(())
}

#[tokio::test]
async fn checks_serialized_output_against_effective_budget() -> TestResult {
    let fixture = Fixture::new()?;
    std::fs::write(fixture.directory.path().join("file.txt"), "x".repeat(2048))?;
    let mut call = fixture.call("lab_repo_read", json!({"path": "file.txt"}));
    call.truncation_policy = TruncationPolicy::Bytes(1024);
    assert_eq!(
        fixture.invoke(call).await,
        Err(FunctionCallError::RespondToModel(
            "repository result exceeds the effective tool response budget".to_string()
        ))
    );
    std::fs::write(fixture.directory.path().join("file.txt"), "x".repeat(8192))?;
    let mut generous = fixture.call("lab_repo_read", json!({"path": "file.txt"}));
    generous.truncation_policy = TruncationPolicy::Bytes(128 * 1024);
    assert_eq!(
        fixture.invoke(generous).await,
        Err(FunctionCallError::RespondToModel(
            "repository result exceeds the effective tool response budget".to_string()
        ))
    );
    Ok(())
}

#[cfg(unix)]
#[tokio::test]
async fn rejects_escaping_symlinks_and_omits_symlink_entries() -> TestResult {
    let fixture = Fixture::new()?;
    let outside = tempfile::tempdir()?;
    std::fs::write(outside.path().join("secret"), "external data")?;
    std::os::unix::fs::symlink(outside.path(), fixture.directory.path().join("escape"))?;
    assert_eq!(
        fixture
            .invoke(fixture.call("lab_repo_read", json!({"path": "escape/secret"})))
            .await,
        Err(FunctionCallError::RespondToModel(
            "requested path resolves outside the bound repository".to_string()
        ))
    );
    assert_eq!(
        fixture
            .invoke(fixture.call("lab_repo_list", json!({"path": "."})))
            .await?,
        json!({"path": ".", "entries": [], "truncated": false})
    );
    Ok(())
}
