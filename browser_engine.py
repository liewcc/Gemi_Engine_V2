import logging
import os
import shutil
import subprocess
import json
import re
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

    @property
    def browser_pids(self):
        import psutil
        try:
            current_process = psutil.Process(os.getpid())
            children = current_process.children(recursive=True)
            pids = []
            for child in children:
                name = child.name().lower()
                if 'chrome' in name or 'chromium' in name:
                    pids.append(child.pid)
            return pids
        except Exception:
            return []

    @browser_pids.setter
    def browser_pids(self, val):
        pass

    @property
    def is_running(self):
        return getattr(self, '_is_running', False) and len(self.browser_pids) > 0

    @is_running.setter
    def is_running(self, val):
        self._is_running = val

    @property
    def _page(self):
        return self._pages.get(self._active_service)

    @_page.setter
    def _page(self, val):
        pass  # legacy no-op

    def __init__(self):
        self._is_running = False
        self._pages = {}
        self._browser = None
        self._playwright = None
        self._active_service = 'gemini'
        self._providers = {}
        self._sandbox_dir = None
        self._data_dir = os.path.join(os.path.dirname(__file__), 'browser_user_data')
        # Registration browser handles (separate Playwright instance, no sandbox)
        self._reg_playwright = None
        self._reg_context = None
        # ponytail: never-set event; providers check this to abort wait loops
        import asyncio as _asyncio
        self._stop_automation_event = _asyncio.Event()

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
                
                # Copy Local State to preserve DPAPI encrypted master keys for cookie decryption
                source_local_state = os.path.join(source_user_data, 'Local State')
                sandbox_local_state = os.path.join(self._sandbox_dir, 'Local State')
                if os.path.exists(source_local_state):
                    shutil.copy2(source_local_state, sandbox_local_state)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self._sandbox_dir,
            headless=headless,
            args=[
                '--no-first-run',
                '--no-default-browser-check',
                '--profile-directory=Default'
            ],
        )
        self.browser_pids = [self._browser.process.pid] if hasattr(self._browser, 'process') and self._browser.process else []

        # Instantiate all providers
        self._providers = {
            name: cls(self) for name, cls in self._PROVIDER_REGISTRY.items()
        }

        # Open one tab per provider and navigate in parallel
        import asyncio
        provider_names = list(self._PROVIDER_REGISTRY.keys())
        existing_pages = self._browser.pages
        for i, name in enumerate(provider_names):
            if i == 0:
                page = existing_pages[0] if existing_pages else await self._browser.new_page()
            else:
                page = await self._browser.new_page()
            self._pages[name] = page
        await asyncio.gather(*[
            self._pages[name].goto(self.BASE_URLS[name], wait_until='domcontentloaded')
            for name in provider_names
        ])

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
            self._pages = {}
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

    async def start_registration(self, profile_name: str = None):
        """
        Opens a headed browser directly on browser_user_data/ (NO sandbox) for manual
        account registration or re-login.  Mirrors V1's start_registration() exactly:
        - Ignores automation-detection args so Google allows sign-in
        - Writes all data directly to the real profile directory (no sandbox cleanup)
        - profile_name=None: auto-picks the next unused Profile N slot (Create New Profile)
        - profile_name='Profile N': opens that specific profile (Rebuild / Re-login)
        """
        await self.stop_registration()

        user_data_dir = self._data_dir  # e.g. .../browser_user_data

        if profile_name:
            # Rebuild / Re-login: use the specified existing profile
            next_profile = profile_name
        else:
            # Create New Profile: pick the next available slot
            next_profile = 'Profile 1'
            local_state_path = os.path.join(user_data_dir, 'Local State')
            if os.path.exists(local_state_path):
                try:
                    import json as _json
                    with open(local_state_path, 'r', encoding='utf-8') as f:
                        state = _json.load(f)
                    keys = state.get('profile', {}).get('info_cache', {}).keys()
                    nums = [int(k.split()[-1]) for k in keys
                            if k.startswith('Profile ') and k.split()[-1].isdigit()]
                    next_num = (max(nums) + 1) if nums else 1
                    next_profile = f'Profile {next_num}'
                except Exception as e:
                    logger.warning('start_registration: could not parse Local State, using Profile 1: %s', e)

            # Also cross-check disk dirs in case Local State is out of date
            try:
                disk_nums = []
                for d in os.listdir(user_data_dir):
                    import re as _re
                    m = _re.match(r'^Profile (\d+)$', d)
                    if m and os.path.isdir(os.path.join(user_data_dir, d)):
                        disk_nums.append(int(m.group(1)))
                if disk_nums:
                    disk_next = max(disk_nums) + 1
                    current_next = int(next_profile.split()[-1])
                    if disk_next > current_next:
                        next_profile = f'Profile {disk_next}'
            except Exception:
                pass

        logger.info('start_registration: opening browser on %s', next_profile)

        # Look for official Google Chrome installation to bypass Google's automation bot checks
        chrome_exe = None
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        paths_to_check = [
            os.path.join(local_app_data, 'Google', 'Chrome', 'Application', 'chrome.exe'),
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                chrome_exe = p
                break

        self._reg_playwright = await async_playwright().start()

        if chrome_exe:
            logger.info('start_registration: found real Chrome at %s, launching via CDP', chrome_exe)
            try:
                import socket
                import asyncio

                cmd = [
                    chrome_exe,
                    '--remote-debugging-port=9222',
                    f'--user-data-dir={user_data_dir}',
                    f'--profile-directory={next_profile}',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--test-type',
                    '--no-sandbox'
                ]
                self._reg_chrome_proc = subprocess.Popen(cmd)

                # Wait for port 9222 to open
                port_ready = False
                for _ in range(20):
                    try:
                        with socket.create_connection(('127.0.0.1', 9222), timeout=0.5):
                            port_ready = True
                            break
                    except OSError:
                        await asyncio.sleep(0.5)

                if not port_ready:
                    raise Exception('Timeout waiting for Chrome CDP port 9222')

                self._reg_browser = await self._reg_playwright.chromium.connect_over_cdp('http://localhost:9222')
                self._reg_context = self._reg_browser.contexts[0] if self._reg_browser.contexts else await self._reg_browser.new_context()
                logger.info('start_registration: successfully connected to Chrome over CDP')
            except Exception as e:
                logger.warning('start_registration: failed to launch real Chrome over CDP (%s), falling back to bundled Chromium', e)
                # Ensure subprocess is cleaned up on failure before fallback
                if hasattr(self, '_reg_chrome_proc') and self._reg_chrome_proc:
                    try:
                        self._reg_chrome_proc.terminate()
                    except Exception:
                        pass
                    self._reg_chrome_proc = None
                chrome_exe = None

        if not chrome_exe:
            # Fallback to bundled Chromium
            self._reg_context = await self._reg_playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                ignore_default_args=['--enable-automation', '--use-mock-keychain'],
                args=[
                    f'--profile-directory={next_profile}',
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
                ignore_https_errors=True,
                bypass_csp=True,
            )

        logger.info('start_registration: browser started on %s', next_profile)
        return next_profile

    async def stop_registration(self):
        """Closes the registration browser if it is open."""
        if self._reg_context:
            try:
                await self._reg_context.close()
            except Exception as e:
                logger.warning('stop_registration: close error: %s', e)
            self._reg_context = None
        if hasattr(self, '_reg_browser') and self._reg_browser:
            try:
                await self._reg_browser.close()
            except Exception:
                pass
            self._reg_browser = None
        if self._reg_playwright:
            try:
                import asyncio
                await asyncio.wait_for(self._reg_playwright.stop(), timeout=5.0)
            except Exception as e:
                logger.warning('stop_registration: stop error: %s', e)
            self._reg_playwright = None
        
        # Kill the child subprocess if we launched Chrome directly
        if hasattr(self, '_reg_chrome_proc') and self._reg_chrome_proc:
            try:
                pid = self._reg_chrome_proc.pid
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
                else:
                    self._reg_chrome_proc.terminate()
            except Exception as e:
                logger.warning('stop_registration: failed to kill chrome process tree: %s', e)
            self._reg_chrome_proc = None

        logger.info('stop_registration: done')

    # ── Provider / Service ─────────────────────────────────────────────────────

    def _get_provider(self):
        return self._providers[self._active_service]

    async def switch_service(self, service: str):
        """Switch the active provider tab (no navigation — tabs are pre-loaded at start)."""
        if service not in self._PROVIDER_REGISTRY:
            raise ValueError(f"Unknown service: {service}")
        self._active_service = service
        logger.info("switched service to %s", service)

    # ── Account / Profile ──────────────────────────────────────────────────────

    def repack_profile_ids(self):
        """Repack profile folders on disk and in Local State so their numbering is continuous."""
        if self.is_running:
            raise RuntimeError("Cannot repack profiles while browser is running")
            
        profiles_path = os.path.abspath(self._data_dir)
        if not os.path.exists(profiles_path):
            return
            
        profile_folders = []
        for d in os.listdir(profiles_path):
            if re.match(r'^Profile \d+$', d):
                if os.path.isdir(os.path.join(profiles_path, d)):
                    profile_folders.append(d)
                    
        profile_folders.sort(key=lambda x: int(x.split(' ')[1]))
        
        rename_map = {}
        for index, folder in enumerate(profile_folders, start=1):
            expected_name = f'Profile {index}'
            if folder != expected_name:
                os.rename(os.path.join(profiles_path, folder), os.path.join(profiles_path, expected_name))
                rename_map[folder] = expected_name
            else:
                rename_map[folder] = expected_name
                
        local_state_path = os.path.join(profiles_path, 'Local State')
        if os.path.exists(local_state_path):
            with open(local_state_path, 'r', encoding='utf-8') as f:
                try:
                    local_state = json.load(f)
                except json.JSONDecodeError:
                    local_state = {}
            
            profile = local_state.setdefault('profile', {})
            info_cache = profile.setdefault('info_cache', {})
            
            new_info_cache = {}
            for old_name, info in info_cache.items():
                if re.match(r'^Profile \d+$', old_name):
                    if old_name in rename_map:
                        new_info_cache[rename_map[old_name]] = info
                else:
                    new_info_cache[old_name] = info

            original_order = profile.get('profiles_order', [])
            new_profiles_order = []
            for p in original_order:
                if not re.match(r'^Profile \d+$', p):
                    if p in new_info_cache:
                        new_profiles_order.append(p)
            
            new_profiles_order.extend(sorted(rename_map.values(), key=lambda x: int(x.split(' ')[1])))

            profile['info_cache'] = new_info_cache
            profile['profiles_order'] = new_profiles_order
            profile['profiles_created'] = len(rename_map)
            
            last_used = profile.get('last_used', '')
            if re.match(r'^Profile \d+$', last_used):
                if last_used in rename_map:
                    profile['last_used'] = rename_map[last_used]
                else:
                    profile['last_used'] = 'Profile 1' if rename_map else ''
                    
            if 'last_active_profiles' in profile:
                new_last_active = []
                for p in profile['last_active_profiles']:
                    if re.match(r'^Profile \d+$', p):
                        if p in rename_map:
                            new_last_active.append(rename_map[p])
                    else:
                        new_last_active.append(p)
                profile['last_active_profiles'] = new_last_active
                
            if 'variations_google_groups' in local_state:
                new_vgg = {}
                for old_name, val in local_state['variations_google_groups'].items():
                    if re.match(r'^Profile \d+$', old_name):
                        if old_name in rename_map:
                            new_vgg[rename_map[old_name]] = val
                    else:
                        new_vgg[old_name] = val
                local_state['variations_google_groups'] = new_vgg
                
            with open(local_state_path, 'w', encoding='utf-8') as f:
                json.dump(local_state, f, separators=(',', ':'))
                
        config_path = os.path.join(os.path.dirname(profiles_path), 'data', 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    config = {}
            if 'active_profile' in config:
                active = config['active_profile']
                if active and re.match(r'^Profile \d+$', active):
                    if active in rename_map:
                        config['active_profile'] = rename_map[active]
                    else:
                        config['active_profile'] = None
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)

    def delete_profile(self, profile_name: str):
        """Delete a profile from disk and remove it from Local State and config."""
        if self.is_running:
            raise RuntimeError("Cannot delete profiles while browser is running")
            
        profile_path = os.path.join(os.path.abspath(self._data_dir), profile_name)
        if os.path.exists(profile_path):
            shutil.rmtree(profile_path, ignore_errors=True)
            
        local_state_path = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        if os.path.exists(local_state_path):
            with open(local_state_path, 'r', encoding='utf-8') as f:
                try:
                    local_state = json.load(f)
                except json.JSONDecodeError:
                    local_state = {}
                    
            if 'profile' in local_state:
                profile = local_state['profile']
                if 'info_cache' in profile and profile_name in profile['info_cache']:
                    del profile['info_cache'][profile_name]
                if 'profiles_order' in profile and profile_name in profile['profiles_order']:
                    profile['profiles_order'].remove(profile_name)
                if 'last_active_profiles' in profile and profile_name in profile['last_active_profiles']:
                    profile['last_active_profiles'].remove(profile_name)
                if profile.get('last_used') == profile_name:
                    profile['last_used'] = profile.get('profiles_order', [''])[0] if profile.get('profiles_order') else ''
                    
            if 'variations_google_groups' in local_state and profile_name in local_state['variations_google_groups']:
                del local_state['variations_google_groups'][profile_name]
                
            with open(local_state_path, 'w', encoding='utf-8') as f:
                json.dump(local_state, f, separators=(',', ':'))
                
        config_path = os.path.join(os.path.dirname(os.path.abspath(self._data_dir)), 'data', 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    config = {}
            if config.get('active_profile') == profile_name:
                config['active_profile'] = None
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)

    def create_profile(self, email: str = '', name: str = '') -> str:
        """Create a new Chrome profile with the next available Profile N ID."""
        if self.is_running:
            raise RuntimeError("Cannot create profiles while browser is running")
            
        local_state_path = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        local_state = {}
        if os.path.exists(local_state_path):
            with open(local_state_path, 'r', encoding='utf-8') as f:
                try:
                    local_state = json.load(f)
                except json.JSONDecodeError:
                    pass
                    
        profile_data = local_state.setdefault('profile', {})
        info_cache = profile_data.setdefault('info_cache', {})
        profiles_order = profile_data.setdefault('profiles_order', [])
        
        max_n = 0
        for p in info_cache.keys():
            m = re.match(r'^Profile (\d+)$', p)
            if m:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
                    
        new_n = max_n + 1
        new_profile_name = f'Profile {new_n}'
        
        new_profile_dir = os.path.join(os.path.abspath(self._data_dir), new_profile_name)
        os.makedirs(new_profile_dir, exist_ok=True)
        
        info_cache[new_profile_name] = {
            "user_name": email,
            "name": name,
            "gaia_name": name
        }
        
        if new_profile_name not in profiles_order:
            profiles_order.append(new_profile_name)
            
        profile_data['profiles_created'] = new_n
        
        with open(local_state_path, 'w', encoding='utf-8') as f:
            json.dump(local_state, f, separators=(',', ':'))
            
        return new_profile_name

    def edit_profile_name(self, profile_name: str, new_name: str):
        """Update the name and gaia_name for a profile in Local State."""
        if self.is_running:
            raise RuntimeError("Cannot edit profiles while browser is running")
            
        local_state_path = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        if not os.path.exists(local_state_path):
            return
            
        with open(local_state_path, 'r', encoding='utf-8') as f:
            try:
                local_state = json.load(f)
            except json.JSONDecodeError:
                return
                
        profile = local_state.get('profile', {})
        info_cache = profile.get('info_cache', {})
        
        if profile_name in info_cache:
            info_cache[profile_name]['name'] = new_name
            info_cache[profile_name]['gaia_name'] = new_name
            
            with open(local_state_path, 'w', encoding='utf-8') as f:
                json.dump(local_state, f, separators=(',', ':'))

    async def switch_account(self, username: str, headless: bool = True):
        """Stop current session and restart with the profile matching username."""
        profile_name = self._find_profile_for_username(username)
        await self.stop()
        await self.start(headless=headless, profile_name=profile_name)

    def _load_profile_cache(self) -> dict:
        local_state = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        if not os.path.exists(local_state):
            return {}
        import json
        with open(local_state, encoding='utf-8') as f:
            return json.load(f).get('profile', {}).get('info_cache', {})

    def _find_profile_for_username(self, username: str) -> str | None:
        """Look up Chrome profile dir by email, display name, or gaia name."""
        needle = username.lower()
        for profile_dir, info in self._load_profile_cache().items():
            candidates = [
                info.get('user_name', ''),
                info.get('name', ''),
                info.get('gaia_name', ''),
            ]
            for c in candidates:
                if needle == c.lower() or needle == c.split('@')[0].lower():
                    return profile_dir
        return None

    def get_profiles(self) -> list:
        """Return all Chrome profiles with email and display name."""
        cache = self._load_profile_cache()
        items = [
            {
                'dir': d,
                'email': info.get('user_name', ''),
                'name': info.get('gaia_name') or info.get('name', ''),
            }
            for d, info in cache.items()
        ]

        def profile_key(item):
            directory = item.get('dir', '')
            import re
            m = re.match(r'^Profile (\d+)$', directory)
            if m:
                return (0, int(m.group(1)))
            else:
                return (1, directory)

        items.sort(key=profile_key)
        return items

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
