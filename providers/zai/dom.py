class ZaiDOM:
    """CSS selectors and element locators for the z.ai web UI (chat.z.ai).

    Update this file when z.ai's DOM structure changes.
    No operation logic here — only locator definitions.

    Confirmed selectors (from live DOM inspection):
      submit button: button#send-message-button (disabled when input empty)
      file input: input[type="file"] — hidden, sits behind button#upload-file-button.
        Only one on the page; set_input_files() targets it directly instead of
        clicking the button (which would open an OS file picker Playwright can't drive).
    """

    def find_submit_button(self) -> list[str]:
        return [
            'button#send-message-button:not([disabled])',
            'button#send-message-button',
        ]

    def find_prompt_input(self) -> list[str]:
        return [
            'textarea#chat-input',
            'textarea[placeholder="Send a Message"]',
            'textarea',
        ]

    def find_stop_button(self) -> list[str]:
        return [
            'button[aria-label="Stop"]',
            'button[aria-label="Stop generating"]',
            'button#stop-message-button',
        ]

    def find_redo_button(self) -> list[str]:
        return [
            'button[aria-label="Regenerate"]',
            'button[aria-label="Retry"]',
        ]

    def find_new_chat_button(self) -> list[str]:
        return [
            'button[aria-label="New chat"]',
            'button[aria-label="New Chat"]',
            'a[href="/"]',
        ]

    def find_response_container(self) -> list[str]:
        return [
            'div.chat-assistant',
            'div.markdown-prose',
        ]

    def find_spinner(self) -> list[str]:
        # z.ai: during generation the send button stays disabled; stop button appears
        return [
            'button#stop-message-button',
            'button[aria-label="Stop"]',
            'button[aria-label="Stop generating"]',
        ]

    def find_model_dropdown(self) -> list[str]:
        return []

    def find_tool_selector(self) -> list[str]:
        return []

    def find_sub_tool_selector(self) -> list[str]:
        return []

    def find_thinking_level_selector(self) -> list[str]:
        return []

    def find_attachment_list(self) -> list[str]:
        # Each chip is a <button> in the chip-scroll strip above the prompt
        # input; filename text lives in the .truncate child.
        return ['div.chip-scroll > button .truncate']

    def find_attachment_chips(self) -> list[str]:
        # Whole chip (icon + filename + hover-reveal remove button).
        return ['div.chip-scroll > button']

    def find_file_input(self) -> list[str]:
        return ['input[type="file"]']

    def find_image_results(self) -> list[str]:
        return ['img']
