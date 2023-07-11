# rpki-rrdp-tools-py

A number of RRDP utilities in Python.

## Download the full state of a RRDP repository:
```
poetry run python -m rrdp_tools.snapshot_rrdp \
    https://rrdp.arin.net/notification.xml \
    [output_dir] \
    --include-session
```

## Reconstruct the files present in a delta.xml or snapshot.xml:

```
poetry run python -m rrdp_tools.reconstruct \
  [path-to]/snapshot.xml \
  [output_dir] \
  -v
```