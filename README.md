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
  -v
```

# Changelog

## v0.2.x:
  * Set timestamp of downloaded files from `last-modified` header.

## v0.2.0:

  * Add `--limit-deltas` to limit the number of deltas to keep
