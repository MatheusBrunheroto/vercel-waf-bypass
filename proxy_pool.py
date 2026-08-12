import functools
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import swiftshadow.providers as _providers
from swiftshadow.classes import ProxyInterface

logger = logging.getLogger(__name__)

TEST_URL = "https://ifconfig.me/ip"


def _isolate_providers():
    registry = getattr(_providers, "Providers", None) or getattr(
        _providers, "ProvidersMap", None
    )
    if registry is None:
        logger.warning("Could not find the swiftshadow provider registry.")
        return

    for provider in registry.values():
        original = provider.providerFunction
        if getattr(original, "_isolated", False):
            continue

        @functools.wraps(original)
        async def guarded(*args, _fn=original, **kwargs):
            try:
                return await _fn(*args, **kwargs)
            except Exception as exc:
                logger.warning("Provider %s failed: %r", _fn.__name__, exc)
                return []

        guarded._isolated = True
        provider.providerFunction = guarded


_isolate_providers()


class ProxyPool:
    def __init__(
        self,
        max_proxies=50,
        protocol="http",
        test_url=TEST_URL,
        timeout=8.0,
        workers=20,
        max_rounds=25,
        overfetch=4,
    ):
        self.swift = ProxyInterface(
            protocol=protocol,
            maxProxies=max_proxies,
            autoRotate=True,
            autoUpdate=False,
        )
        self.protocol = protocol
        self.test_url = test_url
        self.timeout = timeout
        self.workers = workers
        self.max_rounds = max_rounds
        self.overfetch = overfetch

        self.seen = set()
        self.working = []
        self.raw_by_key = {}

        self._refresh()
        if not getattr(self.swift, "proxies", None):
            logger.warning(
                "No proxies loaded at startup; will retry during get_unique()."
            )

    def get_unique(self, amount):
        if amount <= 0:
            return []

        found = []
        rounds = 0

        while len(found) < amount and rounds < self.max_rounds:
            rounds += 1
            missing = amount - len(found)
            candidates = self._pull_candidates(missing * self.overfetch)

            if not candidates:
                logger.debug("No new candidates, refreshing source...")
                self._refresh()
                continue

            found.extend(self._validate_batch(candidates, limit=missing))
            logger.debug("Round %s: %s/%s working proxies", rounds, len(found), amount)

        if len(found) < amount:
            logger.warning(
                "Only got %s out of %s proxies after %s rounds.",
                len(found), amount, rounds,
            )
        return found

    def get_one(self):
        result = self.get_unique(1)
        return result[0] if result else None

    def drop(self, url):
        key = url.split("://")[-1]

        if url in self.working:
            self.working.remove(url)
        self.raw_by_key.pop(key, None)

        try:
            self.swift.proxies = [
                p for p in self.swift.proxies if f"{p.ip}:{p.port}" != key
            ]
        except Exception as exc:
            logger.debug("Could not remove it from swift: %r", exc)

    def reset_seen(self):
        self.seen = set(self.raw_by_key)

    def _key(self, raw):
        return f"{raw.ip}:{raw.port}"

    def _url(self, raw):
        protocol = getattr(raw, "protocol", self.protocol) or self.protocol
        return f"{protocol}://{raw.ip}:{raw.port}"

    def _refresh(self):
        try:
            self.swift.update()
        except ValueError as exc:
            logger.warning("swiftshadow found no proxies this round: %s", exc)
        except Exception as exc:
            logger.warning("swiftshadow refresh failed: %r", exc)

    def _pull_candidates(self, n):
        candidates = []
        misses = 0
        miss_limit = max(n * 3, 15)

        while len(candidates) < n and misses < miss_limit:
            try:
                raw = self.swift.get()
            except Exception as exc:
                logger.debug("swift.get() failed: %r", exc)
                raw = None

            if raw is None:
                misses += 1
                self._refresh()
                continue

            key = self._key(raw)
            if key in self.seen:
                misses += 1
                continue

            self.seen.add(key)
            candidates.append(raw)

        return candidates

    def _validate_batch(self, candidates, limit):
        approved = []
        executor = ThreadPoolExecutor(max_workers=self.workers)

        try:
            futures = {executor.submit(self._test, self._url(p)): p for p in candidates}
            for future in as_completed(futures):
                raw = futures[future]
                if future.result():
                    self._register(raw)
                    approved.append(self._url(raw))
                    if len(approved) >= limit:
                        break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return approved

    def _test(self, url):
        try:
            with httpx.Client(
                proxy=url,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                response = client.get(self.test_url)
        except Exception as exc:
            logger.debug("[FAILED] %s -> %r", url, exc)
            return False

        if response.status_code == 200:
            logger.debug("[OK] %s", url)
            return True

        logger.debug("[FAILED] %s -> status %s", url, response.status_code)
        return False

    def _register(self, raw):
        key = self._key(raw)
        if key in self.raw_by_key:
            return

        self.raw_by_key[key] = raw
        self.working.append(self._url(raw))

        try:
            already = {f"{p.ip}:{p.port}" for p in self.swift.proxies}
            if key not in already:
                self.swift.proxies.append(raw)
        except Exception as exc:
            logger.debug("Could not register it in swift: %r", exc)
