#!/usr/bin/env python3
"""Create domain wordlists, JS file discovery, and payload permutations in Python."""

import argparse
import base64
import concurrent.futures
import html.parser
import itertools
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, List, Set, Tuple, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    print("ERROR: Python dependency 'requests' is required. Install with: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
USER_AGENT = "make_wordlist/1.0 (+https://github.com/Claude/Create-wordlist-domain-v2-with-JS)"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
GITHUB_SEARCH_URL = "https://api.github.com/search/code"

RE_URL = re.compile(r"https?://[\w\-\.\@:%_\+~#=\/\?&]+")
RE_JS_URL = re.compile(r"(?P<url>https?://[\w\-\.\@:%_\+~#=\/\?&]+\.js[\w\-\.\@:%_\+~#=\/\?&]*)")
RE_RELATIVE_JS = re.compile(r'''(?:["'])(?P<path>(?:\./|/)[^"']+\.js)(?:["'])''')
RE_PATH_CLEAN = re.compile(r"^/+")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico")

lock = threading.Lock()


def normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = urlparse(domain).hostname or domain
    domain = domain.strip("/")
    if not domain or " " in domain:
        raise ValueError("Invalid domain")
    return domain


def mkdirp(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.write_text("\n".join(sorted(dict.fromkeys(line.strip() for line in lines if line and line.strip()))) + "\n", encoding="utf-8")


def fetch_wayback_urls(domain: str, limit: int = 10000) -> List[str]:
    params = {
        "url": f"*.{domain}/*",
        "output": "text",
        "fl": "original",
        "collapse": "urlkey",
        "filter": "statuscode:200",
        "limit": str(limit),
    }
    response = requests.get(CDX_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    urls = []
    for line in response.text.splitlines():
        url = line.strip()
        if not url or "@" in url or "," in url or "*" in url:
            continue
        urls.append(url)
    return sorted(set(urls))


def github_search_code(domain: str, token: Optional[str], max_pages: int = 3) -> List[str]:
    urls: List[str] = []
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token.strip()}"

    query = f"{domain}+in:file"
    per_page = 30
    for page in range(1, max_pages + 1):
        params = {"q": query, "per_page": per_page, "page": page}
        response = requests.get(GITHUB_SEARCH_URL, params=params, headers=headers, timeout=30)
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit reached or token invalid")
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            raw_url = item.get("html_url")
            if raw_url:
                urls.append(raw_url)
        if len(items) < per_page:
            break
        time.sleep(1)
    return urls


def fetch_github_file_urls(github_html_urls: List[str], token: Optional[str]) -> List[str]:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token.strip()}"

    raw_urls: List[str] = []
    for html_url in github_html_urls:
        if "/blob/" not in html_url:
            continue
        raw_urls.append(html_url.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/"))
    return raw_urls


def fetch_github_endpoints(domain: str, token: Optional[str], max_pages: int = 3) -> List[str]:
    html_urls = github_search_code(domain, token, max_pages=max_pages)
    raw_urls = fetch_github_file_urls(html_urls, token)
    endpoints: Set[str] = set()
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token.strip()}"

    for raw_url in raw_urls:
        try:
            response = requests.get(raw_url, headers=headers, timeout=30)
            if response.status_code != 200:
                continue
            text = response.text
            endpoints.update(extract_urls_from_text(text, domain))
            endpoints.update(extract_relative_js_paths(text, raw_url, domain))
        except requests.RequestException:
            continue
    return sorted(endpoints)


def extract_urls_from_text(text: str, domain: str) -> Set[str]:
    matches = set()
    for match in RE_URL.finditer(text):
        url = match.group(0).rstrip('"\'')
        parsed = urlparse(url)
        if parsed.netloc and domain in parsed.netloc:
            matches.add(url)
    return matches


def extract_relative_js_paths(text: str, base_url: str, domain: str) -> Set[str]:
    js_urls: Set[str] = set()
    for match in RE_RELATIVE_JS.finditer(text):
        path = match.group("path")
        js_urls.add(urljoin(base_url, path))
    for match in RE_JS_URL.finditer(text):
        js_url = match.group("url")
        if domain in js_url:
            js_urls.add(js_url)
    return js_urls


def extract_domain(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.netloc:
        host = parsed.netloc.split(":")[0].lower()
        return host
    return None


def extract_path(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return RE_PATH_CLEAN.sub("", path.split("?")[0].split("#")[0])


def extract_domains(urls: Iterable[str], target_domain: str) -> Set[str]:
    hosts = set()
    for url in urls:
        host = extract_domain(url)
        if not host:
            continue
        if target_domain in host:
            hosts.add(host)
    return hosts


def is_valid_js_url(url: str, target_domain: str) -> bool:
    if not url.lower().endswith(".js"):
        return False
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return target_domain in parsed.netloc
    return False


def probe_url(url: str, timeout: int = 15) -> Optional[str]:
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if response.status_code < 400:
            return response.url
    except requests.RequestException:
        pass
    return None


def probe_hosts(hosts: Iterable[str], max_workers: int = 30) -> List[str]:
    urls = []
    candidates = []
    for host in hosts:
        for scheme in ("https", "http"):
            candidates.append(f"{scheme}://{host}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(probe_url, url): url for url in candidates}
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result()
            if result:
                urls.append(result)
    return sorted(set(urls))


def get_html_js_urls(page_html: str, base_url: str, target_domain: str) -> Set[str]:
    urls = set()

    class ScriptExtractor(html.parser.HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag.lower() != "script":
                return
            for name, value in attrs:
                if name.lower() == "src" and value:
                    urls.add(urljoin(base_url, value))

    parser = ScriptExtractor()
    parser.feed(page_html)
    for js_url in list(urls):
        if not js_url.lower().endswith(".js"):
            urls.discard(js_url)
            continue
        if target_domain not in urlparse(js_url).netloc:
            urls.discard(js_url)
    return urls


def fetch_url_text(url: str, timeout: int = 30) -> Optional[str]:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return response.text
    except requests.RequestException:
        return None
    return None


def collect_js_files(archive_urls: List[str], github_urls: List[str], target_domain: str, max_workers: int = 30) -> List[str]:
    js_urls: Set[str] = set()
    page_urls = [u for u in archive_urls if not u.lower().endswith(".js")]
    js_urls.update(u for u in archive_urls if is_valid_js_url(u, target_domain))
    js_urls.update(u for u in github_urls if is_valid_js_url(u, target_domain))

    page_urls = page_urls[:200]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_url_text, url): url for url in page_urls}
        for future in concurrent.futures.as_completed(futures):
            page_html = future.result()
            if not page_html:
                continue
            base_url = futures[future]
            urls = get_html_js_urls(page_html, base_url, target_domain)
            js_urls.update(urls)

    js_candidates = list(js_urls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_url_text, url): url for url in js_candidates}
        for future in concurrent.futures.as_completed(futures):
            text = future.result()
            if not text:
                continue
            js_url = futures[future]
            js_urls.update(extract_urls_from_text(text, target_domain))
            js_urls.update(extract_relative_js_paths(text, js_url, target_domain))

    return sorted(js_urls)


def normalize_path(path: str) -> Optional[str]:
    path = path.strip()
    if not path:
        return None
    path = path.split("?")[0].split("#")[0]
    path = RE_PATH_CLEAN.sub("", path)
    if not path or path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        return None
    if path.lower().endswith(IMAGE_EXTENSIONS):
        return None
    return path


def collect_paths(urls: Iterable[str], target_domain: str) -> Set[str]:
    paths: Set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        if not parsed.netloc or target_domain not in parsed.netloc:
            continue
        path = normalize_path(parsed.path)
        if path:
            paths.add(path)
    return paths


def generate_sprawl_payloads(paths: Set[str], max_permutations: int = 100000) -> Tuple[Set[str], Set[str]]:
    full_payloads: Set[str] = set()
    quick_payloads: Set[str] = set()
    for path in paths:
        tokens = [segment for segment in path.split("/") if segment]
        if not tokens:
            continue
        if tokens:
            quick_payloads.add(tokens[0])
        if len(tokens) == 1:
            full_payloads.add(tokens[0])
            continue
        if len(tokens) > 5:
            windows = [tokens[i : i + 4] for i in range(0, len(tokens), 4)]
            for subset in windows:
                for perm in itertools.permutations(subset):
                    full_payloads.add("/".join(perm))
        else:
            for perm in itertools.permutations(tokens):
                full_payloads.add("/".join(perm))
        if len(full_payloads) > max_permutations:
            break
    return full_payloads, quick_payloads


def resolve_github_token(cli_token: Optional[str]) -> Optional[str]:
    if cli_token:
        return cli_token.strip()

    tokens_file = SCRIPT_DIR / ".tokens"
    if tokens_file.exists():
        tokens = [l.strip() for l in tokens_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        if tokens:
            print(f"[*] GitHub token loaded from {tokens_file}")
            return tokens[0]

    print("\nNo GitHub token found. GitHub search is heavily rate-limited without one.")
    print("  1) Enter token now")
    print("  2) Load from .tokens file  (one token per line, place at script directory)")
    print("  0) Skip (proceed without token)")
    choice = input("Choice [0/1/2]: ").strip()

    if choice == "1":
        token = input("Enter GitHub token: ").strip()
        return token or None
    elif choice == "2":
        if not tokens_file.exists():
            print(f"  Create {tokens_file} with one token per line and re-run.")
            return None
        tokens = [l.strip() for l in tokens_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not tokens:
            print("  .tokens file is empty.")
            return None
        print(f"  Loaded token from {tokens_file}")
        return tokens[0]
    return None


def ensure_dependencies() -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        raise RuntimeError("Missing dependency 'requests'. Install with pip install requests")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate domain wordlists, JS files, and payloads in Python.")
    parser.add_argument("domain", help="Target domain, e.g. example.com")
    parser.add_argument("--github-token", help="GitHub token for API searches", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--output-dir", help="Output directory (defaults to <domain>)")
    parser.add_argument("--max-wayback", type=int, default=5000, help="Maximum wayback URLs to fetch")
    parser.add_argument("--max-github-pages", type=int, default=3, help="Maximum GitHub search pages to fetch")
    parser.add_argument("--max-workers", type=int, default=20, help="Number of concurrent HTTP workers")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        domain = normalize_domain(args.domain)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    github_token = resolve_github_token(args.github_token)

    output_dir = Path(args.output_dir or domain)
    mkdirp(output_dir)
    print(f"[*] Writing outputs to: {output_dir}")

    print(f"[*] Fetching Wayback URLs for {domain}...")
    wayback_urls = fetch_wayback_urls(domain, limit=args.max_wayback)
    print(f"    {len(wayback_urls)} wayback URLs found")

    print(f"[*] Fetching GitHub endpoints for {domain}...")
    try:
        github_urls = fetch_github_endpoints(domain, github_token, max_pages=args.max_github_pages)
    except RuntimeError as exc:
        print(f"WARNING: GitHub search failed: {exc}")
        github_urls = []
    print(f"    {len(github_urls)} GitHub endpoint URLs extracted")

    print(f"[*] Extracting subdomains...")
    subdomains = extract_domains(wayback_urls + github_urls, domain)
    print(f"    {len(subdomains)} unique subdomains found")
    if subdomains:
        live_urls = probe_hosts(subdomains, max_workers=args.max_workers)
        print(f"    {len(live_urls)} responsive host URLs discovered")
    else:
        live_urls = []

    print("[*] Collecting JS files...")
    js_urls = collect_js_files(wayback_urls, github_urls, domain, max_workers=args.max_workers)
    print(f"    {len(js_urls)} JS files discovered")

    print("[*] Collecting path candidates...")
    path_urls = set(wayback_urls)
    path_urls.update(github_urls)
    paths = collect_paths(path_urls, domain)
    print(f"    {len(paths)} unique path candidates")

    full_payloads, quick_payloads = generate_sprawl_payloads(paths)
    print(f"[*] Generated {len(full_payloads)} full payloads and {len(quick_payloads)} quick payloads")

    write_lines(output_dir / f"{domain}-alljsfiles.txt", js_urls)
    write_lines(output_dir / f"{domain}-full-payloads.txt", full_payloads)
    write_lines(output_dir / f"{domain}-quick-payloads.txt", quick_payloads)
    write_lines(output_dir / f"{domain}-wayback-urls.txt", wayback_urls)
    write_lines(output_dir / f"{domain}-github-endpoints.txt", github_urls)
    write_lines(output_dir / f"{domain}-subdomains.txt", sorted(subdomains))
    write_lines(output_dir / f"{domain}-live-hosts.txt", sorted(live_urls))

    print("[*] Done. Output files:")
    print(f"    {output_dir / f'{domain}-alljsfiles.txt'}")
    print(f"    {output_dir / f'{domain}-full-payloads.txt'}")
    print(f"    {output_dir / f'{domain}-quick-payloads.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
