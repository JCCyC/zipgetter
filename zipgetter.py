#!/usr/bin/env python3
"""Download all .zip files linked from a web page.

By default, fetches the page with requests and parses links with
BeautifulSoup. With -s, renders the page with Selenium instead (useful
for pages that build their links via JavaScript).

By default only .zip files are downloaded. Use -e to also (or instead)
match other archive extensions.
"""

import argparse
import os
import shutil
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Exit codes 1 and 2 line up with argparse's own default: it exits 2 on a
# usage error, so "syntax" is 2 here too, letting us rely on argparse's
# built-in behavior instead of overriding it.
EXIT_PAGE_INACCESSIBLE = 1
EXIT_SYNTAX_ERROR = 2
EXIT_DOWNLOAD_ERROR = 3
EXIT_OTHER_ERROR = 4

# Masquerade as Chrome on both the page fetch and file downloads, since some
# servers block or alter behavior for the default requests/urllib user agent.
# (Not used in Selenium mode, which already drives a real Chrome/Chromium/Brave.)
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Used when -e is given with no extensions list.
POPULAR_ARCHIVE_EXTENSIONS = ["zip", "rar", "7z", "tar", "tar.gz", "tgz", "tar.bz2", "tar.xz", "gz", "bz2", "xz"]


def find_chrome_binary() -> str:
    """Search the PATH for a Chromium, Brave, or Chrome binary.

    Returns:
        The path to the browser binary.

    Raises:
        FileNotFoundError: If none of Chromium, Brave, or Chrome is found on PATH.
    """
    for name in (
        "chromium",
        "chromium-browser",
        "brave-browser",
        "brave",
        "google-chrome",
        "google-chrome-stable",
    ):
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError(
        "Could not find Chromium, Brave, or Google Chrome on PATH. "
        "Install one of them or add it to PATH."
    )


def get_page_html_requests(url: str) -> tuple[str, dict[str, str], dict[str, str], int]:
    """Fetch a page's HTML using requests.

    Does not raise on HTTP error status codes (4xx/5xx): the caller gets the
    error response's body, headers, and status code so it can still be
    inspected/saved.

    Returns:
        A tuple of (HTML source, request headers, response headers, status code).
    """
    response = requests.get(url, timeout=30, headers={"User-Agent": CHROME_USER_AGENT})
    return response.text, dict(response.request.headers), dict(response.headers), response.status_code


def get_page_html_selenium(url: str) -> str:
    """Fetch a page's HTML using a headless Selenium-driven browser."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.binary_location = find_chrome_binary()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        return driver.page_source
    finally:
        driver.quit()


def find_archive_links(html: str, base_url: str, extensions: list[str]) -> tuple[int, set[str]]:
    """Extract absolute URLs of all archive links in the given HTML.

    Args:
        html: The page's HTML source.
        base_url: The URL the page was loaded from, used to resolve
            relative links.
        extensions: File extensions to match (without the leading dot),
            e.g. ["zip", "tar.gz"].

    Returns:
        A tuple of (total number of links on the page, set of unique
        absolute URLs pointing to matching archive files).
    """
    suffixes = tuple(f".{ext.lower().lstrip('.')}" for ext in extensions)
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=True)
    archive_urls = set()
    for link in links:
        href = link["href"]
        absolute_url = urljoin(base_url, href)
        if urlparse(absolute_url).path.lower().endswith(suffixes):
            archive_urls.add(absolute_url)
    return len(links), archive_urls


def download_file(url: str, dest_dir: str = ".") -> str:
    """Download a file to dest_dir, returning the local file path."""
    filename = os.path.basename(urlparse(url).path)
    dest_path = os.path.join(dest_dir, filename)
    response = requests.get(url, timeout=30, headers={"User-Agent": CHROME_USER_AGENT}, stream=True)
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download all .zip files linked from a web page."
    )
    parser.add_argument("url", help="An HTTP or HTTPS URL to browse.")
    parser.add_argument(
        "-s",
        action="store_true",
        help="Use Selenium (headless Chromium/Brave/Chrome) instead of a plain HTTP request.",
    )
    parser.add_argument(
        "-os",
        dest="html_out",
        metavar="FILE",
        help="Save the fetched page's HTML source to FILE (useful for human debug).",
    )
    parser.add_argument(
        "-oh",
        dest="headers_out",
        metavar="FILE",
        help="Save the request and response HTTP headers to FILE (useful for human debug). "
        "Not available with -s.",
    )
    parser.add_argument(
        "-e",
        dest="extensions",
        nargs="?",
        const=",".join(POPULAR_ARCHIVE_EXTENSIONS),
        default=None,
        metavar="EXT1,EXT2,...",
        help="Also match other archive extensions, e.g. -e zip,rar,tar.gz,tgz. "
        "With no list given, matches common archive extensions "
        f"({', '.join(POPULAR_ARCHIVE_EXTENSIONS)}). "
        "Default (no -e): .zip only.",
    )
    args = parser.parse_args()

    if args.extensions is None:
        extensions = ["zip"]
    else:
        extensions = [ext.strip() for ext in args.extensions.split(",") if ext.strip()]

    if args.headers_out and args.s:
        parser.error("-oh is not available together with -s (Selenium exposes no raw HTTP headers).")

    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https"):
        print(f"Error: URL must use http or https scheme, got: {args.url!r}", file=sys.stderr)
        return EXIT_SYNTAX_ERROR

    request_headers: dict[str, str] = {}
    response_headers: dict[str, str] = {}
    status_code = None
    try:
        if args.s:
            html = get_page_html_selenium(args.url)
        else:
            html, request_headers, response_headers, status_code = get_page_html_requests(args.url)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_OTHER_ERROR
    except requests.RequestException as exc:
        # A connection-level failure (DNS, refused connection, timeout, ...):
        # no HTTP response was ever received, so there's nothing to save.
        print(f"Error fetching page: {exc}", file=sys.stderr)
        return EXIT_PAGE_INACCESSIBLE
    except Exception as exc:
        print(f"Error fetching page: {exc}", file=sys.stderr)
        return EXIT_PAGE_INACCESSIBLE

    if args.html_out:
        try:
            with open(args.html_out, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved page HTML to {args.html_out}")
        except OSError as exc:
            print(f"Error saving HTML to {args.html_out}: {exc}", file=sys.stderr)
            return EXIT_OTHER_ERROR

    if args.headers_out:
        try:
            with open(args.headers_out, "w", encoding="utf-8") as f:
                f.write("Request headers\n\n")
                for name, value in request_headers.items():
                    f.write(f"{name}: {value}\n")
                f.write("\nResponse headers\n\n")
                for name, value in response_headers.items():
                    f.write(f"{name}: {value}\n")
            print(f"Saved request/response headers to {args.headers_out}")
        except OSError as exc:
            print(f"Error saving headers to {args.headers_out}: {exc}", file=sys.stderr)
            return EXIT_OTHER_ERROR

    if status_code is not None and status_code >= 400:
        print(f"Error fetching page: HTTP {status_code}", file=sys.stderr)
        return EXIT_PAGE_INACCESSIBLE

    total_links, archive_urls = find_archive_links(html, args.url, extensions)

    downloaded = 0
    errors = []
    for archive_url in archive_urls:
        print(f"Downloading {archive_url} ...")
        try:
            dest_path = download_file(archive_url)
            print(f"  -> {dest_path}")
            downloaded += 1
        except OSError as exc:
            print(f"  Error downloading {archive_url}: {exc}", file=sys.stderr)
            errors.append(f"{archive_url}: {exc}")

    print()
    print("Stats:")
    print(f"  Total links on page: {total_links}")
    print(f"  Total downloadable ({', '.join(extensions)}) links: {len(archive_urls)}")
    print(f"  Total files downloaded: {downloaded}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for error in errors:
            print(f"    - {error}")
        return EXIT_DOWNLOAD_ERROR
    print("  Errors: none")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Error: unexpected failure: {exc}", file=sys.stderr)
        sys.exit(EXIT_OTHER_ERROR)
