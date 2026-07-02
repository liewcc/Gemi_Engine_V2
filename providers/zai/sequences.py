import asyncio
import logging
import os

from providers.base import ProviderAdapter
from providers.zai.dom import ZaiDOM

logger = logging.getLogger(__name__)


class ZaiSequences(ProviderAdapter):
    """Operation sequences for the z.ai web UI (chat.z.ai)."""

    BASE_URL = "https://chat.z.ai/"

    def __init__(self, engine):
        self._e = engine
        self._dom = ZaiDOM()

    async def _find_visible(self, selectors: list[str], timeout: int = 5000):
        for sel in selectors:
            try:
                loc = self._e._page.locator(sel).first
                if await loc.is_visible(timeout=timeout):
                    return loc
            except Exception:
                continue
        return None

    async def _is_generating(self) -> bool:
        for sel in self._dom.find_spinner():
            try:
                if await self._e._page.locator(sel).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    async def send_prompt(self, text: str):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        target = await self._find_visible(self._dom.find_prompt_input())
        if not target:
            raise Exception("Could not find prompt input area on z.ai page")
        await target.click()
        await self._e._page.keyboard.press("Control+A")
        await self._e._page.keyboard.press("Backspace")
        await target.fill(text)
        return {"status": "filled", "prompt": text}

    async def attach_file(self, path: str):
        """Upload a local file via z.ai's hidden file input.

        button#upload-file-button opens an OS file picker Playwright can't
        drive — instead this sets files directly on the <input type="file">
        it proxies to, which is what set_input_files() is for.
        """
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        if not os.path.exists(path):
            raise FileNotFoundError(f"attach_file: file not found: {path}")

        file_input = self._e._page.locator(self._dom.find_file_input()[0]).first
        await file_input.set_input_files(path)
        await asyncio.sleep(1.0)
        logger.debug("attach_file: uploaded %s", path)

    async def remove_file(self, path: str):
        """Click the hover-reveal remove (x) button on the chip whose
        filename stem matches `path`. The remove button is CSS-hidden until
        the chip is hovered (group-hover:visible), so the click is forced
        rather than hovering first.
        """
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        chips = self._e._page.locator(self._dom.find_attachment_chips()[0])
        count = await chips.count()
        for i in range(count):
            chip = chips.nth(i)
            try:
                name = (await chip.locator('.truncate').first.inner_text()).strip()
            except Exception:
                continue
            if os.path.splitext(name)[0].lower() == stem:
                await chip.locator('button').first.click(force=True)
                await asyncio.sleep(0.5)
                logger.debug("remove_file: removed %s", name)
                return
        logger.debug("remove_file: no attachment matched stem=%s", stem)

    async def get_current_attachments(self) -> list:
        try:
            return await self._e._page.evaluate(
                '''(sel) => Array.from(document.querySelectorAll(sel)).map(el => el.textContent.trim())''',
                self._dom.find_attachment_list()[0],
            )
        except Exception:
            return []

    async def submit(self):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        target = await self._find_visible(self._dom.find_submit_button())
        if target:
            await target.click()
        else:
            await self._e._page.keyboard.press("Enter")
        return {"status": "submitted"}

    async def wait_for_response(self, timeout: int = 180) -> dict:
        if not self._e.is_running:
            raise Exception("Browser Engine not started")

        start = asyncio.get_event_loop().time()

        # Phase 1: wait up to 10s for generation to start
        deadline = start + 10.0
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_generating():
                break
            await asyncio.sleep(0.4)

        # Phase 2: wait for generation to finish
        while asyncio.get_event_loop().time() - start < timeout:
            if self._e._stop_automation_event.is_set():
                await self.stop_response()
                return {"status": "stopped", "message": "Monitoring interrupted"}
            if not await self._is_generating():
                await asyncio.sleep(0.5)
                resp = await self.get_last_response()
                if resp.get("text"):
                    return {"status": "done", "has_image": False, "text": resp["text"]}
            await asyncio.sleep(0.8)

        return {"status": "timeout", "message": "Timed out waiting for response"}

    async def get_last_response(self) -> dict:
        if not self._e.is_running:
            return {"text": "", "done": False}
        try:
            for sel in self._dom.find_response_container():
                loc = self._e._page.locator(sel)
                count = await loc.count()
                if count > 0:
                    text = await loc.nth(count - 1).inner_text()
                    if text.strip():
                        return {"text": text.strip(), "done": True}
        except Exception as e:
            logger.warning("get_last_response error: %s", e)
        return {"text": "", "done": True}

    async def stop_response(self):
        if not self._e.is_running:
            return
        target = await self._find_visible(self._dom.find_stop_button(), timeout=2000)
        if target:
            await target.click()

    async def redo_response(self):
        if not self._e.is_running:
            return
        target = await self._find_visible(self._dom.find_redo_button(), timeout=2000)
        if target:
            await target.click()

    async def new_chat(self, target_url: str = None):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")
        target = await self._find_visible(self._dom.find_new_chat_button(), timeout=2000)
        if target:
            await target.click()
        else:
            await self._e.navigate(target_url or self.BASE_URL)
        await asyncio.sleep(1.5)

    async def dismiss_agreement_popups(self):
        pass

    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        logger.debug("apply_settings not implemented for z.ai")

    async def discover_capabilities(self) -> dict:
        return {
            "models": [],
            "tools": [],
            "sub_tools": {},
            "thinking_levels": [],
        }

    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        return {"status": "ignored", "count": 0, "saved_paths": []}

    async def delete_history(self, range_name: str = "Last hour"):
        logger.debug("delete_history not implemented for z.ai")

    async def get_account_info(self) -> dict:
        return {"email": "", "name": ""}
