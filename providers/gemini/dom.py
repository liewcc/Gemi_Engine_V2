class GeminiDOM:
    """CSS selectors and element locators for the Gemini web UI.

    Update this file when Gemini's DOM structure changes.
    No operation logic here — only locator definitions.
    """

    def find_submit_button(self):
        """Locator for the prompt submit button."""
        raise NotImplementedError

    def find_prompt_input(self):
        """Locator for the prompt text input area."""
        raise NotImplementedError

    def find_model_dropdown(self):
        """Locator for the model selector dropdown trigger."""
        raise NotImplementedError

    def find_tool_selector(self):
        """Locator for the tool selection menu."""
        raise NotImplementedError

    def find_sub_tool_selector(self):
        """Locator for the sub-tool selection (e.g. Imagen 4 Ultra)."""
        raise NotImplementedError

    def find_thinking_level_selector(self):
        """Locator for the thinking level selector."""
        raise NotImplementedError

    def find_stop_button(self):
        """Locator for the stop generation button."""
        raise NotImplementedError

    def find_redo_button(self):
        """Locator for the redo/regenerate button."""
        raise NotImplementedError

    def find_new_chat_button(self):
        """Locator for the new chat button."""
        raise NotImplementedError

    def find_attachment_list(self):
        """Locator for the list of currently attached files."""
        raise NotImplementedError

    def find_response_container(self):
        """Locator for the response output container."""
        raise NotImplementedError

    def find_spinner(self):
        """Locator for the generation-in-progress spinner."""
        raise NotImplementedError

    def find_image_results(self):
        """Locator for generated image elements in the response."""
        raise NotImplementedError
