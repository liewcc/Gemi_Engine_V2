import asyncio
import logging
from providers.base import ProviderAdapter
from providers.copilot.dom import CopilotDOM

logger = logging.getLogger(__name__)

class CopilotSequences(ProviderAdapter):
    """Operation sequences for the Copilot web UI."""

    def __init__(self, engine):
        self._e = engine
        self._dom = CopilotDOM()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _find_visible_element(self, selectors: list[str], timeout: int = 5000):
        for sel in selectors:
            try:
                locator = self._e._page.locator(sel).first
                if await locator.is_visible(timeout=timeout):
                    return locator
            except Exception:
                continue
        return None

    async def _is_generating(self) -> bool:
        """Return True while Copilot is still streaming a response.

        Uses the Stop button as the "generation in progress" signal — it only
        exists in the DOM while the model is actively generating.
        """
        for sel in self._dom.find_stop_button():
            try:
                if await self._e._page.locator(sel).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_generation_start(self, timeout: float = 10.0) -> bool:
        """Poll until the stop/generating indicator appears (generation started)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_generating():
                return True
            await asyncio.sleep(0.4)
        return False

    async def _get_response_text(self) -> str:
        """Extract the last assistant response text from the page."""
        page = self._e._page

        # Strategy 1: .assistant-messages-primary-container inner text
        for sel in self._dom.find_response_container():
            try:
                loc = page.locator(sel)
                count = await loc.count()
                if count > 0:
                    text = await loc.nth(count - 1).inner_text()
                    text = text.strip()
                    if text:
                        return text
            except Exception:
                continue

        # Strategy 2: span.message-text (last one on page)
        for sel in self._dom.find_response_text():
            try:
                loc = page.locator(sel)
                count = await loc.count()
                if count > 0:
                    text = await loc.nth(count - 1).inner_text()
                    text = text.strip()
                    if text:
                        return text
            except Exception:
                continue

        # Strategy 3: JS-based extraction — grab all visible text blocks
        try:
            result = await page.evaluate("""() => {
                const containers = document.querySelectorAll('.assistant-messages-primary-container, .message-text');
                if (!containers.length) return '';
                const last = containers[containers.length - 1];
                return last.innerText || last.textContent || '';
            }""")
            if result and result.strip():
                return result.strip()
        except Exception as e:
            logger.warning("JS extraction failed: %s", e)

        return ""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def send_prompt(self, text: str):
        if not self._e.is_running:
            raise Exception("Browser Engine not started")

        target = await self._find_visible_element(self._dom.find_prompt_input())
        if not target:
            raise Exception("Could not find prompt input area on Copilot page")

        await target.click()
        await self._e._page.keyboard.press("Control+A")
        await self._e._page.keyboard.press("Backspace")
        await target.fill(text)
        return {"status": "filled", "prompt": text}

    async def attach_file(self, path: str):
        logger.debug("attach_file not fully supported on Copilot web UI stub")
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
            # Fallback: Enter key (Copilot sends on Enter by default)
            await self._e._page.keyboard.press("Enter")
        return {"status": "submitted"}

    async def wait_for_response(self, timeout: int = 180) -> dict:
        """Wait until Copilot finishes generating and return the response text.

        Done-detection strategy:
          1. Wait up to 10 s for the Stop button to appear (generation started).
          2. Poll until the Stop button disappears (generation finished).
          3. Extract response text via multiple fallback selectors.

        The stop-button approach is reliable because Copilot renders it
        only while streaming and removes it immediately on completion.
        """
        if not self._e.is_running:
            raise Exception("Browser Engine not started")

        logger.debug("Waiting for Copilot response (timeout=%ds)…", timeout)
        start_time = asyncio.get_event_loop().time()

        # ── Phase 1: wait for generation to start ─────────────────────
        started = await self._wait_for_generation_start(timeout=10.0)
        if not started:
            logger.warning("Generation did not start within 10 s — checking for immediate response")

        # ── Phase 2: wait for generation to finish ─────────────────────
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self._e._stop_automation_event.is_set():
                await self.stop_response()
                return {"status": "stopped", "message": "Monitoring interrupted"}

            still_generating = await self._is_generating()
            if not still_generating:
                # Small grace period so the DOM can finish updating
                await asyncio.sleep(0.5)
                text = await self._get_response_text()
                if text:
                    logger.debug("Response received (%d chars)", len(text))
                    return {"status": "done", "has_image": False, "text": text}
                # Text not populated yet — keep waiting briefly
                await asyncio.sleep(0.5)
                continue

            await asyncio.sleep(0.8)

        return {"status": "timeout", "message": "Timed out waiting for response"}

    async def get_last_response(self) -> dict:
        if not self._e.is_running:
            return {"text": "", "done": False}
        try:
            text = await self._get_response_text()
            return {"text": text, "done": True}
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
            await self._e.navigate(target_url or "https://copilot.microsoft.com")
        await asyncio.sleep(1.5)

    async def dismiss_agreement_popups(self):
        pass

    async def apply_settings(self, model: str = None, tool: str = None,
                             sub_tool: str = None, thinking_level: str = None):
        logger.debug("apply_settings not fully implemented on Copilot web UI")

    async def discover_capabilities(self) -> dict:
        return {
            "models": ["Smart", "Balanced", "Creative", "Precise"],
            "tools": [],
            "sub_tools": {},
            "thinking_levels": [],
        }

    async def download_images(self, save_dir: str, naming_cfg: dict) -> dict:
        return {"status": "ignored", "count": 0, "saved_paths": []}

    async def delete_history(self, range_name: str = "Last hour"):
        logger.debug("delete_history not implemented on Copilot web UI")

    async def get_account_info(self) -> dict:
        return {"email": "", "name": ""}
