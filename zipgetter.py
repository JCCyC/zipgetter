#!/usr/bin/env python3
# zipgetter - download archive files linked from a web page
# Copyright (C) 2026 Juan Carlos Castro y Castro
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Exit codes 1 and 2 line up with argparse's own default: it exits 2 on a
# usage error, so "syntax" is 2 here too, letting us rely on argparse's
# built-in behavior instead of overriding it.
EXIT_PAGE_INACCESSIBLE = 1
EXIT_SYNTAX_ERROR = 2
EXIT_DOWNLOAD_ERROR = 3
EXIT_CHROME_NOT_FOUND = 4
EXIT_OTHER_ERROR = 254

# Masquerade as Chrome on both the page fetch and file downloads, since some
# servers block or alter behavior for the default requests/urllib user agent.
# (Not used in Selenium mode, which already drives a real Chrome/Chromium/Brave.)
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Used when -e is given with no extensions list.
POPULAR_ARCHIVE_EXTENSIONS = ["zip", "rar", "7z", "tar", "tar.gz", "tgz", "tar.bz2", "tar.xz", "gz", "bz2", "xz"]


def find_chrome_binary(override: str | None = None) -> str:
    """Search the PATH for a Chromium, Brave, or Chrome binary.

    Args:
        override: If given, use this path instead of searching PATH. Must
            point to an existing, executable file.

    Returns:
        The path to the browser binary.

    Raises:
        FileNotFoundError: If override is given but not an executable file,
            or if none of Chromium, Brave, or Chrome is found on PATH.
    """
    if override is not None:
        if not os.path.isfile(override) or not os.access(override, os.X_OK):
            raise FileNotFoundError(
                f"Chrome binary not found or not executable: {override!r}"
            )
        return override

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


def get_page_html_selenium(url: str, chrome_binary: str | None = None) -> str:
    """Fetch a page's HTML using a headless Selenium-driven browser.

    Args:
        url: The page URL to load.
        chrome_binary: Path to a Chrome/Chromium/Brave executable to use
            instead of searching PATH.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.binary_location = find_chrome_binary(chrome_binary)
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


def stdout_is_terminal() -> bool:
    """Return True if stdout is an interactive terminal able to redraw a line."""
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


def format_size(num_bytes: float) -> str:
    """Format a byte count with at most 3 significant digits, e.g. '12.3 MiB'."""
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        # Switch units before rounding would produce 4 digits (e.g. '1000 KiB').
        if num_bytes < 999.5 or unit == "TiB":
            break
        num_bytes /= 1024
    if unit == "B" or num_bytes >= 99.95:
        return f"{num_bytes:.0f} {unit}"
    if num_bytes >= 9.995:
        return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.2f} {unit}"


class ProgressBar:
    """An overall progress bar kept on the terminal's bottom line.

    Tracks progress across all files: each finished file (downloaded or
    failed) counts as one step, and the file currently downloading counts
    fractionally by bytes when its size is known. Log lines are printed
    above the bar via log(), which clears and redraws it.

    Only meant to be used when stdout_is_terminal() is True, since it redraws
    the line with carriage returns.
    """

    MIN_REDRAW_INTERVAL = 0.1  # seconds

    def __init__(self, total_files: int) -> None:
        self.total_files = total_files
        self.files_done = 0
        self._file_bytes = 0
        self._file_total: int | None = None
        self._drawn = False
        self._last_draw = 0.0

    def file_progress(self, done: int, total: int | None, force: bool = False) -> None:
        """Record byte progress of the current file (a download_file callback)."""
        self._file_bytes = done
        self._file_total = total
        self._draw(force)

    def file_finished(self) -> None:
        """Count the current file as done, whether it succeeded or failed."""
        self.files_done += 1
        self._file_bytes = 0
        self._file_total = None
        self._draw(force=True)

    def log(self, message: str, file=None) -> None:
        """Print a message above the bar, then redraw the bar."""
        self._clear()
        print(message, file=file or sys.stdout, flush=True)
        self._draw(force=True)

    def finish(self) -> None:
        """Remove the bar so subsequent output starts on a clean line."""
        self._clear()

    def _clear(self) -> None:
        if self._drawn:
            columns = shutil.get_terminal_size().columns
            sys.stdout.write("\r" + " " * (columns - 1) + "\r")
            sys.stdout.flush()
            self._drawn = False

    def _draw(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_draw < self.MIN_REDRAW_INTERVAL:
            return
        self._last_draw = now

        current = 0.0
        if self._file_total:
            current = min(self._file_bytes / self._file_total, 1.0)
        fraction = min((self.files_done + current) / max(self.total_files, 1), 1.0)

        columns = shutil.get_terminal_size().columns
        suffix = f" {fraction * 100:3.0f}% {self.files_done}/{self.total_files} files"
        if self._file_bytes and self.files_done < self.total_files:
            suffix += f" ({format_size(self._file_bytes)})"
        bar_width = max(columns - len(suffix) - 3, 10)
        filled = int(bar_width * fraction)
        line = f"[{'#' * filled}{'.' * (bar_width - filled)}]{suffix}"
        sys.stdout.write("\r" + line[: columns - 1].ljust(columns - 1))
        sys.stdout.flush()
        self._drawn = True


def download_file(
    url: str,
    dest_dir: str = ".",
    progress: Callable[..., None] | None = None,
    on_start: Callable[[int | None], None] | None = None,
) -> str:
    """Download a file to dest_dir, returning the local file path.

    If given, on_start is called as on_start(total_bytes) once the response
    headers arrive, before the body is downloaded. If given, progress is called as progress(bytes_done, total_bytes) after
    each chunk, and once more with force=True at the end; total_bytes is None
    when the size isn't known up front.
    """
    filename = os.path.basename(urlparse(url).path)
    dest_path = os.path.join(dest_dir, filename)
    response = requests.get(url, timeout=30, headers={"User-Agent": CHROME_USER_AGENT}, stream=True)
    response.raise_for_status()
    # With a Content-Encoding, Content-Length is the compressed size, while
    # iter_content yields decoded bytes, so the total wouldn't be comparable.
    total = None
    if "Content-Encoding" not in response.headers:
        try:
            total = int(response.headers["Content-Length"])
        except (KeyError, ValueError):
            pass
    if on_start:
        on_start(total)
    done = 0
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if progress:
        progress(done, total, force=True)
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
        "-c",
        dest="chrome_binary",
        metavar="PATH",
        help="Path to a Chrome/Chromium/Brave/etc. executable to use with -s, "
        "if not found on PATH.",
    )
    parser.add_argument(
        "-O",
        dest="output_dir",
        metavar="DIRECTORY",
        default=".",
        help="Download files into DIRECTORY, which must already exist. "
        "Default: the current directory.",
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

    if args.chrome_binary and not args.s:
        parser.error("-c is only used together with -s.")

    if not os.path.isdir(args.output_dir):
        parser.error(f"-O directory does not exist or is not a directory: {args.output_dir!r}")

    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https"):
        print(f"Error: URL must use http or https scheme, got: {args.url!r}", file=sys.stderr)
        return EXIT_SYNTAX_ERROR

    request_headers: dict[str, str] = {}
    response_headers: dict[str, str] = {}
    status_code = None
    try:
        if args.s:
            html = get_page_html_selenium(args.url, args.chrome_binary)
        else:
            html, request_headers, response_headers, status_code = get_page_html_requests(args.url)
    except FileNotFoundError as exc:
        # Only raised by find_chrome_binary (via get_page_html_selenium):
        # no usable Chrome/Chromium/Brave binary was found or given.
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CHROME_NOT_FOUND
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

    bar = ProgressBar(len(archive_urls)) if stdout_is_terminal() and archive_urls else None

    def log(message: str, file=None) -> None:
        if bar:
            bar.log(message, file=file)
        else:
            print(message, file=file)

    downloaded = 0
    total_size = 0
    all_sizes_known = True
    errors = []
    try:
        for archive_url in archive_urls:
            announced = False
            file_size = None

            def announce(total: int | None, archive_url: str = archive_url) -> None:
                nonlocal announced, file_size
                file_size = total
                size = f" ({format_size(total)})" if total is not None else ""
                log(f"Downloading {archive_url}{size} ...")
                announced = True

            try:
                dest_path = download_file(
                    archive_url,
                    args.output_dir,
                    progress=bar.file_progress if bar else None,
                    on_start=announce,
                )
            except OSError as exc:
                # Failed before the response headers arrived (e.g. connection
                # error or HTTP error status): announce without a size.
                if not announced:
                    announce(None)
                if bar:
                    bar.file_finished()
                log(f"  Error downloading {archive_url}: {exc}", file=sys.stderr)
                errors.append(f"{archive_url}: {exc}")
                continue
            if bar:
                bar.file_finished()
            log(f"  -> {os.path.basename(dest_path)}")
            downloaded += 1
            if file_size is None:
                all_sizes_known = False
            else:
                total_size += file_size
    finally:
        if bar:
            bar.finish()

    print()
    print("Stats:")
    print(f"  Total links on page: {total_links}")
    print(f"  Total downloadable ({', '.join(extensions)}) links: {len(archive_urls)}")
    print(f"  Total files downloaded: {downloaded}")
    if downloaded and all_sizes_known:
        print(f"  Total download size: {format_size(total_size)}")
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
