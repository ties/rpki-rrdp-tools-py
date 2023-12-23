# rpki-rrdp-tools-py

A number of RRDP utilities in Python.

## Download the full state of a RRDP repository:
```
poetry run python -m rrdp_tools.snapshot_rrdp \
    https://rrdp.arin.net/notification.xml \
    [output_dir] \
    # optional: include session in output path
    --include-session \
    # optional
    --skip_snapshot \
```

## Reconstruct the files present in a delta.xml or snapshot.xml:

```
poetry run python -m rrdp_tools.reconstruct \
  [path-to]/snapshot.xml \
  [output_dir] \
  # optional: If file only needs to be semantically validated
  --reconstruct-only \
  -v
```

## Scan a set of RRDP files and print matching files and their details

This supports both manifests and certificates
```
$ poetry run python -m rrdp_tools.rrdp_content_filter ~/Desktop/tmp  --file-match ".*KpSo3.*\.mft"
INFO:__main__:found 156 files
INFO:__main__:Skipping /Users/kockt/Desktop/tmp/notification.xml: not a snapshot or delta document
 33987 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft a596a776b24882a90696119f39498a6ee46c65429d5af697f01e3fd2fa686a9e 27228 2023-12-19 23:41:06
 34021 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft aae20f10e670c9e93f0992ff579b875deaadf09163c92281167654ed4e97515b 27229 2023-12-20 06:27:28
 34022 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft de29b8fb004513030924aa0505527947f17f688f2100b73a5a03e4d08d924b98 27230 2023-12-20 06:40:06
 34024 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft c85c731378ff7c38ea135ac8554108f8df1a38a881a4af0b2fefb9cb1caef2e0 27231 2023-12-20 06:47:06
...
```

This can also print what files were added/deleted between successive manifests:
```
$ poetry run python -m rrdp_tools.rrdp_content_filter ~/Desktop/tmp  --file-match ".*KpSo3.*\.mft" --manifest-diff
INFO:__main__:found 156 files
INFO:__main__:Skipping /Users/kockt/Desktop/tmp/notification.xml: not a snapshot or delta document
 33987 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft a596a776b24882a90696119f39498a6ee46c65429d5af697f01e3fd2fa686a9e 27228 2023-12-19 23:41:06
 34021 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft aae20f10e670c9e93f0992ff579b875deaadf09163c92281167654ed4e97515b 27229 2023-12-20 06:27:28
      + KpSo3VVK5wEHIJnHC2QHVV3d5mk.crl sha256=c220c093ff4bbcdfaff97202a7b8d547845aadd0f81e9bbc8e503c96cf54841e
      - KpSo3VVK5wEHIJnHC2QHVV3d5mk.crl sha256=c5af0fc44a5b91c59482045b3f56506adbee455cc58e740f8b09bc083e6d187e
      + wCLT1QbI_rSTaFSxOnu5f5scl4Y.cer sha256=0b18587742aa403116b6be72433bff02f9ee464e7f5abce5cde3cc9bd755fa6a
 34022 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft de29b8fb004513030924aa0505527947f17f688f2100b73a5a03e4d08d924b98 27230 2023-12-20 06:40:06
      - KpSo3VVK5wEHIJnHC2QHVV3d5mk.crl sha256=c220c093ff4bbcdfaff97202a7b8d547845aadd0f81e9bbc8e503c96cf54841e
      + KpSo3VVK5wEHIJnHC2QHVV3d5mk.crl sha256=d215f56d792becdb168cb681e38a96ac9f7208a0e377869795085f55955703ae
      + P3lU2IwK4_Y5hpe_38GVanU-g9g.cer sha256=1108e9ca3a85e06788a79260620fd32865964ea97f841c4776b011c72faee6fc
      - P3lU2IwK4_Y5hpe_38GVanU-g9g.cer sha256=b484c44560a8ce837819c7f9cf83da011d2e0098cc9462bb9809a1ac495c9623
...
```

# Changelog

## main:

  * Add RRDP content filtering/dumping sub-command
  * Incorporate [erratum](https://www.rfc-editor.org/errata/eid7118) into rfc9286 asn1 (reported by @job).
  * Handle XML schema validation failures more gracefully
  * Print the difference in files between successive manifests (`--manifest-diff`)
  * Introduce a main cli entrypoint (`rrdp_tools.cli`)

## v0.2.1:
  * Set timestamp of downloaded files from `last-modified` header.
  * Process withdraws when reconstructing
  * Validate hashes when reconstructing

## v0.2.0:

  * Add `--limit-deltas` to limit the number of deltas to keep
