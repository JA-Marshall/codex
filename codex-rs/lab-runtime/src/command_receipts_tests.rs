use std::sync::Arc;

use codex_extension_api::ConversationHistorySnapshot;
use codex_protocol::models::ResponseItem;
use codex_protocol::protocol::TruncationPolicy;
use codex_tools::ConversationHistory;
use codex_tools::NoopTurnItemEmitter;
use pretty_assertions::assert_eq;

use super::*;

struct EmptyHistory;
impl ConversationHistorySnapshot for EmptyHistory {
    fn history_version(&self) -> u64 {
        0
    }
    fn user_message_revision(&self) -> u64 {
        0
    }
    fn items(&self) -> Box<dyn Iterator<Item = &ResponseItem> + Send + '_> {
        Box::new(std::iter::empty())
    }
}

async fn start(receipts: &CommandReceipts, id: &str, command: &str) {
    let store = ExtensionData::new("thread");
    receipts
        .on_tool_start(ToolStartInput {
            session_store: &store,
            thread_store: &store,
            turn_store: &store,
            turn_id: "turn",
            root_turn_id: None,
            call_id: id,
            tool_name: &ToolName::namespaced("functions", "exec_command"),
            mcp_tool: None,
            payload: &ToolPayload::Function {
                arguments: json!({"cmd":command}).to_string(),
            },
            conversation_history: Arc::new(EmptyHistory),
            source: ToolCallSource::Direct,
        })
        .await;
}

async fn finish(receipts: &CommandReceipts, id: &str, outcome: ToolCallOutcome) {
    let store = ExtensionData::new("thread");
    receipts
        .on_tool_finish(ToolFinishInput {
            session_store: &store,
            thread_store: &store,
            turn_store: &store,
            turn_id: "turn",
            call_id: id,
            tool_name: &ToolName::namespaced("functions", "exec_command"),
            source: ToolCallSource::Direct,
            outcome,
        })
        .await;
}

async fn lookup(
    receipts: &CommandReceipts,
    thread: &str,
    turn: &str,
    arguments: &str,
    budget: usize,
) -> Result<Value, FunctionCallError> {
    let tool = ReceiptTool {
        receipts: receipts.clone(),
        thread: thread.to_owned(),
    };
    let payload = ToolPayload::Function {
        arguments: arguments.to_owned(),
    };
    let call = ToolCall {
        turn_id: turn.into(),
        call_id: "receipt-call".into(),
        tool_name: tool.tool_name(),
        model: "mock".into(),
        codex_turn_metadata: None,
        truncation_policy: TruncationPolicy::Bytes(budget),
        source: ToolCallSource::Direct,
        conversation_history: ConversationHistory::default(),
        turn_item_emitter: Arc::new(NoopTurnItemEmitter),
        environments: vec![],
        payload: payload.clone(),
    };
    Ok(tool.handle(call).await?.code_mode_result(&payload))
}

#[tokio::test]
async fn receipt_preserves_start_order_and_host_identity_across_out_of_order_finishes()
-> anyhow::Result<()> {
    let receipts = CommandReceipts::default();
    start(&receipts, "provider-call-a", "python3 check.py").await;
    start(&receipts, "provider-call-b", "false").await;
    finish(
        &receipts,
        "provider-call-b",
        ToolCallOutcome::Completed { success: false },
    )
    .await;
    finish(
        &receipts,
        "provider-call-a",
        ToolCallOutcome::Completed { success: true },
    )
    .await;
    let first = lookup(&receipts, "thread", "turn", "{\"index\":1}", 960).await?;
    insta::assert_snapshot!(serde_json::to_string_pretty(&first)?, @r###"
    {
      "commands_seen": 2,
      "index": 1,
      "receipt": {
        "call_id": "provider-call-a",
        "command_preview": "python3 check.py",
        "preview_truncated": false,
        "tool_outcome": {
          "status": "completed",
          "success": true
        }
      },
      "schema_version": 1
    }
    "###);
    let second = lookup(&receipts, "thread", "turn", "{\"index\":2}", 960).await?;
    assert_eq!(
        second,
        json!({"schema_version":1,"index":2,"commands_seen":2,"receipt":{
        "call_id":"provider-call-b","command_preview":"false","preview_truncated":false,
        "tool_outcome":{"status":"completed","success":false}}})
    );
    assert!(
        lookup(&receipts, "other-thread", "turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    assert!(
        lookup(&receipts, "thread", "other-turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    Ok(())
}

#[tokio::test]
async fn incomplete_duplicate_and_unmatched_observations_cannot_become_success()
-> anyhow::Result<()> {
    let receipts = CommandReceipts::default();
    finish(
        &receipts,
        "never-started",
        ToolCallOutcome::Completed { success: true },
    )
    .await;
    assert!(
        lookup(&receipts, "thread", "turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    start(&receipts, "a", "sleep 1").await;
    let pending = lookup(&receipts, "thread", "turn", "{\"index\":1}", 960).await?;
    assert_eq!(
        pending["receipt"]["tool_outcome"],
        json!({"status":"in_progress"})
    );
    finish(&receipts, "a", ToolCallOutcome::Aborted).await;
    assert_eq!(
        lookup(&receipts, "thread", "turn", "{\"index\":1}", 960).await?["receipt"]["tool_outcome"],
        json!({"status":"aborted"})
    );
    finish(&receipts, "a", ToolCallOutcome::Completed { success: true }).await;
    assert!(
        lookup(&receipts, "thread", "turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    let duplicate = CommandReceipts::default();
    start(&duplicate, "a", "true").await;
    start(&duplicate, "a", "false").await;
    assert!(
        lookup(&duplicate, "thread", "turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    Ok(())
}

#[tokio::test]
async fn bounds_reject_invalid_queries_and_report_preview_truncation() -> anyhow::Result<()> {
    let receipts = CommandReceipts::default();
    start(&receipts, "a", &"é".repeat(200)).await;
    let result = lookup(&receipts, "thread", "turn", "{\"index\":1}", 960).await?;
    assert_eq!(
        (
            result["receipt"]["command_preview"].clone(),
            result["receipt"]["preview_truncated"].clone()
        ),
        (json!("é".repeat(128)), json!(true))
    );
    for raw in [
        "{}",
        "{\"index\":0}",
        "{\"index\":-1}",
        "{\"index\":2}",
        "{\"index\":1,\"extra\":true}",
        &" ".repeat(129),
    ] {
        assert!(lookup(&receipts, "thread", "turn", raw, 960).await.is_err());
    }
    assert!(
        lookup(&receipts, "thread", "turn", "{\"index\":1}", 16)
            .await
            .is_err()
    );
    for index in 1..=MAX_RECEIPTS {
        start(&receipts, &format!("call-{index}"), "true").await;
    }
    assert!(
        lookup(&receipts, "thread", "turn", "{\"index\":1}", 960)
            .await
            .is_err()
    );
    for (id, command) in [
        ("valid".to_owned(), "x".repeat(8193)),
        ("\\".repeat(512), "\0".repeat(128)),
    ] {
        let bounded = CommandReceipts::default();
        start(&bounded, &id, &command).await;
        assert!(
            lookup(&bounded, "thread", "turn", "{\"index\":1}", 960)
                .await
                .is_err()
        );
    }
    Ok(())
}
