class GeminiDOM:
    """CSS selectors and element locators for the Gemini web UI.

    Update this file when Gemini's DOM structure changes.
    No operation logic here — only locator definitions.
    """

    # ── Prompt Input ───────────────────────────────────────────────────────────

    def prompt_input(self) -> list[str]:
        """Multiple fallback selectors for the prompt input area."""
        return [
            "div[aria-label='Enter a prompt for Gemini']",
            "div[aria-label='Enter a prompt here']",
            ".ql-editor",
            "textarea[aria-label='Enter a prompt for Gemini']",
            "textarea[aria-label='Enter a prompt here']",
        ]

    # ── Submit / Stop / Redo ───────────────────────────────────────────────────

    def submit_button(self) -> str:
        return (
            'gem-icon-button.submit button[aria-label="Send message"], '
            'gem-icon-button.send-button button[aria-label="Send message"], '
            'button[aria-label="Send message"]'
        )

    def stop_button(self) -> str:
        return 'button[aria-label="Stop response"]'

    def redo_button(self) -> str:
        return '[data-automation-temp-redo="true"]'

    def try_again_button(self) -> str:
        return '[data-automation-temp-tryagain="true"]'

    # ── New Chat ───────────────────────────────────────────────────────────────

    def new_chat_link(self) -> str:
        return 'a[aria-label="New chat"]'

    def new_chat_button(self) -> str:
        return 'button[aria-label="New chat"]'

    # ── Model / Tool Selection ─────────────────────────────────────────────────

    def model_menu_button(self) -> str:
        return 'button[data-test-id="bard-mode-menu-button"]'

    def upload_tools_button(self) -> list[str]:
        return [
            'button[aria-label="Upload & tools"]',
            'button.toolbox-drawer-button',
        ]

    def more_upload_button(self) -> str:
        return 'button.more-upload-button'

    def more_tools_button(self) -> str:
        return 'button.more-tools-button'

    def tool_drawer_item(self) -> str:
        return 'toolbox-drawer-item'

    # ── Attachments ────────────────────────────────────────────────────────────

    def cancel_upload_button(self, file_name: str) -> str:
        return f'button[data-test-id="cancel-button"][aria-label*="{file_name}"]'

    def cancel_upload_buttons(self) -> str:
        return 'button[data-test-id="cancel-button"], button[aria-label="close attachment"]'

    # ── Response Detection ─────────────────────────────────────────────────────

    def processing_state_container(self) -> str:
        return 'section.processing-state_container--processing'

    def response_container(self) -> str:
        """Last response message block."""
        return 'model-response'

    def image_results(self) -> str:
        return (
            'single-image img, img.generated-image, .generated-image img, '
            '.image-container img, img[alt*="generated" i], img[src^="blob:"]'
        )

    # ── Image Download ─────────────────────────────────────────────────────────

    def download_full_size_button(self) -> str:
        return 'button[aria-label="Download full-sized image"]'

    # ── Popups / Agreements ────────────────────────────────────────────────────

    def agreement_popup_buttons(self) -> list[str]:
        return [
            'button[aria-label="Dismiss"]',
            'button:has-text("I agree")',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
        ]

    # ── Account / Profile ──────────────────────────────────────────────────────

    def account_avatar(self) -> str:
        return (
            'a[href*="accounts.google.com/SignOut"], '
            '[aria-label*="Google Account"], '
            'img.mavatar-image, img.gb_n, '
            'img[src*="googleusercontent.com/a/"]'
        )

    # ── Activity / History ─────────────────────────────────────────────────────

    def delete_activity_button(self) -> str:
        return 'button[aria-label="Delete"]'

    def delete_range_menu_item(self, range_name: str) -> str:
        return f'li[role="menuitem"]:has-text("{range_name}")'

    def modal_delete_button(self) -> str:
        return 'button:has-text("Delete"), button[jsname="nUV0Pd"]'

    def modal_confirm_button(self) -> str:
        return 'button:has-text("Got it"), button:has-text("OK")'

    # ── Conversations List ─────────────────────────────────────────────────────

    def conversations_list(self) -> str:
        return '[data-test-id="chat-history-container"], div[data-test-id="conversations-list"]'
