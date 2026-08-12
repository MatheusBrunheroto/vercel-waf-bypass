import logging
import random
import threading
import time

import requests

from vercel import is_challenge, challenge_headers

log = logging.getLogger("fuzzer")

UA_AT = 3
BROWSER_AT = 6
PROXY_AT = 9
GIVE_UP_AT = 10

MAX_CONN_ERRORS = 5


class Worker(threading.Thread):
    def __init__(self, worker_id, words, target, user_agents,
                 proxies, browser, reporter, delay):
        super().__init__(daemon=True)
        self.wid = worker_id
        self.words = words
        self.target = target
        self.user_agents = user_agents
        self.proxies = proxies
        self.browser = browser
        self.reporter = reporter
        self.delay = delay
        self.cookies = {}

    def _pick_ua(self):
        return random.choice(self.user_agents)

    def _record(self, word, status, note=""):
        self.reporter.result(status, word, note)

    def _send(self, word, ua, extra_headers):
        proxy = self.proxies.get(self.wid)
        proxies = {"http": proxy, "https": proxy} if proxy else None
        headers = {"User-Agent": ua}
        headers.update(extra_headers)
        url = f"https://{self.target}/{word}"
        log.debug("[w%s] GET %s via %s", self.wid, word, proxy)
        try:
            return requests.get(
                url,
                headers=headers,
                cookies=self.cookies or None,
                proxies=proxies,
                timeout=10,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            log.debug("[w%s] conn error on %s: %s",
                      self.wid, word, type(exc).__name__)
            return None

    def _rotate_proxy(self):
        self.proxies.rotate(self.wid)
        self.cookies = {}
        self.reporter.proxy_switch()

    def _handle_word(self, word):
        challenges = 0
        conn_errors = 0
        ua = self._pick_ua()
        extra_headers = {}
        url = f"https://{self.target}/{word}"

        while True:
            response = self._send(word, ua, extra_headers)

            if response is None:
                conn_errors += 1
                if conn_errors >= MAX_CONN_ERRORS:
                    log.debug("[w%s] %s unreachable, moving on", self.wid, word)
                    return
                self._rotate_proxy()
                continue
            conn_errors = 0

            if response.status_code != 403:
                if response.status_code != 404:
                    self._record(word, response.status_code)
                return

            if not is_challenge(response):
                self._record(word, 403, note="forbidden (not firewall)")
                return

            challenges += 1
            extra_headers = challenge_headers(response)

            if challenges == UA_AT:
                ua = self._pick_ua()
                log.debug("Changing user agent...")
            elif challenges == BROWSER_AT:
                log.debug("Opening browser...")
                got = self.browser.solve(
                    url,
                    {"User-Agent": ua, **extra_headers},
                    proxy=self.proxies.get(self.wid),
                )
                if got:
                    self.cookies.update(got)
                    self.reporter.challenge_ok()
            elif challenges == PROXY_AT:
                log.debug("Changing proxies...")
                self._rotate_proxy()
            elif challenges >= GIVE_UP_AT:
                self.reporter.blocked_hit()
                return

            time.sleep(random.uniform(*self.delay))

    def _warm_up(self):
        ua = self._pick_ua()
        response = self._send("", ua, {})
        if response is None:
            return
        if response.status_code == 403 and is_challenge(response):
            log.debug("[w%s] solving challenge up front...", self.wid)
            got = self.browser.solve(
                f"https://{self.target}/",
                {"User-Agent": ua, **challenge_headers(response)},
                proxy=self.proxies.get(self.wid),
            )
            if got:
                self.cookies.update(got)
                self.reporter.challenge_ok()

    def run(self):
        self._warm_up()
        for word in self.words:
            self._handle_word(word)
            self.reporter.advance()
            time.sleep(random.uniform(*self.delay))
