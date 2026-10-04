# Changelog

## main

## v0.5.1

  * Use ansible podman support to manage containers
  * 45s timeout for container
  * Pin GitHub Actions to commit hashes
  * Validate snapshot hash when reconstruct downloads a notification URL
  * Read and write sync config with tomlkit (fixes unescaped strings in generated config); validate generated config before replacing the existing one
  * Reject RRDP object URIs that resolve to a path outside the reconstruct output directory (publish and withdraw).
    The path injection issue for withdraws was reported in [#66](https://github.com/ties/rpki-rrdp-tools-py/issues/66) by @N0zoM1z0.
  * Limit HTTP response bodies to 2 GiB (decompressed), as MAX_CONTENTLEN in rpki-client
  * Stream snapshot and delta downloads to disk instead of buffering them in memory
  * Only follow same-origin redirects, and require snapshot/delta URIs on the notification's origin (as rpki-client)
  * Limit notification files to 16 MiB
  * `snapshot-rrdp` and `sync-rrdp`: download the snapshot/deltas of a repository with workers instead of `asyncio.gather`. The first failed file no longer fails the run for the repository.
  * Remove dependencies used by workbooks

## v0.5.0:
  * Recognisable user-agent, which is configurable for RRDP sync.
  * Add optional UTC year/month output sharding and daily file logging.
  * Add countable verbosity and explicit log-level configuration.
  * Fix named repository paths and validation of notification URLs.
  * Write generated configs atomically and preserve the configured user-agent.
  * Shard output directory (--shard=none/year-month/year-month-day)
  * Write logs to output directory

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
