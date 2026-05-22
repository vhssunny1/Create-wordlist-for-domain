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

- `--github-token TOKEN` — GitHub token for API searches
- `--output-dir DIR` — choose a different output folder
- `--max-wayback N` — maximum Wayback URLs to fetch
- `--max-github-pages N` — maximum GitHub search pages to scan
- `--max-workers N` — number of concurrent HTTP workers

### GitHub token

The token is resolved in this order:

1. `--github-token TOKEN` CLI flag
2. `GITHUB_TOKEN` environment variable
3. `.tokens` file in the script directory (one token per line, first line used)
4. Interactive prompt at startup — choose to enter a token or load from `.tokens`

### Example

```bash
python make_wordlist.py example.com
python make_wordlist.py example.com --github-token ghp_xxxxxx
```

## Outputs

Only two files are written to `<domain>/`:

- `example.com-full-payloads.txt` — all permuted path payloads, each prefixed with `/`
- `example.com-quick-payloads.txt` — top-level folder payloads for quick fuzzing, each prefixed with `/`

## Notes

- Pass a plain domain like `example.com`, not `https://example.com`
- Payloads are prefixed with `/` — e.g. `/wp/wp-json/v2/posts`
- GitHub search is heavily rate-limited without a token
- Uses Python instead of the original toolchain (`waybackurls`, `unfurl`, `httpx`, `getJS`, `sprawl`)
