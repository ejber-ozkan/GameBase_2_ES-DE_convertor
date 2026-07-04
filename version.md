# Version Information

- **Current Version:** `v1.0.0`
- **Release Date:** 2026-07-04

## Version History

### `v1.0.0` (Initial Release)
- Native cross-platform database parser using pure-Python `access-parser` to query Access databases without OLEDB/ODBC driver dependencies.
- Full metadata resolving for `Games`, `Years`, `Genres`, `PGenres`, `Developers`, and `Publishers`.
- Resolves `Extras` (Type 0) to locate the first valid JPEG/PNG cover art per game.
- Generates fully portable, parent-relative paths (e.g., `../Screenshots/` and `../Extras/`) relative to the `Games/` directory.
- Maps all file paths to use forward slashes (`/`) for cross-platform emulator parsing (Windows, Linux, Android, macOS).
- Converts GameBase 0-5 ratings to ES-DE 0.0-1.0 ratings.
- Resolves GameBase special years (e.g., `9991` for the 1980s, `9992` for the 1990s) into valid standard release dates and omits unknown dates.
- Standardizes description generation by merging comments and full reviews.
- Provides `run_converter.bat` (Windows) and `run_converter.sh` (macOS/Linux) for fully automated local virtual environment and package installation.
