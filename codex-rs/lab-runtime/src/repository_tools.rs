//! Bounded repository research through the executor's existing filesystem authority.
//!
//! Canonical containment is defense in depth, not a replacement for the host's
//! filesystem sandbox. The executor remains responsible for race-safe access.

use std::collections::BTreeMap;
use std::sync::Arc;

use codex_extension_api::ExtensionData;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_extension_api::ToolContributor;
use codex_file_system::GetMetadataOptions;
use codex_file_system::WalkEntryKind;
use codex_file_system::WalkOptions;
use codex_tools::AdditionalProperties;
use codex_tools::FunctionCallError;
use codex_tools::JsonSchema;
use codex_tools::JsonToolOutput;
use codex_tools::ResponsesApiTool;
use codex_tools::ToolCall;
use codex_tools::ToolExecutor;
use codex_tools::ToolExecutorFuture;
use codex_tools::ToolName;
use codex_tools::ToolOutput;
use codex_tools::ToolSpec;
use codex_utils_absolute_path::AbsolutePathBuf;
use codex_utils_path_uri::PathUri;
use futures::StreamExt;
use serde::Deserialize;
use serde_json::json;

const MAX_FILE_BYTES: usize = 32 * 1024;
// Model-tokenizer-independent ceiling: even byte-wise tokenization stays below
// the repository's 10K-token limit for a new individual context item.
const MAX_RESPONSE_BYTES: usize = 8 * 1024;
const MAX_DIRECTORY_ENTRIES: usize = 128;
const MAX_PATH_BYTES: usize = 4096;

/// Read-only tools bound to one repository and one executor environment.
///
/// Every operation uses the invocation's effective filesystem sandbox context.
/// These tools neither spawn processes nor obtain their own filesystem executor.
pub struct RepositoryTools {
    root: PathUri,
}

impl RepositoryTools {
    pub fn new(root: AbsolutePathBuf) -> Self {
        Self {
            root: PathUri::from_abs_path(&root),
        }
    }
}

impl ToolContributor for RepositoryTools {
    fn tools(
        &self,
        _session_store: &ExtensionData,
        _thread_store: &ExtensionData,
    ) -> Vec<Arc<dyn for<'call> ToolExecutor<ToolCall<'call>>>> {
        [Operation::Read, Operation::List]
            .into_iter()
            .map(|operation| {
                Arc::new(RepositoryTool {
                    root: self.root.clone(),
                    operation,
                }) as Arc<dyn for<'call> ToolExecutor<ToolCall<'call>>>
            })
            .collect()
    }
}

/// Installs the two repository research tools without adding other contributors.
pub fn install_repository_tools<C: Sync>(
    registry: &mut ExtensionRegistryBuilder<C>,
    root: AbsolutePathBuf,
) {
    registry.tool_contributor(Arc::new(RepositoryTools::new(root)));
}

#[derive(Clone, Copy)]
enum Operation {
    Read,
    List,
}

struct RepositoryTool {
    root: PathUri,
    operation: Operation,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Arguments {
    path: String,
}

impl<'call> ToolExecutor<ToolCall<'call>> for RepositoryTool {
    fn tool_name(&self) -> ToolName {
        ToolName::plain(match self.operation {
            Operation::Read => "lab_repo_read",
            Operation::List => "lab_repo_list",
        })
    }

    fn spec(&self) -> ToolSpec {
        let description = match self.operation {
            Operation::Read => {
                "Read one UTF-8 repository file, limited to 32 KiB on disk and 8 KiB of serialized output. Use a repository-relative path with forward slashes. Oversized or non-text files return an error."
            }
            Operation::List => {
                "List up to 128 immediate repository directory entries in name order. Use a repository-relative path, or '.' for the repository root. Symlinks and special files are omitted. The truncated flag reports a bounded partial listing."
            }
        };
        ToolSpec::Function(ResponsesApiTool {
            name: self.tool_name().name,
            description: description.to_string(),
            strict: true,
            defer_loading: None,
            parameters: JsonSchema::object(
                BTreeMap::from([(
                    "path".to_string(),
                    JsonSchema::string(Some("Repository-relative path.".to_string())),
                )]),
                Some(vec!["path".to_string()]),
                Some(AdditionalProperties::Boolean(false)),
            ),
            output_schema: None,
        })
    }

    fn handle<'a>(&'a self, call: ToolCall<'call>) -> ToolExecutorFuture<'a>
    where
        'call: 'a,
    {
        Box::pin(async move {
            let raw = call.function_arguments()?;
            if raw.len() > 2 * MAX_PATH_BYTES {
                return Err(rejected("repository tool arguments exceed the size limit"));
            }
            let args: Arguments = serde_json::from_str(raw)
                .map_err(|_| rejected("expected an object containing only a string path"))?;
            validate_path(&args.path)?;
            let [environment] = call.environments.as_slice() else {
                return Err(rejected(
                    "repository tools require exactly one executor environment",
                ));
            };
            let fs = &environment.file_system;
            let sandbox = Some(&environment.file_system_sandbox_context);
            let root = fs
                .canonicalize(&self.root, sandbox)
                .await
                .map_err(fs_error)?;
            let cwd = fs
                .canonicalize(&PathUri::from_abs_path(&environment.cwd), sandbox)
                .await
                .map_err(fs_error)?;
            if cwd != root {
                return Err(rejected(
                    "executor working directory differs from the bound repository",
                ));
            }
            let requested = if args.path == "." {
                root.clone()
            } else {
                root.join(&args.path)
                    .map_err(|_| rejected("invalid repository-relative path"))?
            };
            let target = fs
                .canonicalize(&requested, sandbox)
                .await
                .map_err(fs_error)?;
            if !target.starts_with(&root) {
                return Err(rejected(
                    "requested path resolves outside the bound repository",
                ));
            }
            let metadata = fs
                .get_metadata(
                    &target,
                    GetMetadataOptions {
                        follow_symlinks: false,
                    },
                    sandbox,
                )
                .await
                .map_err(fs_error)?;
            let mut value = match self.operation {
                Operation::Read => {
                    if !metadata.is_file || metadata.is_symlink {
                        return Err(rejected("requested path is not a regular file"));
                    }
                    if metadata.size > MAX_FILE_BYTES as u64 {
                        return Err(rejected("repository file exceeds the 32 KiB read limit"));
                    }
                    let mut stream = fs
                        .read_file_stream(&target, sandbox)
                        .await
                        .map_err(fs_error)?;
                    let mut bytes = Vec::new();
                    while let Some(chunk) = stream.next().await {
                        let chunk = chunk.map_err(fs_error)?;
                        if chunk.len() > MAX_FILE_BYTES - bytes.len() {
                            return Err(rejected("repository file exceeds the 32 KiB read limit"));
                        }
                        bytes.extend_from_slice(&chunk);
                    }
                    let content = String::from_utf8(bytes)
                        .map_err(|_| rejected("repository file is not valid UTF-8"))?;
                    json!({"path": args.path, "content": content})
                }
                Operation::List => {
                    if !metadata.is_directory || metadata.is_symlink {
                        return Err(rejected("requested path is not a directory"));
                    }
                    // Use the executor's bounded walk, not unbounded read_directory.
                    // The upstream executor may enumerate names before applying its cap.
                    let mut outcome = fs
                        .walk(
                            &target,
                            WalkOptions {
                                max_depth: 0,
                                max_directories: 1,
                                max_entries: MAX_DIRECTORY_ENTRIES,
                                follow_directory_symlinks: false,
                                prune_hidden_directories: false,
                            },
                            sandbox,
                        )
                        .await
                        .map_err(fs_error)?;
                    if !outcome.errors.is_empty() || outcome.entries.len() > MAX_DIRECTORY_ENTRIES {
                        return Err(rejected(
                            "repository directory could not be listed reliably",
                        ));
                    }
                    outcome.entries.sort_by_key(|entry| entry.path.basename());
                    let mut entries = Vec::with_capacity(outcome.entries.len());
                    for entry in outcome.entries {
                        if entry.path.parent().as_ref() != Some(&target) {
                            return Err(rejected(
                                "executor returned an entry outside the requested directory",
                            ));
                        }
                        let name = entry.path.basename().ok_or_else(|| {
                            rejected("executor returned an invalid directory entry")
                        })?;
                        let kind = match entry.kind {
                            WalkEntryKind::Directory => "directory",
                            WalkEntryKind::File => "file",
                        };
                        entries.push(json!({"name": name, "kind": kind}));
                    }
                    json!({"path": args.path, "entries": entries, "truncated": outcome.truncated})
                }
            };
            // Keep model-visible ordering stable when workspace feature unification
            // enables serde_json's preserve_order implementation.
            value.sort_all_objects();
            if value.to_string().len() > call.response_byte_budget(MAX_RESPONSE_BYTES) {
                return Err(rejected(
                    "repository result exceeds the effective tool response budget",
                ));
            }
            Ok(Box::new(JsonToolOutput::new(value)) as Box<dyn ToolOutput>)
        })
    }
}

fn validate_path(path: &str) -> Result<(), FunctionCallError> {
    if path.is_empty()
        || path.len() > MAX_PATH_BYTES
        || path.chars().any(char::is_control)
        || path.contains(['\\', ':'])
        || path != "." && path.split('/').any(|part| matches!(part, "" | "." | ".."))
    {
        return Err(rejected("invalid repository-relative path"));
    }
    Ok(())
}

fn rejected(message: &str) -> FunctionCallError {
    FunctionCallError::RespondToModel(message.to_string())
}

fn fs_error(error: std::io::Error) -> FunctionCallError {
    // Executor diagnostics can contain paths beyond the bound repository.
    rejected(&format!(
        "repository filesystem operation failed: {:?}",
        error.kind()
    ))
}
