# Create-wordlist-domain-v2-with-JS

A Python-based pipeline for passive domain reconnaissance, JS discovery, and payload generation.

## What it does

- collects archived URLs from the Wayback Machine
- gathers GitHub-hosted endpoint references for the target domain
- extracts domains, subdomains, and path candidates
- discovers JavaScript files and JS-derived URLs
- generates payload permutations similar to `sprawl`
- writes final outputs in a clean output directory

## New Python workflow

This repository now includes `make_wordlist.py` and no longer uses a bash wrapper. The full workflow is implemented in Python.

### Dependencies

- Python 3.8+
- `requests`

Install dependencies with:

```
pip install requests
```

### Usage

```
python make_wordlist.py target.com
```

Optional arguments:

- `--github-token TOKEN` — use a GitHub token for API searches
- `--output-dir DIR` — choose a different output folder
- `--max-wayback N` — maximum Wayback URLs to fetch
- `--max-github-pages N` — maximum GitHub search pages to scan
- `--max-workers N` — number of concurrent HTTP workers

### Example

```bash
python make_wordlist.py example.com --github-token ghp_xxxxxx
```

## Outputs

The script writes:

- `example.com-alljsfiles.txt` — discovered JavaScript file URLs
- `example.com-full-payloads.txt` — permuted path payloads generated from discovered paths
- `example.com-quick-payloads.txt` — top-level folder payloads for quick fuzzing
- `example.com-wayback-urls.txt` — archived URLs from Wayback
- `example.com-github-endpoints.txt` — extracted GitHub endpoint URLs
- `example.com-subdomains.txt` — discovered target subdomains
- `example.com-live-hosts.txt` — responsive host URLs

## Notes

- The script expects a plain domain like `example.com`, not `https://example.com`
- It uses Python logic instead of the original toolchain (`waybackurls`, `unfurl`, `httpx`, `getJS`, `sprawl`)
- GitHub search is best with a token to avoid API rate limits
