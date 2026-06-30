import asyncio
import logging
from providers.base import ProviderAdapter
from providers.deepseek.dom import DeepSeekDOM

logger = logging.getLogger(__name__)

class DeepSeekSequences(ProviderAdapter):
    """Operation sequences for the DeepSeek web UI."""

    def __init__(self, engine):
        self._e = engine
        self._dom = DeepSeekDOM()

    async def _find_visible_element(self, selectors: list[str], timeout: int = 5000):
        for sel in selectors:
            try:
                locator = self._e._page.locator(sel).first
                if await locator.is_visible(timeout=timeout):
                    return locator
            except Exception:
                continue
        return None

    async def send_prompt(self, text: str):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        
        target = await self._find_visible_element(self._dom.find_prompt_input())
        if not target:
            raise Exception("Could not find prompt input area on DeepSeek page")
        
        await target.click()
        await self._e._page.keyboard.press("Control+A")
        await self._e._page.keyboard.press("Backspace")
        await target.fill(text)
        return {"status": "filled", "prompt": text}

    async def attach_file(self, path: str):
        logger.debug("attach_file not fully supported on DeepSeek web UI stub")
        return {"status": "ignored"}

    async def remove_file(self, path: str):
        return {"status": "ignored"}

    async def get_current_attachments(self) -> list:
        return []

    async def submit(self):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        
        target = await self._find_visible_element(self._dom.find_submit_button())
        if target:
            await target.click()
        else:
            await self._e._page.keyboard.press("Enter")
        return {"status": "submitted"}

    async def wait_for_response(self, timeout: int = 180) -> dict:
        if not self._e.is_running:
            raise Exception("Browser Engine not started")

        logger.debug("Waiting for DeepSeek response...")
        start_time = asyncio.get_event_loop().time()
        
        # Wait up to 5s for generation to start
        await asyncio.sleep(1.0)
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self._e._stop_automation_event.is_set():
                await self.stop_response()
                return {"status": "stopped", "message": "Monitoring interrupted"}

            # Check if loading spinner/generating indicator is visible
            spinner_visible = False
            for sel in self._dom.find_spinner():
                try:
                    if await self._e._page.locator(sel).first.is_visible(timeout=1000):
                        spinner_visible = True
                        break
                except Exception:
                    continue
            
            if not spinner_visible:
                # Generation complete! Get last response text.
                resp = await self.get_last_response()
                if resp.get("text"):
                    return {"status": "done", "has_image": False, "text": resp["text"]}
            
            await asyncio.sleep(1.5)
            
        return {"status": "timeout", "message": "Timed out waiting for response"}

    async def get_last_response(self) -> dict:
        if not self._e.is_running:
            return {"text": "", "done": False}
        try:
            # Locate all messages
            selectors = self._dom.find_response_container()
            for sel in selectors:
                locators = self._e._page.locator(sel)
                count = await locators.count()
                if count > 0:
                    text = await locators.nth(count - 1).inner_text()
                    return {"text": text.strip(), "done": True}
        except Exception as e:
            logger.warning("get_last_response error: %s", e)
        return {"text": "", "done": True}

    async def stop_response(self):
        if not self._e.is_running:
            return
        target = await self._find_visible_element(self._dom.find_stop_button(), timeout=2000)
        if target:
            await target.click()

    async def redo_response(self):
        if not self._e.is_running:
            return
        target = await self._find_visible_element(self._dom.find_redo_button(), timeout=2000)
        if target:
            await target.click()

    async def new_chat(self, target_url: str = None):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        
        target = await self._find_visible_element(self._dom.find_new_chat_button(), timeout=2000)
        if target:
            await target.click()
        else:
            await self._e.navigate(target_url or "https://chat.deepseek.com")
        await asyncio.sleep(1.5)

    async def dismiss_agreement_popups(self):
        pass

    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        logger.debug("apply_settings not fully implemented on DeepSeek web UI")

    async def discover_capabilities(self) -> dict:
        return {
            "models": ["deepseek-chat", "deepseek-coder"],
            "tools": [],
            "sub_tools": {},
            "thinking_levels": ["Low", "High"]
        }

    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        return {"status": "ignored", "count": 0, "saved_paths": []}

    async def delete_history(self, range_name: str = "Last hour"):
        logger.debug("delete_history not implemented on DeepSeek web UI")

    async def get_account_info(self) -> dict:
        return {"email": "", "name": ""}
