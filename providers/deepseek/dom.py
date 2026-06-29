class DeepSeekDOM:
    """CSS selectors and element locators for the DeepSeek web UI.

    Update this file when DeepSeek's DOM structure changes.
    No operation logic here — only locator definitions.
    """

    def find_submit_button(self):
        raise NotImplementedError

    def find_prompt_input(self):
        raise NotImplementedError

    def find_model_dropdown(self):
        raise NotImplementedError

    def find_tool_selector(self):
        raise NotImplementedError

    def find_sub_tool_selector(self):
        raise NotImplementedError

    def find_thinking_level_selector(self):
        raise NotImplementedError

    def find_stop_button(self):
        raise NotImplementedError

    def find_redo_button(self):
        raise NotImplementedError

    def find_new_chat_button(self):
        raise NotImplementedError

    def find_attachment_list(self):
        raise NotImplementedError

    def find_response_container(self):
        raise NotImplementedError

    def find_spinner(self):
        raise NotImplementedError

    def find_image_results(self):
        raise NotImplementedError
