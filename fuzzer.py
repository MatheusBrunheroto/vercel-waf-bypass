import logging

from browser import BrowserSolver
from proxy_manager import ProxyManager
from proxy_pool import ProxyPool
from reporter import Reporter
from utils import load_lines, split_evenly
from worker import Worker

log = logging.getLogger("fuzzer")


class Fuzzer:
    def __init__(self, target, wordlist_file, user_agent_file, threads,
                 delay=(0.3, 1.0), browser=None, show_progress=True):
        self.target = target.rstrip("/")
        self.wordlist = [w for w in load_lines(wordlist_file)
                         if ".php" not in w.lower()]
        self.user_agents = load_lines(user_agent_file)
        if not self.wordlist:
            raise ValueError("wordlist is empty")
        if not self.user_agents:
            raise ValueError("user-agent list is empty")

        self.threads = max(1, threads)
        self.delay = delay
        self.show_progress = show_progress
        self.browser = browser or BrowserSolver()

        self.reporter = Reporter(total=len(self.wordlist),
                                 use_bar=show_progress)
        self.reporter.banner()
        self.reporter.header(f"Validating proxies with {self.threads} workers...")

        pool = ProxyPool(max_proxies=max(200, self.threads * 20),
                         timeout=8.0, workers=self.threads)
        self.proxies = ProxyManager(pool, num_workers=self.threads)

    def run(self):
        chunks = split_evenly(self.wordlist, self.threads)
        self.reporter.header(
            f"Fuzzing {self.target} | {len(self.wordlist)} words "
            f"| {self.threads} workers"
        )

        workers = [
            Worker(
                worker_id=i,
                words=chunks[i],
                target=self.target,
                user_agents=self.user_agents,
                proxies=self.proxies,
                browser=self.browser,
                reporter=self.reporter,
                delay=self.delay,
            )
            for i in range(self.threads)
        ]

        for w in workers:
            w.start()
        for w in workers:
            w.join()

        self.reporter.finish()
