# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`zipgetter` is a single-file Python CLI script (no `.py` extension) that downloads archive files (`.zip` by default) linked from a web page. There is no Python package structure, test suite, or linter configured — the entire tool lives in this one file. The only build step is the Debian packaging in `debian/` (see below).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run
./zipgetter <url> [options]

# Build a local .deb (into build/deb/) from committed content at HEAD or a ref
scripts/build-deb [REF]

# Build a signed source package for a Launchpad PPA upload
scripts/build-deb -S [REF]
```

There are no automated tests or lint config. Verify changes by running the script against a real or local page and checking its stdout/exit code.

## Architecture

The script has two independent page-fetching backends, selected by the `-s` flag:

- `get_page_html_requests` — default path. Fetches with `requests`, returns HTML plus request/response headers and status code so they can be inspected or saved (`-oh`/`-os`) even on HTTP errors.
- `get_page_html_selenium` — used with `-s`. Drives a headless Chromium/Brave/Chrome via Selenium (found on `PATH` by `find_chrome_binary`) for pages that build links via JavaScript. Exposes no raw HTTP headers, so `-oh` is rejected in combination with `-s`. It warns on stderr (without failing) when `selenium.__version__` is older than `MIN_SELENIUM_VERSION`, which must match the `selenium>=` floor in `requirements.txt`.

Both backends feed into a common pipeline in `main()`:

1. Fetch HTML via one of the two backends above.
2. `find_archive_links` parses the HTML with BeautifulSoup, resolves `<a href>` values against the page URL with `urljoin`, and filters by extension suffix (`.zip` by default, or the set from `-e`).
3. `download_file` streams each matched URL to a file in the current directory, named from the URL's basename.
4. `main()` prints per-file download progress (plus an overall in-place `ProgressBar` across all files, only when `stdout_is_terminal()`) and a final stats summary (total links seen, matching links found, files downloaded, errors).

All HTTP requests (page fetch and downloads) send a spoofed Chrome `User-Agent` (`CHROME_USER_AGENT`) since some servers alter behavior for the default `requests`/`urllib` UA. This does not apply in Selenium mode, which already drives a real browser.

### Exit codes

Exit codes are deliberate and encoded as module-level constants (`EXIT_PAGE_INACCESSIBLE = 1`, `EXIT_SYNTAX_ERROR = 2`, `EXIT_DOWNLOAD_ERROR = 3`, `EXIT_CHROME_NOT_FOUND = 4`, `EXIT_OTHER_ERROR = 254`). Code 2 is reserved to line up with argparse's own default usage-error exit code rather than being explicitly returned. `EXIT_OTHER_ERROR` is kept at the high end of the range (254) specifically so new, more specific exit codes (like `EXIT_CHROME_NOT_FOUND`) can keep claiming small numbers without colliding with it. Preserve this scheme when modifying error handling — callers of the script may depend on distinguishing "page unreachable" from "some downloads failed" from "bad arguments" from "no usable Chrome binary."

## Changelog

User-visible changes go under `## [Unreleased]` in `CHANGELOG.md` (Keep a Changelog format, newest release first). When releasing, rename that section to the new version and date, bump `__version__` in `zipgetter`, and add the version's compare link at the bottom.

## Debian packaging

`debian/` is standard debhelper (compat 13) packaging for an `Architecture: all` package targeting Ubuntu jammy (22.04, the oldest series with Python 3.10) as the first PPA series; other series are filled with Launchpad's "Copy packages" rather than separate uploads. `debian/rules` generates the man page from `--help` with help2man, plus `debian/zipgetter.h2m` for the exit-status section, so keep that file in sync with the exit codes. `dh_python3` rewrites the `#!/usr/bin/env python3` shebang to `/usr/bin/python3` in the installed script.

`scripts/build-deb` builds from a git ref, not the working tree, using `dist/zipgetter-X.Y.Z.tar.gz` as the orig tarball when it exists so the PPA gets byte-for-byte the tarball from the GitHub release. The upstream version comes from `debian/changelog`, whose top entry must match `__version__` at release time. When a runtime dependency changes in `requirements.txt`, update `Depends`/`Suggests` (and `Build-Depends` if it's imported at startup) in `debian/control`.
