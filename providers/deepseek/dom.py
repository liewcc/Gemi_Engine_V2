class DeepSeekDOM:
    """CSS selectors and element locators for the DeepSeek web UI.

    Update this file when DeepSeek's DOM structure changes.
    No operation logic here — only locator definitions.
    """

    def find_submit_button(self) -> list[str]:
        # DeepSeek uses a div[role="button"] with DS design-system classes, not <button>.
        # The send button is a circle primary button; when text is present it loses --disabled.
        return [
            'div.ds-button.ds-button--primary.ds-button--filled.ds-button--circle:not(.ds-button--disabled)',
            'div.ds-button--circle:not(.ds-button--disabled)',
            'div[role="button"].ds-button--primary',
        ]

    def find_prompt_input(self) -> list[str]:
        # Live DOM: <textarea placeholder="Message DeepSeek" name="search" ...>
        # The textarea has hashed classes; target by placeholder attribute.
        return [
            'textarea[placeholder="Message DeepSeek"]',
            'textarea[name="search"]',
            'textarea',
        ]

    def find_model_dropdown(self) -> list[str]:
        return [
            'div[class*="modelDropdown"]',
            'div[class*="model-select"]',
            'button[data-testid="model-selector"]'
        ]

    def find_tool_selector(self) -> list[str]:
        return [
            'div[class*="toolSelector"]',
            'button[data-testid="tool-selector"]'
        ]

    def find_sub_tool_selector(self) -> list[str]:
        return [
            'div[class*="subToolSelector"]',
            'div[class*="sub-tool"]'
        ]

    def find_thinking_level_selector(self) -> list[str]:
        return [
            'div[class*="thinkingSelector"]',
            'div[class*="thinking"]'
        ]

    def find_stop_button(self) -> list[str]:
        # During streaming DeepSeek swaps the send button icon to a stop square.
        # The circle button remains but the SVG changes; target the active circle button.
        return [
            'div.ds-button.ds-button--primary.ds-button--filled.ds-button--circle:not(.ds-button--disabled)',
            'div.ds-button--circle:not(.ds-button--disabled)',
            'button[aria-label="Stop"]',
        ]

    def find_redo_button(self) -> list[str]:
        return [
            'button[aria-label="Regenerate"]',
            'div[class*="regenerateButton"]',
            'button[class*="redo"]'
        ]

    def find_new_chat_button(self) -> list[str]:
        return [
            'div[class*="newChatButton"]',
            'button[aria-label="New Chat"]',
            'button.new-chat-button'
        ]

    def find_attachment_list(self) -> list[str]:
        return [
            'div[class*="attachmentList"]',
            'div[class*="attachment"]'
        ]

    def find_response_container(self) -> list[str]:
        # Live DOM (confirmed): DeepSeek renders AI replies inside ds-markdown divs.
        # ds-markdown--block is the outer prose wrapper; ds-markdown alone catches partial renders.
        return [
            'div.ds-markdown.ds-markdown--block',
            'div.ds-markdown',
        ]

    def find_spinner(self) -> list[str]:
        # DeepSeek has no dedicated spinner element in the DOM.
        # During generation the send button is in its non-disabled active state
        # (the icon swaps to a stop square).  We detect "still generating" by
        # checking that at least one ds-markdown block exists but the send
        # button has NOT returned to --disabled yet.  Callers should adapt;
        # this list is kept for legacy compat — none of these match in practice.
        return [
            'div.ds-button--circle:not(.ds-button--disabled)',
        ]

    def find_image_results(self) -> list[str]:
        return [
            'img',
            'div[class*="image"]'
        ]
