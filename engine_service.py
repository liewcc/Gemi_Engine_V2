import asyncio
import logging
import os
import uvicorn
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel

from browser_engine import BrowserEngine
import config_utils

# ── Logging (set up once, all modules inherit) ─────────────────────────────────
logging.basicConfig(
    handlers=[RotatingFileHandler('engine.log', maxBytes=5_000_000, backupCount=3)],
    format='%(asctime)s %(levelname)-8s %(name)-20s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Windows asyncio policy ─────────────────────────────────────────────────────
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ── App + Engine ───────────────────────────────────────────────────────────────
app = FastAPI(title='Gemi Engine V2')
engine = BrowserEngine()


async def _route_service(service: Optional[str]):
    """Switch active provider if service param is given and differs from current."""
    if service and service != engine._active_service:
        await engine.switch_service(service)

# ── Request Models ─────────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    headless: bool = True
    profile_name: Optional[str] = None

class SwitchAccountRequest(BaseModel):
    username: str

class SwitchServiceRequest(BaseModel):
    service: str

class NavigateRequest(BaseModel):
    url: str

class PromptRequest(BaseModel):
    text: str

class FileRequest(BaseModel):
    path: str

class ApplySettingsRequest(BaseModel):
    model: Optional[str] = None
    tool: Optional[str] = None
    sub_tool: Optional[str] = None
    thinking_level: Optional[str] = None
    service: Optional[str] = None

class WaitResponseRequest(BaseModel):
    timeout: int = 180

class DownloadRequest(BaseModel):
    save_dir: str
    prefix: str = 'img'
    padding: int = 4
    start: int = 1
    service: Optional[str] = None

class DeleteHistoryRequest(BaseModel):
    range_name: str = 'Last hour'

# ── Engine Management ──────────────────────────────────────────────────────────
@app.get('/health')
async def health():
    if getattr(engine, '_reg_chrome_proc', None) is not None and engine._reg_chrome_proc.poll() is not None:
        try:
            await engine.stop_registration()
        except Exception:
            pass
    return {
        'status': 'ok',
        'engine_running': engine.is_running,
        'browser_pids': engine.browser_pids,
        'service_pid': os.getpid(),
        'headless': getattr(engine, 'headless', False),
        'active_profile': getattr(engine, 'active_profile', None),
    }

@app.get('/browser/status')
async def browser_status():
    return {
        'engine_running': engine.is_running,
        'url': engine._page.url if engine._page else None,
        'browser_pids': engine.browser_pids,
        'headless': getattr(engine, 'headless', False),
        'active_profile': getattr(engine, 'active_profile', None),
    }

@app.get('/browser/tabs')
async def get_browser_tabs():
    try:
        return await engine.get_tabs()
    except Exception as e:
        logger.error('get_browser_tabs: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/engine/start')
async def start_engine(req: StartRequest):
    if engine.is_running:
        return {'status': 'already_running'}
    try:
        headless = req.headless if req.headless is not None else True
        cfg = config_utils.load_config()
        profile_name = req.profile_name or cfg.get('active_profile')
        await engine.start(headless=headless, profile_name=profile_name)
        return {'status': 'success', 'message': f'Engine started (headless={headless})'}
    except Exception as e:
        logger.error('start_engine: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/engine/stop')
async def stop_engine():
    try:
        await engine.stop()
        return {'status': 'success'}
    except Exception as e:
        logger.error('stop_engine: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

class RegistrationRequest(BaseModel):
    profile_name: Optional[str] = None  # None = auto-pick next slot (Create), set = use existing (Rebuild)

@app.post('/engine/start_registration')
async def start_registration(req: RegistrationRequest = RegistrationRequest()):
    """Start a separate headed browser directly on browser_user_data/ for manual account
    registration or re-login. No sandbox — data written directly to the Profile directory.
    - profile_name=None (default): auto-picks next unused Profile N slot (Create New Profile)
    - profile_name='Profile N': opens that specific existing profile (Rebuild Profile)"""
    try:
        profile = await engine.start_registration(profile_name=req.profile_name)
        return {'status': 'success', 'profile': profile,
                'message': f'Registration browser started on {profile}. Please sign in to Google, then close the browser.'}
    except Exception as e:
        logger.error('start_registration: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/engine/stop_registration')
async def stop_registration():
    """Close the registration browser."""
    try:
        await engine.stop_registration()
        return {'status': 'success'}
    except Exception as e:
        logger.error('stop_registration: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/engine/logs')
async def get_logs(lines: int = Query(200)):
    try:
        if not os.path.exists('engine.log'):
            return {'logs': []}
        with open('engine.log', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        return {'logs': all_lines[-lines:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Account / Profile ──────────────────────────────────────────────────────────
@app.post('/engine/switch_account')
async def switch_account(req: SwitchAccountRequest):
    try:
        await engine.switch_account(req.username)
        return {'status': 'success', 'username': req.username}
    except Exception as e:
        logger.error('switch_account: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/engine/re_login')
async def re_login():
    """Stop and restart with the same profile to force re-login."""
    try:
        profile = engine._find_profile_for_username(
            config_utils.load_config().get('active_user', '')
        )
        await engine.stop()
        await engine.start(profile_name=profile)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/engine/profiles')
async def get_profiles():
    if getattr(engine, '_reg_chrome_proc', None) is not None and engine._reg_chrome_proc.poll() is not None:
        try:
            await engine.stop_registration()
        except Exception:
            pass
    return {'profiles': engine.get_profiles()}

@app.get('/engine/profiles/status')
async def get_profiles_status():
    profiles = engine.get_profiles()
    return {'profiles': profiles, 'active': engine._active_service}

# ── Config ─────────────────────────────────────────────────────────────────────
@app.get('/engine/config')
async def get_config():
    try:
        return config_utils.load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/engine/config')
async def update_config(updates: dict = Body(...)):
    try:
        return config_utils.save_config(updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Browser Atomic Operations ──────────────────────────────────────────────────
@app.post('/browser/navigate')
async def navigate(req: NavigateRequest):
    try:
        await engine.navigate(req.url)
        return {'status': 'success', 'url': req.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/capture_dom')
async def capture_dom():
    try:
        return {'dom': await engine.capture_dom()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/eval')
async def eval_js(script: str = Body(..., embed=True)):
    try:
        result = await engine._page.evaluate(script)
        return {'result': result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/browser/account')
async def get_account():
    try:
        return await engine.get_account_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/switch_service')
async def switch_service(req: SwitchServiceRequest):
    try:
        await engine.switch_service(req.service)
        return {'status': 'success', 'service': req.service}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/discover')
async def discover(service: Optional[str] = Query(None)):
    try:
        await _route_service(service)
        data = await engine.discover_capabilities()
        return {'status': 'success', 'data': data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/apply_settings')
async def apply_settings(req: ApplySettingsRequest):
    try:
        await _route_service(req.service)
        await engine.apply_settings(
            model=req.model, tool=req.tool,
            sub_tool=req.sub_tool, thinking_level=req.thinking_level
        )
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/prompt')
async def set_prompt(req: PromptRequest):
    try:
        await engine.send_prompt(req.text)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/file/add')
async def add_file(req: FileRequest):
    try:
        await engine.attach_file(req.path)
        return {'status': 'success', 'path': req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/file/remove')
async def remove_file(req: FileRequest):
    try:
        await engine.remove_file(req.path)
        return {'status': 'success', 'path': req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/browser/current_attachments')
async def current_attachments():
    try:
        return {'attachments': await engine.get_current_attachments()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/clear_attachments')
async def clear_attachments():
    try:
        await engine.clear_attachments() if hasattr(engine, 'clear_attachments') else None
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/submit')
async def submit():
    try:
        await engine.submit()
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/wait_response')
async def wait_response(req: WaitResponseRequest):
    try:
        result = await engine.wait_for_response(timeout=req.timeout)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/browser/last_response')
async def last_response():
    try:
        return await engine.get_last_response()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/stop')
async def stop_response():
    try:
        await engine.stop_response()
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/redo')
async def redo_response():
    try:
        await engine.redo_response()
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/new_chat')
async def new_chat(service: Optional[str] = Query(None)):
    try:
        await _route_service(service)
        await engine.new_chat()
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/download')
async def download_images(req: DownloadRequest):
    try:
        await _route_service(req.service)
        naming_cfg = {'prefix': req.prefix, 'padding': req.padding, 'start': req.start}
        result = await engine.download_images(req.save_dir, naming_cfg)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/browser/delete_history')
async def delete_history(req: DeleteHistoryRequest):
    try:
        await engine.delete_history(req.range_name)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/browser/screenshot')
async def browser_screenshot(path: str = Query('screenshot.png')):
    try:
        await engine._page.screenshot(path=path)
        return {'status': 'success', 'path': path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/browser/click')
async def browser_click(x: int = Query(...), y: int = Query(...)):
    try:
        await engine._page.mouse.click(x, y)
        return {'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    cfg = config_utils.load_config()
    port = int(cfg.get('port', 18900))
    uvicorn.run(app, host='127.0.0.1', port=port)
