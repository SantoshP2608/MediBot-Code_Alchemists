"""Bounded public-page rendering for pharmacy product discovery."""
import json
import os
from threading import BoundedSemaphore

_slots = BoundedSemaphore(2)


def render_search(url, pharmacy):
    from backend.services.price import checked_url, PHARMACIES
    checked_url(url, pharmacy)
    if os.environ.get('MEDIBOT_BROWSER_PRICES', '1') == '0':
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    if not _slots.acquire(timeout=1):
        return None
    try:
        with sync_playwright() as driver:
            channel = os.environ.get('MEDIBOT_BROWSER_CHANNEL', 'msedge')
            browser = driver.chromium.launch(headless=True, **({'channel': channel} if channel else {}))
            try:
                page = browser.new_page()
                def route_request(route):
                    request = route.request
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        try:
                            checked_url(request.url, pharmacy)
                        except ValueError:
                            return route.abort()
                    if request.resource_type in {'image', 'media', 'font'}:
                        return route.abort()
                    return route.continue_()
                page.route('**/*', route_request)
                response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
                if response is None or response.status >= 400:
                    return None
                try:
                    source = PHARMACIES[pharmacy]
                    paths = source.get('product_paths', [source['product_path']])
                    selector = ','.join(f'a[href*="{path}"], [data-redirect-url*="{path}"]' for path in paths)
                    page.wait_for_selector(selector, timeout=8000)
                except Exception:
                    pass
                html = page.content()
                # Serialize updated public page state, without executing any scraped code.
                state = page.evaluate('() => window.__INITIAL_STATE__ || null')
                if state:
                    html = '<script>window.__INITIAL_STATE__ = ' + json.dumps(state).replace('</', '<\\/') + ';</script>' + html
                return html
            finally:
                browser.close()
    except Exception:
        # Missing browser, timeout or access restrictions leave the pharmacy link usable.
        return None
    finally:
        _slots.release()
