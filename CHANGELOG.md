# Changelog

## v0.4.1:
  * BSD 3-clause license
  * dependency updates
  * remove old pinned transitive dependencies
  * container based on Debian trixie
  * Clean up dev dependencies, and use prek instead of pre-commit.

## v0.3.0:

  * Use UV for build
  * Serialise _to_ XML from RRDP datastructures
  * Parse manifest SIA
  * Explicitly include multidict 6.0.5 to install on Fedora 40
  * Add RRDP content filtering/dumping sub-command
  * Incorporate [erratum](https://www.rfc-editor.org/errata/eid7118) into rfc9286 asn1 (reported by @job).
  * Handle XML schema validation failures more gracefully
  * Print the difference in files between successive manifests (`--manifest-diff`)
  * Introduce a main cli entrypoint (`rrdp_tools.cli`)
  * re-use rrdp parser in `snapshot_rrdp.py`

## v0.2.1:
  * Set timestamp of downloaded files from `last-modified` header.
  * Process withdraws when reconstructing
  * Validate hashes when reconstructing

## v0.2.0:

  * Add `--limit-deltas` to limit the number of deltas to keep
