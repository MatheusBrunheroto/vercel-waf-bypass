import sys
import threading
import time

BANNER = r"""
 _____ _____ ____ _____
|_   _| ____/ ___|_   _|
  | | |  _| \___ \ | |
  | | | |___ ___) || |
  |_| |_____|____/ |_|
        vercel waf fuzzer
"""


class Reporter:
    BAR_WIDTH = 28
    REDRAW_EVERY = 0.1

    def __init__(self, total, use_bar=True, out=None, err=None):
        self.total = max(total, 0)
        self.done = 0
        self.proxy_switches = 0
        self.challenges = 0
        self.blocked = 0
        self.results = []

        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.use_bar = bool(use_bar) and self.err.isatty()
        self._lock = threading.Lock()
        self._last_draw = 0.0

    def banner(self):
        self.err.write(BANNER + "\n")
        self.err.flush()

    def header(self, text):
        self.err.write(text + "\n")
        self.err.flush()

    def _bar_text(self):
        total = self.total or 1
        frac = min(self.done / total, 1.0)
        w = self.BAR_WIDTH
        filled = int(w * frac)
        if filled >= w:
            bar = "#" * w
        else:
            bar = "#" * filled + ">" + "-" * (w - filled - 1)
        pct = int(frac * 100)
        return (f"[{bar}] {pct:3d}% {self.done}/{self.total}"
                f"  px:{self.proxy_switches} ch:{self.challenges} "
                f"blk:{self.blocked}")

    def _draw(self, force=False):
        if not self.use_bar:
            return
        now = time.monotonic()
        if not force and (now - self._last_draw) < self.REDRAW_EVERY:
            return
        self._last_draw = now
        self.err.write("\r\033[2K" + self._bar_text())
        self.err.flush()

    def advance(self, n=1):
        with self._lock:
            self.done += n
            self._draw()

    def proxy_switch(self):
        with self._lock:
            self.proxy_switches += 1

    def challenge_ok(self):
        with self._lock:
            self.challenges += 1

    def blocked_hit(self):
        with self._lock:
            self.blocked += 1

    def result(self, status, word, note=""):
        with self._lock:
            self.results.append((status, word, note))
            line = f"{status:>3}  {word}" + (f"  [{note}]" if note else "")
            if self.use_bar:
                self.err.write("\r\033[2K" + line + "\n")
                self.err.flush()
                self._draw(force=True)
            else:
                self.out.write(line + "\n")
                self.out.flush()

    def finish(self):
        with self._lock:
            if self.use_bar:
                self._draw(force=True)
                self.err.write("\n")
                self.err.flush()
            self._summary()

    def _summary(self):
        w = self.out.write
        w("\n")
        w("── Summary " + "─" * 30 + "\n")
        w(f"  words tested   : {self.done}/{self.total}\n")
        w(f"  proxy switches : {self.proxy_switches}\n")
        w(f"  challenges ok  : {self.challenges}\n")
        w(f"  blocked (WAF)  : {self.blocked}\n")
        w(f"  results found  : {len(self.results)}\n")
        if self.results:
            w("\n")
            for status, word, note in sorted(self.results,
                                             key=lambda r: (r[0], r[1])):
                extra = f"  [{note}]" if note else ""
                w(f"  {status:>3}  {word}{extra}\n")
        self.out.flush()
