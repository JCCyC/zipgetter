# zipgetter

Download all `.zip` files (or other archive types) linked from a web page.

By default the page is fetched with `requests` and parsed with
`BeautifulSoup`. Pages that build their links via JavaScript can instead be
rendered with a headless, Selenium-driven browser.

## Requirements

- Python 3.10+
- The packages in `requirements.txt`
- For `-s` (Selenium mode) only: a Chromium, Brave, or Google Chrome binary
  on `PATH`

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Debian package

To build and install a `.deb` (on Debian, Ubuntu, or derivatives):

```bash
sudo apt install devscripts debhelper dh-python help2man python3-bs4 python3-requests lintian
scripts/build-deb
sudo apt install ./build/deb/zipgetter_*_all.deb
```

This installs `zipgetter` into `/usr/bin` along with a man page. Selenium
mode (`-s`) additionally needs `python3-selenium`, a Chrome-family browser,
and a matching chromedriver.

## Usage

```bash
./zipgetter <url> [options]
```

Matching archive files are downloaded into the current directory (or the
directory given with `-O`). When
stdout is an interactive terminal, an overall progress bar (files done out
of files found) is shown on the bottom line; it is omitted when output is piped or redirected.

### Options

| Flag | Description |
| --- | --- |
| `--version` | Print the version number and exit. |
| `-s` | Use Selenium (headless Chromium/Brave/Chrome) instead of a plain HTTP request. |
| `-c PATH` | Path to a Chrome/Chromium/Brave executable to use with `-s`, if not found on `PATH`. Only valid together with `-s`. |
| `-O DIRECTORY` | Download files into `DIRECTORY` instead of the current directory. It must already exist. |
| `-os FILE` | Save the fetched page's HTML source to `FILE`. |
| `-oh FILE` | Save the request/response HTTP headers to `FILE`. Not available with `-s`. |
| `-e [EXT1,EXT2,...]` | Also match other archive extensions. With no list given, matches common archive extensions (zip, rar, 7z, tar, tar.gz, tgz, tar.bz2, tar.xz, gz, bz2, xz). Default (no `-e`): `.zip` only. |

### Examples

```bash
# Download all .zip files linked from a page
./zipgetter https://example.com/downloads

# Same, but render the page with headless Chrome first (for JS-built link lists)
./zipgetter -s https://example.com/downloads

# Match zip, rar, and tar.gz files
./zipgetter -e zip,rar,tar.gz https://example.com/downloads

# Match all common archive extensions
./zipgetter -e https://example.com/downloads

# Download into an existing directory
./zipgetter -O ~/Downloads/archives https://example.com/downloads

# Also save the fetched HTML and headers for debugging
./zipgetter -os page.html -oh headers.txt https://example.com/downloads
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, all matching files downloaded. |
| `1` | The page could not be fetched (network error or HTTP 4xx/5xx). |
| `2` | Command-line usage error. |
| `3` | The page was fetched, but one or more files failed to download. |
| `4` | No usable Chrome-family browser found for `-s` (not on `PATH`, or the `-c` path is not an executable file). |
| `254` | Any other unexpected error (e.g. failure writing the `-os`/`-oh` output files). |

## License

Copyright (C) 2026 Juan Carlos Castro y Castro

zipgetter is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE) for the full text.
