class CopilotDOM:
    """CSS selectors and element locators for the Copilot web UI.

    Selectors verified via live DOM probing on copilot.microsoft.com (2026-06-30).
    Update this file when Copilot's DOM structure changes.
    No operation logic here — only locator definitions.

    Key data-testid values (most stable):
      composer-input          — the main textarea
      submit-button           — send button (visible only when input is non-empty)
      composer-background     — outer composer wrapper
      sidebar-new-conversation-nav-item — new chat button

    Response DOM (from class scan):
      .assistant-messages-primary-container — wraps all AI turns
      .message-text                          — inline text span inside each turn
    """

    def find_submit_button(self) -> list[str]:
        return [
            # Most stable: data-testid (confirmed present after typing)
            '[data-testid="submit-button"]',
            # aria-label fallback
            'button[aria-label="Submit message"]',
            'button[aria-label="Submit"]',
            'button[aria-label="Send"]',
        ]

    def find_prompt_input(self) -> list[str]:
        return [
            # Most stable: id + data-testid both confirmed present
            'textarea#userInput',
            '[data-testid="composer-input"]',
            # Generic fallback
            'textarea[placeholder="Message Copilot"]',
            'textarea',
        ]

    def find_model_dropdown(self) -> list[str]:
        return [
            '[data-testid="composer-chat-mode-smart-button"]',
            'button[aria-label*="Response mode"]',
            'div[class*="modelDropdown"]',
            'button[data-testid="model-selector"]',
        ]

    def find_tool_selector(self) -> list[str]:
        return [
            'div[class*="toolSelector"]',
            'button[data-testid="tool-selector"]',
        ]

    def find_sub_tool_selector(self) -> list[str]:
        return [
            'div[class*="subToolSelector"]',
            'div[class*="sub-tool"]',
        ]

    def find_thinking_level_selector(self) -> list[str]:
        return [
            'div[class*="thinkingSelector"]',
            'div[class*="thinking"]',
        ]

    def find_stop_button(self) -> list[str]:
        return [
            # Confirmed aria-label variants seen during generation
            'button[aria-label="Stop responding"]',
            'button[aria-label="Stop response"]',
            'button[aria-label="Stop"]',
            '[data-testid="stop-button"]',
        ]

    def find_redo_button(self) -> list[str]:
        return [
            'button[aria-label="Regenerate"]',
            'button[aria-label="Retry"]',
            '[data-testid="regenerate-button"]',
            'div[class*="regenerateButton"]',
        ]

    def find_new_chat_button(self) -> list[str]:
        return [
            # Confirmed data-testid (sidebar button)
            '[data-testid="sidebar-new-conversation-nav-item"]',
            'button[aria-label="New chat"]',
            'button[aria-label="New topic"]',
            'button[aria-label="New Chat"]',
        ]

    def find_attachment_list(self) -> list[str]:
        return [
            '[data-testid="composer-file-input"]',
            'div[class*="attachmentList"]',
            'div[class*="attachment"]',
        ]

    def find_response_container(self) -> list[str]:
        return [
            # Confirmed from live DOM scan (Script 2)
            '.assistant-messages-primary-container',
            # Fallback class-based selectors
            'div[class*="assistant-messages"]',
            'div[class*="message-container"]',
        ]

    def find_response_text(self) -> list[str]:
        """Selector for the text node(s) inside a response turn."""
        return [
            'span.font-ligatures-none.whitespace-pre-wrap',
            'span.message-text',
            '.message-text',
        ]

    def find_spinner(self) -> list[str]:
        return [
            # The stop button being present means generation is still active
            '[data-testid="stop-button"]',
            'button[aria-label="Stop responding"]',
            'button[aria-label="Stop response"]',
            # Class-based fallbacks
            'div[class*="loadingSpinner"]',
            '.loading-spinner',
            '.generating',
        ]

    def find_image_results(self) -> list[str]:
        return [
            'img[class*="generated"]',
            'img[alt*="generated"]',
            'img',
            'div[class*="image"]',
        ]

    def find_composer(self) -> list[str]:
        """Top-level composer wrapper."""
        return [
            '[data-testid="composer"]',
            '[data-testid="composer-content"]',
            '[data-testid="composer-background"]',
        ]
