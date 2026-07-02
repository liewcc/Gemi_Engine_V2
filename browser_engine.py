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
from providers.zai.sequences import ZaiSequences

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
        'zai': 'https://chat.z.ai/',
    }

    _PROVIDER_REGISTRY = {
        'gemini': GeminiSequences,
        'deepseek': DeepSeekSequences,
        'copilot': CopilotSequences,
        'zai': ZaiSequences,
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
        self._discovery_cache = {}
        self._providers = {}
        self._sandbox_dir = None
        self._data_dir = os.path.join(os.path.dirname(__file__), 'browser_user_data')
        self._staging_dir = os.path.join(os.path.dirname(__file__), 'registration_staging')
        self.headless = False
        self.active_profile = None
        # Registration browser handles (separate Playwright instance, no sandbox)
        self._reg_playwright = None
        self._reg_context = None
        self._reg_is_new_profile = False
        self._last_registration_result = None
        # ponytail: never-set event; providers check this to abort wait loops
        import asyncio as _asyncio
        self._stop_automation_event = _asyncio.Event()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, headless: bool = True, profile_name: str = None):
        """Launch Chrome via Playwright CDP with optional profile sandbox."""
        if self._reg_context is not None:
            raise Exception("Registration browser is currently open. Close it before starting the main browser.")
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
                '--profile-directory=Default',
                '--disable-blink-features=AutomationControlled',
            ],
        )
        self.browser_pids = [self._browser.process.pid] if hasattr(self._browser, 'process') and self._browser.process else []
        self.headless = headless
        self.active_profile = profile_name

        # Instantiate all providers
        self._providers = {
            name: cls(self) for name, cls in self._PROVIDER_REGISTRY.items()
        }

        # Open one tab per provider and navigate in parallel
        import asyncio
        _stealth_script = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        provider_names = list(self._PROVIDER_REGISTRY.keys())
        existing_pages = self._browser.pages
        for i, name in enumerate(provider_names):
            if i == 0:
                page = existing_pages[0] if existing_pages else await self._browser.new_page()
            else:
                page = await self._browser.new_page()
            await page.add_init_script(_stealth_script)
            self._pages[name] = page
        async def _navigate(name):
            page = self._pages[name]
            url = self.BASE_URLS[name]
            # Use JS navigation to avoid CDP-level automation signals that trigger Cloudflare
            await page.goto('about:blank', wait_until='commit')
            await page.evaluate(f"window.location.href = '{url}'")
            await page.wait_for_load_state('domcontentloaded')

        await asyncio.gather(*[_navigate(name) for name in provider_names])

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
            self._discovery_cache.clear()
            self.is_running = False
            self.browser_pids = []
            self.headless = False
            self.active_profile = None
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
        Opens a headed browser for manual account registration or re-login.
        - profile_name='Profile N': Rebuild / Re-login. Unchanged — opens that specific
          existing profile directly on the real browser_user_data/ (no sandbox).
        - profile_name=None: Create New Profile. Logs in inside an isolated staging
          directory (registration_staging/) that never touches browser_user_data/ or
          its Local State. The real 'Profile N' slot is only computed and committed
          (see _finalize_new_profile_registration, called from stop_registration)
          once the browser is closed AND a real login was actually detected. This
          avoids reserving a slot before knowing whether login happened, and avoids
          the staging Chrome process ever sharing a singleton lock / Local State with
          any other already-running Chrome instance on this machine.
        """
        if self.is_running:
            raise Exception("Main browser is running. Stop it first before opening the registration browser.")
        await self.stop_registration()
        self._last_registration_result = None

        if profile_name:
            # Rebuild / Re-login: use the specified existing profile, directly on the real dir.
            user_data_dir = self._data_dir
            next_profile = profile_name
            self._reg_is_new_profile = False
        else:
            # Create New Profile: fresh isolated staging dir, wiped before each attempt.
            if os.path.exists(self._staging_dir):
                shutil.rmtree(self._staging_dir, ignore_errors=True)
            os.makedirs(self._staging_dir, exist_ok=True)
            user_data_dir = self._staging_dir
            next_profile = 'Default'
            self._reg_is_new_profile = True

            # Seed staging with the real install's Local State (os_crypt key) so
            # cookies/login data Chrome encrypts during this staged login stay
            # decryptable once moved into browser_user_data/. Without this,
            # Chrome generates a fresh random key for the empty staging dir; after
            # commit, switch_account's sandbox copies the REAL Local State's
            # (different) key, which can't decrypt this profile's session data —
            # the newly created account then shows up signed out / empty.
            real_local_state = os.path.join(self._data_dir, 'Local State')
            if os.path.exists(real_local_state):
                shutil.copy2(real_local_state, os.path.join(self._staging_dir, 'Local State'))

        logger.info('start_registration: opening browser on %s (dir=%s)', next_profile, user_data_dir)

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

        if self._reg_context:
            self._reg_context.on("close", lambda ctx: self._on_reg_context_close())

        logger.info('start_registration: browser started on %s', next_profile)
        # For Create New Profile the real slot isn't known until commit time (see
        # _finalize_new_profile_registration) — return None so callers don't display
        # a name that may turn out wrong.
        return None if self._reg_is_new_profile else next_profile

    def _on_reg_context_close(self):
        logger.info("Registration browser context closed.")
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.stop_registration())
        except RuntimeError:
            pass

    async def stop_registration(self):
        """Closes the registration browser if it is open."""
        if getattr(self, '_stopping_registration', False):
            return
        self._stopping_registration = True
        try:
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

            # Now that the browser process is fully torn down and files are unlocked,
            # commit or discard a "Create New Profile" staging session (no-op for Rebuild).
            if getattr(self, '_reg_is_new_profile', False):
                await self._finalize_new_profile_registration()
        finally:
            self._stopping_registration = False

        logger.info('stop_registration: done')

    def _compute_next_profile_slot(self) -> str:
        """Scan Local State + disk in browser_user_data/ for the next unused 'Profile N'."""
        user_data_dir = self._data_dir
        next_profile = 'Profile 1'
        local_state_path = os.path.join(user_data_dir, 'Local State')
        if os.path.exists(local_state_path):
            try:
                with open(local_state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                keys = state.get('profile', {}).get('info_cache', {}).keys()
                nums = [int(k.split()[-1]) for k in keys
                        if k.startswith('Profile ') and k.split()[-1].isdigit()]
                next_num = (max(nums) + 1) if nums else 1
                next_profile = f'Profile {next_num}'
            except Exception as e:
                logger.warning('_compute_next_profile_slot: could not parse Local State, using Profile 1: %s', e)

        try:
            disk_nums = []
            for d in os.listdir(user_data_dir):
                m = re.match(r'^Profile (\d+)$', d)
                if m and os.path.isdir(os.path.join(user_data_dir, d)):
                    disk_nums.append(int(m.group(1)))
            if disk_nums:
                disk_next = max(disk_nums) + 1
                current_next = int(next_profile.split()[-1])
                if disk_next > current_next:
                    next_profile = f'Profile {disk_next}'
        except Exception:
            pass

        return next_profile

    async def _finalize_new_profile_registration(self):
        """Commit or discard a Create New Profile staging session.

        Detects a completed login via registration_staging/Default/Preferences'
        `account_info` — populated by Chrome as soon as the user signs into a
        Google account in ANY tab, regardless of whether they also opt into full
        Chrome-account sync. (Local State's `profile.info_cache[...].user_name` was
        tried first and rejected: it only gets set by the separate, optional
        "turn on Chrome sync" step, so a real, fully-logged-in website session was
        being misclassified as "no login" and discarded.)

        If no account_info is found, the whole staging dir is discarded and
        browser_user_data/ is never touched. If found, only now does this compute
        the real target slot, build a real info_cache entry from the Preferences
        data, merge it into the real Local State, and move the staged profile
        folder into place.
        """
        result = {'status': 'discarded', 'profile': None}
        try:
            account = None
            staging_prefs_path = os.path.join(self._staging_dir, 'Default', 'Preferences')
            if os.path.exists(staging_prefs_path):
                with open(staging_prefs_path, 'r', encoding='utf-8') as f:
                    staged_prefs = json.load(f)
                accounts = staged_prefs.get('account_info') or []
                if accounts and accounts[0].get('email'):
                    account = accounts[0]

            if not account:
                logger.info('_finalize_new_profile_registration: no login detected, discarding staging dir')
            else:
                next_profile = self._compute_next_profile_slot()
                email = account.get('email', '')
                full_name = account.get('full_name') or account.get('given_name') or ''
                new_entry = {
                    'user_name': email,
                    'name': full_name or email,
                    'gaia_name': full_name or email,
                    'gaia_given_name': account.get('given_name', ''),
                    'gaia_id': account.get('gaia', ''),
                }

                real_local_state_path = os.path.join(self._data_dir, 'Local State')
                if os.path.exists(real_local_state_path):
                    with open(real_local_state_path, 'r', encoding='utf-8') as f:
                        real_state = json.load(f)
                else:
                    real_state = {}

                # Fallback for the very first profile ever created (no real Local
                # State existed for start_registration to seed staging with): pull
                # the os_crypt key staging generated for this login back into the
                # real Local State, so it matches what actually encrypted this
                # profile's cookies/login data.
                if 'os_crypt' not in real_state:
                    staged_local_state_path = os.path.join(self._staging_dir, 'Local State')
                    if os.path.exists(staged_local_state_path):
                        try:
                            with open(staged_local_state_path, 'r', encoding='utf-8') as f:
                                staged_state = json.load(f)
                            if 'os_crypt' in staged_state:
                                real_state['os_crypt'] = staged_state['os_crypt']
                        except Exception:
                            pass

                real_profile_block = real_state.setdefault('profile', {})
                real_info_cache = real_profile_block.setdefault('info_cache', {})
                real_info_cache[next_profile] = new_entry
                profiles_order = real_profile_block.setdefault('profiles_order', [])
                if next_profile not in profiles_order:
                    profiles_order.append(next_profile)
                real_profile_block['last_used'] = next_profile
                os.makedirs(self._data_dir, exist_ok=True)
                with open(real_local_state_path, 'w', encoding='utf-8') as f:
                    json.dump(real_state, f, separators=(',', ':'))

                src_dir = os.path.join(self._staging_dir, 'Default')
                dst_dir = os.path.join(self._data_dir, next_profile)
                if os.path.exists(dst_dir):
                    raise Exception(f'Target profile directory {next_profile} already exists')
                shutil.move(src_dir, dst_dir)

                result = {'status': 'success', 'profile': next_profile}
                logger.info('_finalize_new_profile_registration: committed new profile as %s (%s)', next_profile, email)
        except Exception as e:
            logger.error('_finalize_new_profile_registration: %s', e)
            result = {'status': 'error', 'profile': None, 'message': str(e)}
        finally:
            if os.path.exists(self._staging_dir):
                shutil.rmtree(self._staging_dir, ignore_errors=True)
            self._reg_is_new_profile = False
            self._last_registration_result = result
        return result

    # ── Provider / Service ─────────────────────────────────────────────────────

    def _get_provider(self):
        return self._providers[self._active_service]

    async def switch_service(self, service: str):
        """Switch the active provider tab (no navigation — tabs are pre-loaded at start)."""
        if service not in self._PROVIDER_REGISTRY:
            raise ValueError(f"Unknown service: {service}")
        self._active_service = service
        page = self._pages.get(service)
        if page:
            await page.bring_to_front()
        logger.info("switched service to %s", service)

    # ── Account / Profile ──────────────────────────────────────────────────────

    def _cleanup_empty_profiles(self):
        """Delete any empty/leftover Chrome profiles that have no email and are named 'Person *' or are empty."""
        # Check if browser or registration browser is running
        if self._browser is not None:
            return
        if self._reg_context is not None:
            return
        reg_proc = getattr(self, '_reg_chrome_proc', None)
        if reg_proc is not None and reg_proc.poll() is None:
            # Subprocess is still running
            return

        local_state_path = os.path.join(os.path.abspath(self._data_dir), 'Local State')
        if not os.path.exists(local_state_path):
            return

        try:
            with open(local_state_path, 'r', encoding='utf-8') as f:
                local_state = json.load(f)
        except Exception:
            return

        profile_data = local_state.get('profile', {})
        info_cache = profile_data.get('info_cache', {})
        if not info_cache:
            return

        to_delete = []
        for d, info in info_cache.items():
            if not d.startswith('Profile '):
                continue
            email = info.get('user_name', '').strip()
            if not email:
                to_delete.append(d)

        if not to_delete:
            return

        # Delete from disk
        for profile_name in to_delete:
            profile_path = os.path.join(os.path.abspath(self._data_dir), profile_name)
            if os.path.exists(profile_path):
                try:
                    shutil.rmtree(profile_path, ignore_errors=True)
                except Exception:
                    pass

        # Update Local State
        modified = False
        if 'profile' in local_state:
            profile = local_state['profile']
            if 'info_cache' in profile:
                for profile_name in to_delete:
                    if profile_name in profile['info_cache']:
                        del profile['info_cache'][profile_name]
                        modified = True
            if 'profiles_order' in profile:
                orig_len = len(profile['profiles_order'])
                profile['profiles_order'] = [p for p in profile['profiles_order'] if p not in to_delete]
                if len(profile['profiles_order']) != orig_len:
                    modified = True
            if 'last_active_profiles' in profile:
                orig_len = len(profile['last_active_profiles'])
                profile['last_active_profiles'] = [p for p in profile['last_active_profiles'] if p not in to_delete]
                if len(profile['last_active_profiles']) != orig_len:
                    modified = True
            if profile.get('last_used') in to_delete:
                profile['last_used'] = profile['profiles_order'][0] if profile.get('profiles_order') else ''
                modified = True

        if 'variations_google_groups' in local_state:
            for profile_name in to_delete:
                if profile_name in local_state['variations_google_groups']:
                    del local_state['variations_google_groups'][profile_name]
                    modified = True

        if modified:
            try:
                with open(local_state_path, 'w', encoding='utf-8') as f:
                    json.dump(local_state, f, separators=(',', ':'))
            except Exception:
                pass

    def repack_profile_ids(self):
        """Repack profile folders on disk and in Local State so their numbering is continuous."""
        if self.is_running:
            raise RuntimeError("Cannot repack profiles while browser is running")
            
        self._cleanup_empty_profiles()
            
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
        self._cleanup_empty_profiles()
        cache = self._load_profile_cache()
        items = []
        for d, info in cache.items():
            email = info.get('user_name', '').strip()
            name = (info.get('gaia_name') or info.get('name', '')).strip()
            # Filter out profiles that have no email
            if not email:
                continue
            items.append({
                'dir': d,
                'email': email,
                'name': name,
            })

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

    async def get_artifact_code(self) -> dict:
        provider = self._get_provider()
        if not hasattr(provider, 'get_artifact_code'):
            return {"status": "unsupported", "code": None}
        return await provider.get_artifact_code()

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

    async def get_tabs(self) -> dict:
        if not self.is_running or not self._browser:
            return {"tabs": [], "active_service": self._active_service}

        tabs_info = []
        for index, page in enumerate(self._browser.pages):
            try:
                title = await page.title()
            except Exception:
                title = "Untitled"

            # Check if this page corresponds to any known service tab
            associated_service = None
            for service_name, service_page in self._pages.items():
                if service_page == page:
                    associated_service = service_name
                    break

            is_active = (associated_service == self._active_service) if associated_service else False

            tabs_info.append({
                "index": index,
                "title": title,
                "url": page.url,
                "service": associated_service,
                "is_active": is_active
            })

        return {
            "tabs": tabs_info,
            "active_service": self._active_service
        }
