# vercel-waf-bypass

A threaded HTTP fuzzer aimed at targets protected by Vercel. It walks a wordlist
and, whenever it hits the Vercel firewall challenge (a 403 with
`x-vercel-mitigated: challenge`), it climbs an evasion ladder: rotate the
user-agent, solve the challenge with a stealth browser (Camoufox), and switch
proxy — each worker uses its own validated proxy.

## Requires Polishing

This project still needs polishing. For now I'd recommend running it at a really
low rate (that's why the default is a single thread) — this mostly just keeps the
fuzzing going without stopping while you're asleep, rather than being a fast,
production-ready tool.

## ⚠️ Disclaimer

This tool is intended **for educational purposes and authorized security testing
only**. Use it exclusively against systems you own or have explicit written
permission to test. Using it against third-party systems without authorization is
illegal and is entirely your own responsibility. The authors are not liable for
any misuse.

## Dependencies

- Python 3.9+
- [`requests`](https://pypi.org/project/requests/) — HTTP requests from the workers
- [`httpx`](https://pypi.org/project/httpx/) — proxy validation
- [`swiftshadow`](https://pypi.org/project/swiftshadow/) — public proxy collection
- [`camoufox[geoip]`](https://pypi.org/project/camoufox/) — stealth browser (optional, used only to solve the challenge)

Install:

```bash
pip install requests httpx swiftshadow "camoufox[geoip]"
python -m camoufox fetch   # download the browser once (only if you use the browser step)
```

If Camoufox is not installed, the script still works — it just skips the
browser-based challenge-solving step.

## Input files

- **Wordlist** (`-w`): one path per line. Blank lines and lines starting with `#`
  are ignored; entries containing `.php` are skipped automatically.
- **User-agents** (`-a`): shipped with the repo as [`user_agent.txt`](user_agent.txt),
  with ~1000 real user-agents. One per line; each request picks a random one.

## Usage

```bash
python main.py -u <host> -w <wordlist> -a <user_agents> [-t N] [-d MIN MAX] [-v]
```

Arguments:

| Flag | Description | Default |
|------|-------------|---------|
| `-u`, `--url` | Target host (e.g. `example.com`) | required |
| `-w`, `--wordlist` | Path to the wordlist | required |
| `-a`, `--user-agents` | Path to the user-agent list | required |
| `-t`, `--threads` | Number of workers (used for both proxy validation and the target) | `1` |
| `-d`, `--delay` | Seconds between requests: one value (fixed) or two (random range) | `0.3 1.0` |
| `-v`, `--verbose` | Show every request and internal step (disables the progress bar) | off |

## Examples

Basic usage:

```bash
python main.py -u example.com -w wordlist.txt -a user_agent.txt
```

With 20 workers and a random delay between 0.5 and 2 seconds:

```bash
python main.py -u example.com -w wordlist.txt -a user_agent.txt -t 20 -d 0.5 2
```

Fixed 1-second delay, verbose mode:

```bash
python main.py -u example.com -w wordlist.txt -a user_agent.txt -d 1 -v
```

Saving the summary to a file (the progress bar stays on the terminal, the summary
goes to stdout):

```bash
python main.py -u example.com -w wordlist.txt -a user_agent.txt > result.txt
```
