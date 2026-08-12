import argparse
import logging
import sys

from fuzzer import Fuzzer


def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    for h in root.handlers:
        h.setLevel(level)
    root.setLevel(level)

    logging.getLogger("fuzzer").setLevel(logging.DEBUG if verbose else logging.ERROR)
    quiet = logging.DEBUG if verbose else logging.ERROR
    logging.getLogger("proxy_pool").setLevel(quiet)
    logging.getLogger("swiftshadow").setLevel(quiet)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Threaded Vercel fuzzer: 403 escalation + per-worker proxies.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-u", "--url", required=True, help="Target host, e.g. sitedacli.com")
    p.add_argument("-w", "--wordlist", required=True, help="Path to the wordlist file.")
    p.add_argument("-a", "--user-agents", required=True, help="Path to the UA file.")
    p.add_argument("-t", "--threads", type=int, default=1,
                   help="Workers for BOTH proxy validation and the target.")
    p.add_argument("-d", "--delay", type=float, nargs="+", default=[0.3, 1.0],
                   metavar=("MIN", "MAX"),
                   help="Seconds between requests: one value (fixed) or two "
                        "(random range, e.g. -d 0.5 2).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Show every request and internal step.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.verbose)

    if args.threads < 1:
        print("error: --threads must be >= 1", file=sys.stderr)
        sys.exit(1)

    if len(args.delay) == 1:
        delay = (args.delay[0], args.delay[0])
    elif len(args.delay) == 2:
        delay = (min(args.delay), max(args.delay))
    else:
        print("error: --delay takes one or two values", file=sys.stderr)
        sys.exit(1)
    if delay[0] < 0:
        print("error: --delay cannot be negative", file=sys.stderr)
        sys.exit(1)

    try:
        fuzzer = Fuzzer(
            target=args.url,
            wordlist_file=args.wordlist,
            user_agent_file=args.user_agents,
            threads=args.threads,
            delay=delay,
            show_progress=not args.verbose,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    fuzzer.run()


if __name__ == "__main__":
    main()
