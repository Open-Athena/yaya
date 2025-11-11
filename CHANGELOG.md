# Changelog

All notable changes to yaya will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-11-11

### Major Rewrite - Clean AST Architecture

This release represents a complete architectural rewrite, moving from byte-patching to full AST reserialization with formatting preservation. This enables true byte-for-byte lossless editing.

### Added
- **Blank line preservation within dicts** - Critical bug fix for GitHub Actions workflows, Kubernetes manifests, and other files using blank lines for visual organization
- **Quote style preservation** - Preserves single quotes, double quotes, and unquoted values
- **Flow vs block style control** - Auto-detect or explicitly control collection styles
- **List indentation detection** - Automatically detects and preserves aligned (offset=0) vs indented (offset=2) list styles
- **Jinja2 expression preservation** - Treats Jinja2 expressions as opaque strings
- **Order-preserving key insertion** - `insert_key_between()` for precise key ordering
- **Comprehensive test suite** - 95 tests (up from 21), including real-world transformation tests
- **Spec documentation** - Added `specs/` directory with detailed feature specifications

### Changed
- **Architecture**: Complete rewrite using clean, immutable AST nodes
  - New modules: `converter.py`, `emitter.py`, `nodes.py`, `extract.py`, `formatting.py`
  - Extract all formatting metadata during parsing
  - Re-serialize entire document while preserving formatting
- **API additions**:
  - `replace_in_values_regex()` - Regex-based replacements
  - `insert_key_between()` - Insert key between two existing keys
  - `ensure_key()` - Idempotent key addition
  - `set_list_indent_style()` - Control list indentation style
  - `assert_value()`, `assert_present()`, `assert_absent()` - Value assertions
- **Test improvements**: All tests now use exact expected outputs (no loose `in` assertions)

### Fixed
- **Blank lines within dicts** - Previously collapsed, now preserved byte-for-byte
- **Quote style changes** - Previously would change quotes in some cases
- **Block scalar indicators** - Now fully preserved (`|`, `|-`, `|+`)
- **List indentation** - Correctly detects and applies document style
- **Flow vs block style** - No longer forces one style over the other

### Technical Details
- Clean AST with immutable nodes (`Document`, `Mapping`, `Sequence`, `Scalar`, `Comment`, `BlankLines`)
- Formatting metadata extracted from original bytes (quotes, indentation, styles, blank lines)
- Full document reserialization with byte-for-byte preservation of unchanged sections
- Works with ruamel.yaml's CommentedMap/CommentedSeq but converts to clean representation

## [0.2.0] - 2025-11-07

### Added
- `get_version()` function and CLI to expose git commit hash
- Style hints for collection formatting (flow vs block)

### Fixed
- `set_list_indent_style()` now properly respected when creating new structures

## Previous Versions

See git history for changes before 0.2.0.

[0.3.0]: https://github.com/Open-Athena/yaya/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Open-Athena/yaya/releases/tag/v0.2.0
