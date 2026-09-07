use super::*;
use codex_lab_runtime::execute_campaign_run;
use pretty_assertions::assert_eq;
use std::collections::BTreeSet;

async fn scoped_fixture(server: &MockServer) -> Result<support::Fixture> {
    let mut fixture = support::Fixture::new(&server.uri()).await?;
    std::fs::create_dir(fixture.repository.join("src"))?;
    std::fs::write(fixture.repository.join("src/.keep"), "")?;
    support::git(&fixture.repository, &["add", "src"]).await?;
    support::git(
        &fixture.repository,
        &[
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "source root",
        ],
    )
    .await?;
    fixture.commit = support::git(&fixture.repository, &["rev-parse", "HEAD"])
        .await?
        .trim()
        .to_string();
    Ok(fixture)
}

fn scoped_policy(
    fixture: &support::Fixture,
    options: &codex_lab_runtime::RunOptions,
    writes: Value,
    denied: Value,
) -> Result<PathBuf> {
    let mut policy = campaign::policy(options, 1);
    policy["task_scope"] =
        json!({"schema_version":1,"write_paths":writes,"deny_read_paths":denied});
    let path = fixture.runs.join(format!("{}-policy.json", options.run_id));
    std::fs::write(&path, serde_json::to_vec(&policy)?)?;
    Ok(path)
}

fn exec(id: &str, cmd: &str) -> String {
    response(
        id,
        responses::ev_function_call(
            id,
            "exec_command",
            &json!({"cmd":cmd,"max_output_tokens":1024,"timeout_ms":5000}).to_string(),
        ),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn task_scope_enforces_creation_repair_verifier_immutability_and_private_reads() -> Result<()>
{
    let server = MockServer::start().await;
    let fixture = scoped_fixture(&server).await?;
    let mut options = campaign::campaign_options(&fixture, "scope-repair");
    options.plan = Some(support::plan(1)?);
    options.workflow_catalog = options
        .workflow_catalog
        .replace("[workflows.base]", "[workflows.base]\nmax_repairs = 1");
    let private = tempfile::tempdir()?;
    std::fs::write(private.path().join("solution.txt"), "private solution")?;
    let unlisted = tempfile::tempdir()?;
    std::fs::write(
        unlisted.path().join("solution.txt"),
        "unlisted private solution",
    )?;
    let toolchain = tempfile::tempdir()?;
    std::fs::write(
        toolchain.path().join("resource.txt"),
        "pinned toolchain resource",
    )?;
    let policy = scoped_policy(&fixture, &options, json!(["src"]), json!([private.path()]))?;
    let mut policy_value: Value = serde_json::from_slice(&std::fs::read(&policy)?)?;
    policy_value["task_scope"]["read_paths"] = json!([toolchain.path()]);
    std::fs::write(&policy, serde_json::to_vec(&policy_value)?)?;
    let mut first = implementation_and_verification("first");
    first[0] = first[0].replace("+hello", "+wrong");
    first[2] = exec(
        "first-verify",
        "if { printf hello > greeting.txt; } 2>/dev/null; then exit 74; fi; test \"$(cat greeting.txt)\" = hello && test ! -e forbidden.txt",
    );
    // Real writes outside the scope must be denied by the managed sandbox.
    first.insert(0, exec("outside", "if printf changed >> README.md; then exit 71; fi; if printf bad > forbidden.txt; then exit 72; fi; printf scratch > \"$TMPDIR/probe\"; test -f \"$TMPDIR/probe\""));
    first.insert(1, exec("private", &format!("if cat '{}'; then exit 73; fi; if cat '{}'; then exit 75; fi; cat '{}'; printf private-denied", private.path().join("solution.txt").display(), unlisted.path().join("solution.txt").display(), toolchain.path().join("resource.txt").display())));
    first.insert(
        2,
        response(
            "outside-patch",
            responses::ev_custom_tool_call("outside-patch", "apply_patch", FORBIDDEN_PATCH),
        ),
    );
    let mut repair = implementation_and_verification("repair");
    repair[0] = response(
        "repair-patch",
        responses::ev_custom_tool_call(
            "repair-patch",
            "apply_patch",
            "*** Begin Patch\n*** Update File: greeting.txt\n@@\n-wrong\n+hello\n*** End Patch",
        ),
    );
    repair[2] = exec(
        "repair-verify",
        "if { printf hello > greeting.txt; } 2>/dev/null; then exit 74; fi; test \"$(cat greeting.txt)\" = hello && test ! -e forbidden.txt",
    );
    first.extend(repair);
    for event in &mut first {
        *event = event.replace("greeting.txt", "src/greeting.txt");
    }
    let mock = responses::mount_sse_sequence(&server, first).await;
    let result = execute_campaign_run(options, fixture.paths.clone(), &policy)
        .await
        .inspect_err(|error| eprintln!("SCOPED RUN FAILED: {error:#}"))?;
    assert_eq!(result.state, WorkflowState::Completed);
    assert_eq!(
        std::fs::read_to_string(fixture.repository.join("src/greeting.txt"))?,
        "hello\n"
    );
    assert_eq!(
        std::fs::read_to_string(fixture.repository.join("README.md"))?,
        "Fixture task: create greeting.txt containing hello.\n"
    );
    assert!(!fixture.repository.join("forbidden.txt").exists());
    let requests = mock.requests();
    let private_output = requests
        .iter()
        .find_map(|request| request.function_call_output_text("private"))
        .context("private-read result")?;
    assert!(private_output.contains("private-denied"));
    assert!(private_output.contains("pinned toolchain resource"));
    assert!(!private_output.contains("private solution"));
    let mut hashes = BTreeSet::new();
    for index in 1..=4 {
        let output: Value = serde_json::from_slice(&std::fs::read(
            result
                .artifacts
                .join(format!("evidence/phase-{index:02}.json")),
        )?)?;
        let scope = &output["task_scope"];
        hashes.insert(
            scope["scope_sha256"]
                .as_str()
                .context("scope digest")?
                .to_owned(),
        );
        assert_eq!(scope["audit"]["authorized"], true);
        if index % 2 == 0 {
            assert_eq!(
                (
                    scope["candidate_write_paths"].clone(),
                    scope["audit"]["candidate_unchanged"].clone()
                ),
                (json!([]), json!(true))
            );
        }
        let scratch = scope["scratch"].as_str().context("scratch evidence")?;
        assert!(!std::path::Path::new(scratch).exists());
    }
    assert_eq!(hashes.len(), 1);
    let metrics: Value = serde_json::from_slice(&std::fs::read(
        result.artifacts.join("evidence/metrics.json"),
    )?)?;
    assert_eq!(metrics["repair_attempts"], 1);
    if let Some(destination) = std::env::var_os("CODEX_LAB_SCOPE_ARTIFACT_EXPORT") {
        ensure!(
            tokio::process::Command::new("cp")
                .arg("-a")
                .arg(&result.artifacts)
                .arg(destination)
                .status()
                .await?
                .success(),
            "export mock scope artifact"
        );
    }
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn task_scope_quarantines_a_new_alias_after_confirmed_shutdown() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = scoped_fixture(&server).await?;
    let mut options = campaign::campaign_options(&fixture, "scope-alias");
    options.plan = Some(support::plan(1)?);
    let policy = scoped_policy(&fixture, &options, json!(["src"]), json!([]))?;
    let mock = responses::mount_sse_sequence(
        &server,
        vec![
            exec("alias", "ln -s ../README.md src/alias"),
            response(
                "done",
                responses::ev_assistant_message("done", "{\"completed_steps\":[\"S01\"]}"),
            ),
        ],
    )
    .await;
    let error = execute_campaign_run(options, fixture.paths.clone(), &policy)
        .await
        .expect_err("new aliases are quarantined");
    assert!(error.to_string().contains("task scope audit"), "{error:#}");
    assert_eq!(mock.requests().len(), 2);
    let events: Vec<Value> =
        std::fs::read_to_string(fixture.runs.join("scope-alias/runtime-events.jsonl"))?
            .lines()
            .map(serde_json::from_str)
            .collect::<std::result::Result<_, _>>()?;
    let audit = events
        .iter()
        .position(|event| event["type"] == "phase_scope_audit")
        .context("audit")?;
    let stopped = events
        .iter()
        .position(|event| event["type"] == "phase_stopped")
        .context("shutdown")?;
    let failed = events
        .iter()
        .position(|event| event["type"] == "runtime_failed")
        .context("failure")?;
    assert!(audit < stopped && stopped < failed);
    assert_eq!(events[audit]["evidence"]["authorized"], false);
    let failure: Value = serde_json::from_slice(&std::fs::read(
        fixture.runs.join("scope-alias/evidence/failure.json"),
    )?)?;
    assert_eq!(failure["classification"], "scope_blocked");
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn task_scope_rejects_unsafe_roots_before_model_requests() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = scoped_fixture(&server).await?;
    for (index, roots) in [json!(["."])].into_iter().enumerate() {
        let options = campaign::campaign_options(&fixture, &format!("scope-rejected-{index}"));
        let policy = scoped_policy(&fixture, &options, roots, json!([]))?;
        let error = execute_campaign_run(options, fixture.paths.clone(), &policy)
            .await
            .expect_err("unsafe scope");
        assert!(error.to_string().contains("task scope"), "{error:#}");
        let failure: Value = serde_json::from_slice(&std::fs::read(
            fixture
                .runs
                .join(format!("scope-rejected-{index}/evidence/failure.json")),
        )?)?;
        assert_eq!(failure["classification"], "scope_blocked");
    }
    assert!(
        server
            .received_requests()
            .await
            .context("requests")?
            .is_empty()
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn task_scope_does_not_expand_after_an_amended_plan() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = scoped_fixture(&server).await?;
    let mut options = campaign::campaign_options(&fixture, "scope-amendment");
    options.plan = Some(support::plan(1)?);
    let policy = scoped_policy(&fixture, &options, json!(["src"]), json!([]))?;
    let mut sequence = vec![
        response(
            "amend",
            responses::ev_function_call(
                "amend",
                "lab_request_amendment",
                "{\"reason\":\"Need to create greeting.txt at repository root.\"}",
            ),
        ),
        response(
            "amended",
            responses::ev_assistant_message("plan", &serde_json::to_string(&support::plan(2)?)?),
        ),
    ];
    sequence.extend(implementation_and_verification("blocked"));
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let error = execute_campaign_run(options, fixture.paths.clone(), &policy)
        .await
        .expect_err("candidate required outside immutable scope");
    assert!(
        error.to_string().contains("verification") || error.to_string().contains("repair"),
        "{error:#}"
    );
    assert_eq!(mock.requests().len(), 7);
    assert!(!fixture.repository.join("greeting.txt").exists());
    assert!(
        !fixture
            .runs
            .join("scope-amendment/evidence/metrics.json")
            .exists()
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn task_scope_preserves_expanded_permission_paths_through_verification() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = scoped_fixture(&server).await?;
    let mut options = campaign::campaign_options(&fixture, "scope-xml-expansion");
    options.plan = Some(serde_json::from_str(
        &serde_json::to_string(&support::plan(1)?)?.replace("greeting.txt", "src/greeting.txt"),
    )?);
    let outside = tempfile::tempdir()?;
    let mut read_root = outside.path().to_path_buf();
    for _ in 0..15 {
        read_root.push("'".repeat(240));
    }
    std::fs::create_dir_all(&read_root)?;
    let reference = read_root.join("reference.txt");
    std::fs::write(&reference, "reference")?;
    let policy_path = scoped_policy(&fixture, &options, json!(["src"]), json!([]))?;
    let mut policy: Value = serde_json::from_slice(&std::fs::read(&policy_path)?)?;
    policy["task_scope"]["read_paths"] = json!([read_root]);
    std::fs::write(&policy_path, serde_json::to_vec(&policy)?)?;
    let mut sequence = implementation_and_verification("scope-long-path");
    for event in &mut sequence {
        *event = event.replace("greeting.txt", "src/greeting.txt");
    }
    sequence[2] = exec(
        "scope-long-path-verify",
        &format!(
            "test \"$(cat \"{}\")\" = reference && test \"$(cat src/greeting.txt)\" = hello && test ! -e forbidden.txt",
            reference.display()
        ),
    );
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let result = execute_campaign_run(options, fixture.paths.clone(), &policy_path).await?;
    assert_eq!(
        (result.state, mock.requests().len()),
        (WorkflowState::Completed, 5)
    );
    assert_eq!(
        std::fs::read_to_string(fixture.repository.join("src/greeting.txt"))?,
        "hello\n"
    );
    for index in 1..=2 {
        let phase: Value = serde_json::from_slice(&std::fs::read(
            result
                .artifacts
                .join(format!("evidence/phase-{index:02}.json")),
        )?)?;
        assert_eq!(phase["task_scope"]["audit"]["authorized"], true);
    }
    Ok(())
}
