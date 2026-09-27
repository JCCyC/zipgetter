# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- In Selenium mode (`-s`), a warning on stderr when the installed Selenium is older than 4.18 (such as the 4.0.0 alpha in Ubuntu 22.04's `python3-selenium`), which handles current browsers poorly.
- Exit code 5 when `-s` is given but Selenium is not installed (or is missing one of its own dependencies). This used to exit 1, as if the page were unreachable.
- `-e common` selects the common archive extensions, and `common` can be combined with other extensions, as in `-e common,iso`.

### Changed

- The minimum Selenium version in `requirements.txt` is lowered from 4.20 to 4.18, so Ubuntu 24.04's `python3-selenium` (4.18.1) qualifies.
- **Breaking:** `-e` now requires an extensions list. A bare `-e` used to select the common archive extensions, but when followed by the URL it took the URL as its list; use `-e common` instead.
- `--version` now prints copyright, license and author information, which also adds COPYRIGHT and AUTHOR sections to the man page.

### Fixed

- `-s` now works with distro Selenium packages such as Debian/Ubuntu's `python3-selenium`, which lack the Selenium Manager helper that normally locates chromedriver. When Selenium can't find a driver, zipgetter falls back to the `chromedriver` on `PATH`.

## [0.9.1] - 2026-09-27

### Added

- Debian packaging (`debian/`) and `scripts/build-deb`, to build a `.deb` or a source package for an Ubuntu PPA. The package includes a man page.

### Changed

- The script is now named `zipgetter` instead of `zipgetter.py`.

## [0.9.0] - 2026-09-27

First release.

### Added

- Download all `.zip` files linked from a web page, or other archive types with `-e`.
- `-s` to render the page with headless Chromium/Brave/Chrome via Selenium, for pages that build their links with JavaScript.
- `-c PATH` to point `-s` at a specific Chrome/Chromium/Brave executable.
- `-O DIRECTORY` to choose the download directory.
- `-os FILE` and `-oh FILE` to save the fetched HTML and HTTP headers for debugging.
- `--version` to print the version number.
- Overall progress bar when stdout is a terminal.
- File sizes in the "Downloading" messages and the total download size in the final stats, when the server provides them.
- Distinct exit codes for an unreachable page, usage errors, failed downloads and a missing Chrome binary.

[Unreleased]: https://github.com/JCCyC/zipgetter/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/JCCyC/zipgetter/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/JCCyC/zipgetter/releases/tag/v0.9.0
