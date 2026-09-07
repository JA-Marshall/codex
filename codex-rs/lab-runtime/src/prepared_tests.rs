use std::fs;

use anyhow::Result;
use codex_lab::LabRun;
use codex_lab::WorkflowState;
use pretty_assertions::assert_eq;

use super::*;
use crate::authority_support;

fn fixture() -> Result<(tempfile::TempDir, RunAuthority, EvidenceStore, RunOptions)> {
    let (root, run) = authority_support::new_run()?;
    let authority = RunAuthority::new(run)?;
    authority.update(LabRun::begin_planning)?;
    let plan = authority_support::plan(1)?;
    authority.update(|run| run.submit_plan(plan))?;
    let artifacts = authority.artifacts()?;
    let evidence = EvidenceStore::new(&artifacts)?;
    for name in [
        "effective-settings.json",
        "environment.json",
        "runtime-manifest.json",
    ] {
        evidence.write_json(name, &serde_json::json!({"schema_version":1}))?;
    }
    let options = RunOptions {
        repository: root.path().to_owned(),
        repository_commit: "0".repeat(40),
        codex_home: root.path().to_owned(),
        runs_directory: root.path().to_owned(),
        run_id: "run".into(),
        task: "Test runtime admission".into(),
        workflow_catalog: fs::read_to_string(artifacts.join("config/workflow.source.toml"))?,
        instruction_root: root.path().to_owned(),
        workflow: "test".into(),
        plan: None,
    };
    Ok((root, authority, evidence, options))
}

#[test]
fn prepared_round_trip_leaves_source_pending_and_reuses_only_data() -> Result<()> {
    let (_root, authority, evidence, options) = fixture()?;
    let before = fs::read(authority.artifacts()?.join("events.jsonl"))?;
    let prepared = seal(&options, &authority, &evidence, 0)?;
    let loaded = load(&prepared.prepared, "child".into())?;
    assert_eq!(loaded.options.run_id, "child");
    assert_eq!(loaded.options.plan, Some(authority_support::plan(1)?));
    assert_eq!(
        authority.snapshot()?.state,
        WorkflowState::AwaitingPlanApproval
    );
    assert_eq!(authority.snapshot()?.approved, None);
    assert_eq!(
        fs::read(authority.artifacts()?.join("events.jsonl"))?,
        before
    );
    assert_eq!(loaded.lineage["approval_reused"], false);
    Ok(())
}

#[test]
fn prepared_rejects_changed_partial_missing_and_oversized_artifacts() -> Result<()> {
    for name in [
        "config/run-spec.json",
        "plans/1/plan.json",
        "plans/1/plan.view.json",
        "instructions/executor.SKILL.md",
        "events.jsonl",
        "runtime-events.jsonl",
        "evidence/prepared.json",
    ] {
        let (_root, authority, evidence, options) = fixture()?;
        let prepared = seal(&options, &authority, &evidence, 0)?;
        let path = authority.artifacts()?.join(name);
        let original = fs::read(&path)?;
        fs::write(&path, b"{")?;
        assert!(load(&prepared.prepared, "child".into()).is_err(), "{name}");
        fs::remove_file(&path)?;
        assert!(load(&prepared.prepared, "child".into()).is_err(), "{name}");
        fs::write(&path, &original)?;
        assert!(load(&prepared.prepared, "child".into()).is_ok(), "{name}");
    }
    let (_root, authority, evidence, options) = fixture()?;
    let prepared = seal(&options, &authority, &evidence, 0)?;
    fs::OpenOptions::new()
        .write(true)
        .open(&prepared.prepared)?
        .set_len(65537)?;
    assert!(load(&prepared.prepared, "child".into()).is_err());
    Ok(())
}

#[test]
fn prepared_seal_rejects_active_phase_and_prior_approval() -> Result<()> {
    let (_root, authority, evidence, options) = fixture()?;
    let target = authority.snapshot()?.target.unwrap();
    authority.update(|run| run.approve(target, "test human"))?;
    assert!(seal(&options, &authority, &evidence, 0).is_err());
    let (_root, authority, evidence, options) = fixture()?;
    fs::write(authority.artifacts()?.join("runtime-events.jsonl"),
        b"{\"sequence\":1,\"type\":\"phase_started\",\"phase\":\"planning\",\"epoch\":1,\"target\":null}\n")?;
    assert!(seal(&options, &authority, &evidence, 0).is_err());
    assert!(!authority.artifacts()?.join(DESCRIPTOR).exists());
    Ok(())
}

#[cfg(unix)]
#[test]
fn prepared_rejects_escaping_and_symlink_references() -> Result<()> {
    let (_root, authority, evidence, options) = fixture()?;
    let prepared = seal(&options, &authority, &evidence, 0)?;
    let root = authority.artifacts()?;
    for reference in [
        "../skill/SKILL.md",
        "/etc/passwd",
        "config/../manifest.json",
        "config\\run-spec.json",
    ] {
        assert!(read_artifact(&root, reference, 65536).is_err());
    }
    let original = root.join("instructions/executor.SKILL.md");
    let backup = root.join("original-skill");
    fs::rename(&original, &backup)?;
    std::os::unix::fs::symlink(backup, original)?;
    assert!(load(&prepared.prepared, "child".into()).is_err());
    Ok(())
}
