//! Read-only comparisons of recorded controls. No model calls or run restoration.

#[cfg(unix)]
use std::fs::File;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use serde_json::Value;
use serde_json::json;

use crate::artifact_input::digest;
use crate::artifact_input::read_artifact;
use crate::comparison_input::read_run;

pub(crate) struct Observation {
    pub controls: Value,
    pub metadata: Value,
    pub outcomes: Value,
    pub problems: Vec<String>,
}

/// Compare one recorded pair. The only supported independent variable is
/// `plan.renderer`; every other behavioral difference prevents a controlled label.
/// Missing serving revisions stay unknown, even for an otherwise controlled pair.
pub fn compare_runs(left: &Path, right: &Path, vary: &str, output: &Path) -> Result<PathBuf> {
    ensure!(
        vary == "plan.renderer",
        "only plan.renderer comparisons are supported"
    );
    let left_root = left.canonicalize()?;
    let right_root = right.canonicalize()?;
    ensure!(
        left_root != right_root,
        "comparison requires two distinct runs"
    );
    let name = output
        .file_name()
        .context("output needs a directory name")?;
    let parent = output.parent().context("output parent missing")?;
    let parent = if parent.as_os_str().is_empty() {
        Path::new(".")
    } else {
        parent
    };
    let output = parent.canonicalize()?.join(name);
    for root in [&left_root, &right_root] {
        ensure!(
            !output.starts_with(root) && !root.starts_with(&output),
            "comparison output overlaps a source run"
        );
    }
    let left = read_run(&left_root)?;
    let right = read_run(&right_root)?;
    let report = report(&left, &right, vary);
    let bytes = serde_json::to_vec_pretty(&report)?;
    ensure!(
        bytes.len() <= 8 * 1024 * 1024,
        "comparison exceeds byte limit"
    );
    let mut markdown = format!(
        "# Recorded run comparison\n\nClassification: **{}**. One run per condition; no statistical winner is inferred. Remote immutable serving revision is not established.\n\n| Control | Left | Right |\n| --- | --- | --- |\n",
        report["classification"].as_str().unwrap_or_default()
    );
    for difference in report["control_differences"]
        .as_array()
        .context("differences missing")?
    {
        markdown.push_str(&format!(
            "| {} | {} | {} |\n",
            cell(&difference["path"]),
            cell(&difference["left"]),
            cell(&difference["right"])
        ));
    }
    markdown.push_str("\nComplete controls, metadata differences, outcomes and limitations are retained in comparison.json.\n");
    for issue in left.problems.iter().chain(&right.problems) {
        markdown.push_str(&format!("\n- {}\n", cell(&json!(issue))));
    }
    // Recheck every input fingerprint after analysis to reject concurrent edits.
    for (root, observation) in [(&left_root, &left), (&right_root, &right)] {
        for (name, hash) in observation.metadata["artifact_sha256"]
            .as_object()
            .context("artifact inventory missing")?
        {
            ensure!(
                digest(&read_artifact(root, name, 8 * 1024 * 1024)?)
                    == hash.as_str().context("invalid digest")?,
                "source run changed during comparison"
            );
        }
    }
    std::fs::create_dir(&output)?;
    for (name, content) in [
        ("comparison.json", bytes.as_slice()),
        ("comparison.md", markdown.as_bytes()),
    ] {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(output.join(name))?;
        file.write_all(content)?;
        file.sync_all()?;
    }
    #[cfg(unix)]
    File::open(&output)?.sync_all()?;
    Ok(output.join("comparison.json"))
}

fn report(left: &Observation, right: &Observation, vary: &str) -> Value {
    let mut controls = Vec::new();
    differences("", &left.controls, &right.controls, &mut controls);
    let mut metadata = Vec::new();
    differences("", &left.metadata, &right.metadata, &mut metadata);
    let controlled = left.problems.is_empty()
        && right.problems.is_empty()
        && controls.len() == 1
        && controls[0]["path"] == vary;
    json!({"schema_version":1,"vary":vary,
        "classification":if controlled {"controlled_recorded_pair"} else {"descriptive_only"},
        "sample_size_per_condition":1,"immutable_serving_revision_established":false,
        "control_differences":controls,"metadata_differences":metadata,
        "left":{"controls":left.controls,"metadata":left.metadata,"outcomes":left.outcomes,"problems":left.problems},
        "right":{"controls":right.controls,"metadata":right.metadata,"outcomes":right.outcomes,"problems":right.problems},
        "limitations":["recorded controls, not proof of immutable remote model weights", "no confidence interval or winner from one pair",
            "artifact hashes detect subsequent edits, not a malicious host rewriting all evidence", "unrecorded system and provider state remains unknown"]})
}

fn differences(path: &str, left: &Value, right: &Value, result: &mut Vec<Value>) {
    if left == right {
        return;
    }
    if let (Some(left), Some(right)) = (left.as_object(), right.as_object()) {
        // Visit shared keys once: duplicate differences would incorrectly
        // disqualify a pair whose only changed control is the renderer.
        for key in left
            .keys()
            .chain(right.keys().filter(|key| !left.contains_key(*key)))
        {
            let path = if path.is_empty() {
                key.clone()
            } else {
                format!("{path}.{key}")
            };
            if let (Some(left), Some(right)) = (left.get(key), right.get(key)) {
                differences(&path, left, right, result);
            } else {
                result.push(
                    json!({"path":path,"left":left.get(key),"right":right.get(key),
                    "left_present":left.contains_key(key),"right_present":right.contains_key(key)}),
                );
            }
        }
    } else {
        result.push(json!({"path":path,"left":left,"right":right}));
    }
}

fn cell(value: &Value) -> String {
    let text = value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string());
    let mut escaped: String = text.chars().take(256).filter(|c| !c.is_control()).collect();
    escaped = escaped
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('|', "&#124;")
        .replace('`', "&#96;");
    if text.chars().count() > 256 {
        escaped.push_str("… (full value in JSON)");
    }
    escaped
}

#[cfg(test)]
#[path = "comparison_tests.rs"]
mod tests;
