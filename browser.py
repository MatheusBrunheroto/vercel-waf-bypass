import logging
import threading
import time

log = logging.getLogger("fuzzer")

COOKIE_HINTS = ("_vercel_jwt", "vcrcs", "vercel")


class BrowserSolver:
    def __init__(self, headless=False, solve_timeout=15, nav_timeout=15000,
                 geoip=True):
        self.headless = headless
        self.solve_timeout = solve_timeout
        self.nav_timeout = nav_timeout
        self.geoip = geoip
        self._lock = threading.Lock()

    def solve(self, url, headers, proxy=None):
        try:
            from camoufox.sync_api import Camoufox
        except ImportError:
            log.debug("camoufox not installed; skipping browser step")
            return None

        proxy_conf = {"server": proxy} if proxy else None

        with self._lock:
            try:
                with Camoufox(
                    headless=self.headless,
                    proxy=proxy_conf,
                    geoip=self.geoip if proxy else False,
                ) as browser:
                    context = browser.new_context(extra_http_headers=headers)
                    try:
                        page = context.new_page()
                        resp = None
                        try:
                            resp = page.goto(url, wait_until="domcontentloaded",
                                             timeout=self.nav_timeout)
                        except Exception as exc:
                            log.warning("browser navigation failed (%s): %s",
                                        type(exc).__name__, exc)

                        if self._is_challenge(resp):
                            cookies = self._wait_for_cookie(context, page)
                        else:
                            status = resp.status if resp else "?"
                            log.debug("no challenge on page (status %s); closing",
                                      status)
                            cookies = {c["name"]: c["value"]
                                       for c in context.cookies()}

                        log.debug("browser cookies: %s", list(cookies.keys()))
                        return cookies or None
                    finally:
                        context.close()
            except Exception as exc:
                log.warning("browser step failed (%s): %s",
                            type(exc).__name__, exc)
                return None

    def _is_challenge(self, resp):
        if resp is None:
            return False
        try:
            if resp.status != 403:
                return False
            return resp.headers.get("x-vercel-mitigated") == "challenge"
        except Exception:
            return False

    def _wait_for_cookie(self, context, page):
        deadline = time.monotonic() + self.solve_timeout
        while time.monotonic() < deadline:
            cookies = {c["name"]: c["value"] for c in context.cookies()}
            if any(hint in name.lower()
                   for name in cookies
                   for hint in COOKIE_HINTS):
                return cookies
            try:
                page.wait_for_timeout(500)
            except Exception:
                time.sleep(0.5)
        return {c["name"]: c["value"] for c in context.cookies()}
