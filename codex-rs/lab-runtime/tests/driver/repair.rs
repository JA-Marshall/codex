use super::*;
use pretty_assertions::assert_eq;

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn repair_loop_rechecks_after_fix_and_stops_at_the_frozen_budget() -> Result<()> {
    for (limit, repaired, padding) in [
        (0_u8, false, 0),
        (1, true, 0),
        (1, false, 0),
        (1, true, 16384),
    ] {
        let server = MockServer::start().await;
        let mut fixture = support::Fixture::new(&server.uri()).await?;
        fixture.workflow_catalog = fixture.workflow_catalog.replace(
            "[workflows.base]",
            &format!("[workflows.base]\nmax_repairs = {limit}"),
        );
        let mut sequence = implementation_and_verification("first");
        sequence[0] = sequence[0].replace("+hello", "+wrong");
        if limit > 0 {
            let mut retry = implementation_and_verification("repair");
            let replacement = if repaired { "+hello" } else { "+still-wrong" };
            retry[0] = response(
                "repair-patch",
                responses::ev_custom_tool_call(
                    "repair-patch",
                    "apply_patch",
                    &format!(
                        "*** Begin Patch\n*** Update File: greeting.txt\n@@\n-wrong\n{replacement}\n*** End Patch"
                    ),
                ),
            );
            sequence.extend(retry);
        }
        if padding > 0 {
            for event in &mut sequence {
                *event = event.replace(
                    "&& test ! -e forbidden.txt",
                    &format!("&& test ! -e forbidden.txt # {}", "x".repeat(padding)),
                );
            }
        }
        let expected_requests = sequence.len();
        let mock = responses::mount_sse_sequence(&server, sequence).await;
        let mut reviewer = Reviewer {
            repository: fixture.repository.clone(),
            targets: Vec::new(),
            views: Vec::new(),
            responses: Some(mock.clone()),
            expected_requests_at_review: vec![0],
            approve: true,
        };
        let outcome = execute_run(
            fixture.options("repair", "md", Some(support::plan(1)?)),
            fixture.paths.clone(),
            &mut reviewer,
        )
        .await;
        assert_eq!(outcome.is_ok(), repaired, "{outcome:?}");
        assert_eq!(reviewer.targets.len(), 1);
        assert_eq!(mock.requests().len(), expected_requests);
        if padding > 0 {
            for prefix in ["first", "repair"] {
                let output = mock
                    .requests()
                    .iter()
                    .find_map(|request| {
                        request.function_call_output_text(&format!("{prefix}-receipt"))
                    })
                    .context("missing long-command receipt")?;
                let receipt: Value = serde_json::from_str(&output)
                    .with_context(|| format!("long-command receipt: {output}"))?;
                assert_eq!(receipt["receipt"]["call_id"], format!("{prefix}-verify"));
                assert_eq!(receipt["receipt"]["preview_truncated"], true);
            }
        }
        let root = fixture.runs.join("repair");
        let events: Vec<Value> = std::fs::read_to_string(root.join("events.jsonl"))?
            .lines()
            .map(serde_json::from_str)
            .collect::<std::result::Result<_, _>>()?;
        assert_eq!(
            events
                .iter()
                .filter(|e| e["change"]["type"] == "repair_started")
                .count(),
            usize::from(limit)
        );
        assert_eq!(
            events.last().context("terminal event")?["state"],
            if repaired { "completed" } else { "failed" }
        );
        assert!(
            events
                .iter()
                .any(|e| e["change"]["type"] == "verification_recorded"
                    && e["change"]["evidence"]["passed"] == false)
        );
        if repaired {
            assert_eq!(
                std::fs::read_to_string(fixture.repository.join("greeting.txt"))?,
                "hello\n"
            );
            let metrics: Value =
                serde_json::from_slice(&std::fs::read(root.join("evidence/metrics.json"))?)?;
            assert_eq!(metrics["repair_attempts"], 1);
            assert_eq!(metrics["turns"], 4);
            let prompt: Value =
                serde_json::from_slice(&std::fs::read(root.join("evidence/input-03.json"))?)?;
            assert!(
                prompt["prompt"]
                    .as_str()
                    .context("repair prompt")?
                    .contains("failed checks: V01")
            );
        }
        for phase in 1..=if limit == 0 { 2 } else { 4 } {
            let evidence: Value = serde_json::from_slice(&std::fs::read(
                root.join(format!("evidence/phase-{phase:02}.json")),
            )?)?;
            assert!(
                evidence["events"]
                    .as_array()
                    .context("phase events")?
                    .iter()
                    .any(|e| e["msg"]["type"] == "shutdown_complete")
            );
        }
    }
    Ok(())
}
