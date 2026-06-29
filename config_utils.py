import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'data', 'config.json')

_DEFAULTS = {
    'headless': True,
    'active_profile': None,
    'active_user': '',
    'active_service': 'gemini',
}


def load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        return dict(_DEFAULTS)
    with open(_CONFIG_PATH, encoding='utf-8') as f:
        data = json.load(f)
    return {**_DEFAULTS, **data}


def save_config(updates: dict) -> dict:
    current = load_config()
    current.update(updates)
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    return current
