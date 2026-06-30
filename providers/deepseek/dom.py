class DeepSeekDOM:
    """CSS selectors and element locators for the DeepSeek web UI.

    Update this file when DeepSeek's DOM structure changes.
    No operation logic here — only locator definitions.
    """

    def find_submit_button(self) -> list[str]:
        return [
            'button[type="submit"]',
            'button[aria-label="Send"]',
            'button[class*="submit"]',
            'button[class*="send"]',
            'div[class*="sendButton"]'
        ]

    def find_prompt_input(self) -> list[str]:
        return [
            'textarea#chat-input',
            'textarea[placeholder*="Ask"]',
            'textarea[aria-label*="Chat"]',
            'textarea',
            'div.ql-editor'
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
        return [
            'button[aria-label="Stop"]',
            'div[class*="stopButton"]',
            'button[class*="stop"]'
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
        return [
            'div[class*="message-container"]',
            '.chat-message',
            '.model-response'
        ]

    def find_spinner(self) -> list[str]:
        return [
            'div[class*="loadingSpinner"]',
            '.loading-spinner',
            '.generating'
        ]

    def find_image_results(self) -> list[str]:
        return [
            'img',
            'div[class*="image"]'
        ]
