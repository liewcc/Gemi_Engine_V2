from abc import ABC, abstractmethod


class ProviderAdapter(ABC):
    """Abstract base class defining the interface all provider sequences must implement."""

    @abstractmethod
    async def send_prompt(self, text: str):
        """Type text into the prompt input without submitting."""
        pass

    @abstractmethod
    async def attach_file(self, path: str):
        """Attach a single file to the current prompt."""
        pass

    @abstractmethod
    async def remove_file(self, path: str):
        """Remove a single attached file from the current prompt."""
        pass

    @abstractmethod
    async def get_current_attachments(self) -> list:
        """Return list of currently attached file paths."""
        pass

    @abstractmethod
    async def submit(self):
        """Click the submit button. Does not wait for response."""
        pass

    @abstractmethod
    async def wait_for_response(self, timeout: int = 180) -> dict:
        """Wait until response generation completes. Provider-specific DOM observation."""
        pass

    @abstractmethod
    async def get_last_response(self) -> dict:
        """Read the latest response text and done status."""
        pass

    @abstractmethod
    async def stop_response(self):
        """Click the stop generation button."""
        pass

    @abstractmethod
    async def redo_response(self):
        """Click the redo/regenerate button."""
        pass

    @abstractmethod
    async def new_chat(self, target_url: str = None):
        """Start a new conversation."""
        pass

    @abstractmethod
    async def dismiss_agreement_popups(self):
        """Dismiss any agreement or consent popups."""
        pass

    @abstractmethod
    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        """Apply model/tool/thinking level settings via the provider UI."""
        pass

    @abstractmethod
    async def discover_capabilities(self) -> dict:
        """Scan the UI and return available models, tools, and thinking levels."""
        pass

    @abstractmethod
    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        """Download generated images from the last response."""
        pass

    @abstractmethod
    async def delete_history(self, range_name: str = "Last hour"):
        """Delete provider activity/chat history."""
        pass

    @abstractmethod
    async def get_account_info(self) -> dict:
        """Return current logged-in account information."""
        pass
