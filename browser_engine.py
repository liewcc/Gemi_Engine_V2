import logging
import os
import shutil
import subprocess
from playwright.async_api import async_playwright

from providers.gemini.sequences import GeminiSequences
from providers.deepseek.sequences import DeepSeekSequences
from providers.copilot.sequences import CopilotSequences

logger = logging.getLogger(__name__)


class BrowserEngine:
    """Facade — owns browser lifecycle and provider registry.

    All browser operations are delegated to the active provider.
    This class has no knowledge of business logic, automation, or quotas.
    """

    BASE_URLS = {
        'gemini': 'https://gemini.google.com/app',
        'deepseek': 'https://chat.deepseek.com',
        'copilot': 'https://copilot.microsoft.com',
    }

    _PROVIDER_REGISTRY = {
        'gemini': GeminiSequences,
        'deepseek': DeepSeekSequences,
        'copilot': CopilotSequences,
    }

    def __init__(self):
        self.is_running = False
        self.browser_pids = []
        self._page = None
        self._browser = None
        self._playwright = None
        self._active_service = 'gemini'
        self._providers = {}
        self._sandbox_dir = None
        self._data_dir = os.path.join(os.path.dirname(__file__), '..', 'browser_user_data')

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, headless: bool = True, profile_name: str = None):
        """Launch Chrome via Playwright CDP with optional profile sandbox."""
        source_user_data = os.path.abspath(self._data_dir)
        sandbox_path = os.path.join(os.path.dirname(source_user_data), 'browser_session_sandbox')

        # Clean previous sandbox
        if os.path.exists(sandbox_path):
            self._sandbox_dir = sandbox_path
            await self._cleanup_sandbox()

        self._sandbox_dir = sandbox_path
        os.makedirs(self._sandbox_dir, exist_ok=True)

        # Map profile into sandbox via junction
        if profile_name:
            target_profile = os.path.join(source_user_data, profile_name)
            sandbox_default = os.path.join(self._sandbox_dir, 'Default')
            if os.path.exists(target_profile):
                cmd = f'mklink /J "{sandbox_default}" "{target_profile}"'
                subprocess.run(cmd, shell=True, capture_output=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self._sandbox_dir,
            headless=headless,
            args=['--no-first-run', '--no-default-browser-check'],
        )
        self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()

        self.browser_pids = [self._browser.process.pid] if hasattr(self._browser, 'process') and self._browser.process else []

        # Instantiate all providers
        self._providers = {
            name: cls(self) for name, cls in self._PROVIDER_REGISTRY.items()
        }

        self.is_running = True
        logger.info("engine started headless=%s profile=%s", headless, profile_name)

    async def stop(self):
        """Close browser and clean up sandbox."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("stop: %s", e)
        finally:
            await self._cleanup_sandbox()
            self._browser = None
            self._playwright = None
            self._page = None
            self._providers = {}
            self.is_running = False
            self.browser_pids = []
            logger.info("engine stopped")

    async def _cleanup_sandbox(self):
        if self._sandbox_dir and os.path.exists(self._sandbox_dir):
            try:
                shutil.rmtree(self._sandbox_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("sandbox cleanup failed: %s", e)
        self._sandbox_dir = None

    # ── Provider / Service ─────────────────────────────────────────────────────

    def _get_provider(self):
        return self._providers[self._active_service]

    async def switch_service(self, service: str):
        """Switch to a different provider and navigate to its URL."""
        if service not in self._PROVIDER_REGISTRY:
            raise ValueError(f"Unknown service: {service}")
        self._active_service = service
        await self.navigate(self.BASE_URLS[service])
        logger.info("switched service to %s", service)

    # ── Account / Profile ──────────────────────────────────────────────────────

    async def switch_account(self, username: str, headless: bool = True):
        """Stop current session and restart with the profile matching username."""
        profile_name = self._find_profile_for_username(username)
        await self.stop()
        await self.start(headless=headless, profile_name=profile_name)

    def _find_profile_for_username(self, username: str) -> str | None:
        """Look up which Chrome profile directory corresponds to username."""
        local_state = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        if not os.path.exists(local_state):
            return None
        import json
        with open(local_state, encoding='utf-8') as f:
            state = json.load(f)
        info_cache = state.get('profile', {}).get('info_cache', {})
        for profile_dir, info in info_cache.items():
            user_name = info.get('user_name', '')
            if username.split('@')[0].lower() == user_name.split('@')[0].lower():
                return profile_dir
        return None

    def get_profiles(self) -> list:
        """Return list of available Chrome profile directories."""
        user_data = os.path.abspath(self._data_dir)
        if not os.path.exists(user_data):
            return []
        return [d for d in os.listdir(user_data)
                if os.path.isdir(os.path.join(user_data, d)) and d.startswith('Profile')]

    # ── Browser Primitives ─────────────────────────────────────────────────────

    async def navigate(self, url: str):
        await self._page.goto(url, wait_until='domcontentloaded')

    async def capture_dom(self) -> str:
        return await self._page.content()

    # ── Provider Delegates ─────────────────────────────────────────────────────

    async def send_prompt(self, text: str):
        await self._get_provider().send_prompt(text)

    async def attach_file(self, path: str):
        await self._get_provider().attach_file(path)

    async def remove_file(self, path: str):
        await self._get_provider().remove_file(path)

    async def get_current_attachments(self) -> list:
        return await self._get_provider().get_current_attachments()

    async def submit(self):
        await self._get_provider().submit()

    async def wait_for_response(self, timeout: int = 180) -> dict:
        return await self._get_provider().wait_for_response(timeout=timeout)

    async def get_last_response(self) -> dict:
        return await self._get_provider().get_last_response()

    async def stop_response(self):
        await self._get_provider().stop_response()

    async def redo_response(self):
        await self._get_provider().redo_response()

    async def new_chat(self, target_url: str = None):
        await self._get_provider().new_chat(target_url=target_url)

    async def dismiss_agreement_popups(self):
        await self._get_provider().dismiss_agreement_popups()

    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        await self._get_provider().apply_settings(
            model=model, tool=tool, sub_tool=sub_tool, thinking_level=thinking_level
        )

    async def discover_capabilities(self) -> dict:
        return await self._get_provider().discover_capabilities()

    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        return await self._get_provider().download_images(save_dir, naming_cfg)

    async def delete_history(self, range_name: str = 'Last hour'):
        await self._get_provider().delete_history(range_name)

    async def get_account_info(self) -> dict:
        return await self._get_provider().get_account_info()
