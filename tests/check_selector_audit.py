"""Offline smoke test for _enumerate_locators (no browser needed).

Run:  python check_selector_audit.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from browser_engine import _enumerate_locators, STATE_DEPENDENT
from providers.gemini.dom import GeminiDOM
from providers.deepseek.dom import DeepSeekDOM
from providers.copilot.dom import CopilotDOM
from providers.zai.dom import ZaiDOM


def _run():
    all_doms = [
        ('gemini', GeminiDOM()),
        ('deepseek', DeepSeekDOM()),
        ('copilot', CopilotDOM()),
        ('zai', ZaiDOM()),
    ]

    # Collect all public method names across all four DOM classes
    all_method_names = set()
    for provider, dom in all_doms:
        entries = _enumerate_locators(dom)
        for name, _ in entries:
            all_method_names.add(name)

    # Every name in STATE_DEPENDENT must exist as a public method on at least one DOM class
    orphaned = STATE_DEPENDENT - all_method_names
    assert not orphaned, \
        f'STATE_DEPENDENT contains names not found in any DOM class: {sorted(orphaned)}'

    for provider, dom in all_doms:
        entries = _enumerate_locators(dom)
        names = [name for name, _ in entries]

        # Parameterized methods must be excluded
        if provider == 'gemini':
            assert 'cancel_upload_button' not in names, \
                f'{provider}: cancel_upload_button should be excluded (has required param)'
            assert 'delete_range_menu_item' not in names, \
                f'{provider}: delete_range_menu_item should be excluded (has required param)'

        # A known locator must be present with a non-empty chain
        if provider == 'gemini':
            prompt = dict(entries).get('prompt_input')
            assert prompt is not None, f'{provider}: prompt_input missing'
            assert len(prompt) > 0, f'{provider}: prompt_input chain is empty'

        # zai's empty-chain methods come back as empty lists
        if provider == 'zai':
            model_dd = dict(entries).get('find_model_dropdown')
            assert model_dd is not None, f'{provider}: find_model_dropdown missing'
            assert model_dd == [], f'{provider}: find_model_dropdown should be empty, got {model_dd}'

        print(f'  {provider}: {len(entries)} locators enumerated')

    print('OK')


if __name__ == '__main__':
    _run()
