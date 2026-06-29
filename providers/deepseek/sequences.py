from providers.base import ProviderAdapter
from providers.deepseek.dom import DeepSeekDOM


class DeepSeekSequences(ProviderAdapter):
    """Operation sequences for the DeepSeek web UI."""

    def __init__(self, engine):
        self._e = engine
        self._dom = DeepSeekDOM()

    async def send_prompt(self, text: str):
        raise NotImplementedError

    async def attach_file(self, path: str):
        raise NotImplementedError

    async def remove_file(self, path: str):
        raise NotImplementedError

    async def get_current_attachments(self) -> list:
        raise NotImplementedError

    async def submit(self):
        raise NotImplementedError

    async def wait_for_response(self, timeout: int = 180) -> dict:
        raise NotImplementedError

    async def get_last_response(self) -> dict:
        raise NotImplementedError

    async def stop_response(self):
        raise NotImplementedError

    async def redo_response(self):
        raise NotImplementedError

    async def new_chat(self, target_url: str = None):
        raise NotImplementedError

    async def dismiss_agreement_popups(self):
        raise NotImplementedError

    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        raise NotImplementedError

    async def discover_capabilities(self) -> dict:
        raise NotImplementedError

    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        raise NotImplementedError

    async def delete_history(self, range_name: str = "Last hour"):
        raise NotImplementedError

    async def get_account_info(self) -> dict:
        raise NotImplementedError
