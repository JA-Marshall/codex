use pretty_assertions::assert_eq;

use super::BrowserExtensionConfig;
use super::install;
use crate::tool::BROWSER_NAVIGATE_TOOL_NAME;
use codex_core::config::Config;
use codex_extension_api::ExtensionData;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_extension_api::ToolName;

fn installed_tool_names(config: BrowserExtensionConfig) -> Vec<ToolName> {
    let mut builder = ExtensionRegistryBuilder::<Config>::new();
    install(&mut builder);
    let registry = builder.build();
    let session_store = ExtensionData::new("session");
    let thread_store = ExtensionData::new("11111111-1111-4111-8111-111111111111");
    thread_store.insert(config);

    registry
        .tool_contributors()
        .iter()
        .flat_map(|contributor| contributor.tools(&session_store, &thread_store))
        .map(|tool| tool.tool_name())
        .collect()
}

#[test]
fn installed_extension_contributes_browser_navigate_when_enabled() {
    assert_eq!(
        installed_tool_names(BrowserExtensionConfig { available: true }),
        vec![ToolName::plain(BROWSER_NAVIGATE_TOOL_NAME)]
    );
}

#[test]
fn installed_extension_contributes_no_tools_when_disabled() {
    assert!(installed_tool_names(BrowserExtensionConfig { available: false }).is_empty());
}

#[test]
fn installed_extension_contributes_no_tools_before_thread_start() {
    let mut builder = ExtensionRegistryBuilder::<Config>::new();
    install(&mut builder);
    let registry = builder.build();
    let session_store = ExtensionData::new("session");
    let thread_store = ExtensionData::new("11111111-1111-4111-8111-111111111111");

    assert!(
        registry
            .tool_contributors()
            .iter()
            .flat_map(|contributor| contributor.tools(&session_store, &thread_store))
            .next()
            .is_none()
    );
}
