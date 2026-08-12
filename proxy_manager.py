import logging
import threading

log = logging.getLogger("fuzzer")


class ProxyManager:
    def __init__(self, pool, num_workers, spare=None):
        self.pool = pool
        self._lock = threading.Lock()
        self._assigned = {}
        want = num_workers + (num_workers if spare is None else spare)
        self._spares = pool.get_unique(want)
        log.debug("ProxyManager: prefetched %s proxies", len(self._spares))

    def _take_spare_locked(self):
        if not self._spares:
            need = max(len(self._assigned), 5)
            log.info("Fetching a new proxy list...")
            self._spares = self.pool.get_unique(need)
        return self._spares.pop() if self._spares else None

    def get(self, worker_id):
        with self._lock:
            if worker_id not in self._assigned:
                self._assigned[worker_id] = self._take_spare_locked()
            return self._assigned[worker_id]

    def rotate(self, worker_id, drop_old=True):
        with self._lock:
            old = self._assigned.get(worker_id)
            if drop_old and old:
                try:
                    self.pool.drop(old)
                except Exception:
                    pass
            self._assigned[worker_id] = self._take_spare_locked()
            return self._assigned[worker_id]
