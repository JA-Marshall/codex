//! Extension wiring for the local `browser_navigate` tool.
//!
//! The tool is contributed per thread only when the `browser_navigate` feature is
//! enabled. It is a plain function tool, so unlike the backend-served Playwright browser
//! it needs no ChatGPT apps backend connection and works for any model provider,
//! including Muse lab providers.

use std::sync::Arc;

use codex_core::config::Config;
use codex_extension_api::ConfigContributor;
use codex_extension_api::ExtensionData;
use codex_extension_api::ExtensionFuture;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_extension_api::ThreadLifecycleContributor;
use codex_extension_api::ThreadStartInput;
use codex_extension_api::ToolContributor;
use codex_features::Feature;

use crate::tool::BrowserNavigateTool;

#[derive(Clone)]
struct BrowserExtension;

#[derive(Clone)]
struct BrowserExtensionConfig {
    available: bool,
}

impl From<&Config> for BrowserExtensionConfig {
    fn from(config: &Config) -> Self {
        Self {
            available: config.features.enabled(Feature::BrowserNavigate),
        }
    }
}

impl ThreadLifecycleContributor<Config> for BrowserExtension {
    fn on_thread_start<'a>(
        &'a self,
        input: ThreadStartInput<'a, Config>,
    ) -> ExtensionFuture<'a, ()> {
        Box::pin(async move {
            input
                .thread_store
                .insert(BrowserExtensionConfig::from(input.config));
        })
    }
}

impl ConfigContributor<Config> for BrowserExtension {
    fn on_config_changed(
        &self,
        _session_store: &ExtensionData,
        thread_store: &ExtensionData,
        _previous_config: &Config,
        new_config: &Config,
    ) {
        thread_store.insert(BrowserExtensionConfig::from(new_config));
    }
}

impl ToolContributor for BrowserExtension {
    fn tools(
        &self,
        _session_store: &ExtensionData,
        thread_store: &ExtensionData,
    ) -> Vec<
        Arc<dyn for<'call> codex_extension_api::ToolExecutor<codex_extension_api::ToolCall<'call>>>,
    > {
        let Some(config) = thread_store.get::<BrowserExtensionConfig>() else {
            return Vec::new();
        };
        if !config.available {
            return Vec::new();
        }
        let Ok(tool) = BrowserNavigateTool::with_default_backend() else {
            return Vec::new();
        };

        vec![Arc::new(tool)]
    }
}

/// Installs the local browser tool contributor into the extension registry.
pub fn install(registry: &mut ExtensionRegistryBuilder<Config>) {
    let extension = Arc::new(BrowserExtension);
    registry.thread_lifecycle_contributor(extension.clone());
    registry.config_contributor(extension.clone());
    registry.tool_contributor(extension);
}

#[cfg(test)]
#[path = "extension_tests.rs"]
mod tests;
