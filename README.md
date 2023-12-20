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
 34032 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 6ddb2089f38f6f97542761c0cde89130fcf1f6f3e6ccb5d96c6b47d0fafd6b52 27232 2023-12-20 07:25:06
 34037 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft eb85cdff4b62aa4b487a1487c439aa0af8838f363d53f3b796ca81276bfb6382 27233 2023-12-20 08:03:06
 34040 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft a537473cf2dc876b9c5088078d0a4645d9ed738850dc2a151219b03f01017a4e 27235 2023-12-20 08:28:06
 34043 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft ad6dc2eb68b6c0a6170bcb3fcb5bfde4df41e0cf691f809e7e5e116b5ca2353d 27236 2023-12-20 08:40:06
 34046 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 7001f22cb79ee0cfcaedfd02e73dfa6a9e04e92de32435d086beabfee382779f 27237 2023-12-20 08:55:06
 34051 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft d301c405db54754cc1e74e4ce7a9e8405c958bbb3cdbb8d64df34d959086be4e 27238 2023-12-20 09:12:06
 34056 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 6326ba5959f8d2423ad2a8d15696c2ba80c1b3c9bc4769311a318de33339b6ba 27239 2023-12-20 09:28:54
 34058 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft bc38e602052b78010b58fbd8a9c72e67ff000d96474e202a2980b6da35420560 27240 2023-12-20 09:57:46
 34061 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 72b17a28dc8bf88a872eb98e6d84e65f9e9c4b153ed459eb406a605e06e18636 27241 2023-12-20 10:02:46
 34064 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 4ce9ce0332aadd78f6cad25e4369ce688ae2b101998458927ad1f147f3c287c3 27242 2023-12-20 10:12:46
 34067 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 4fe353146d556559827b1369ed24263fe707c289859de27262ce413646d2f2de 27243 2023-12-20 10:27:46
 34072 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 5ec07f580e1aa50b83ceefa6842a95549ed52338625f755b0817fe66ccc9f839 27244 2023-12-20 10:42:46
 34077 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 6f2d6637196d1f4d3f06f2a847bb5b3f4eee3c7d4b1d6af9b7cef204a71ac0e4 27245 2023-12-20 10:57:46
 34082 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 26a40a7158430b5344df06ce2471250825395e7da556a9826d33c3ab96fd3f28 27246 2023-12-20 11:12:46
 34091 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 98128d916f539f314f428b20bd4bd2cdcb345a187bcb1ab514102230512724d4 27247 2023-12-20 11:57:46
 34095 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 8404b42ef4805ba044b395be49d995ec664d1a89d50fae1317eb242aa53ff68d 27248 2023-12-20 12:12:46
 34100 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 7a7e07efb4feb24d3dbab4e1fee39b44910bc3dc181578cd44735b077b65187e 27250 2023-12-20 12:34:58
 34103 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 5ad660e1e4783aa17ff77bc15b4208c915f3bb4f36d6b565f18d276214cbcf1b 27251 2023-12-20 12:47:58
 34110 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft aaa30a1f11284684a85828194c36df9aea4de4ef6b86fd8f22965fa7ef0fef01 27252 2023-12-20 13:17:58
 34116 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 102570b290473c9dd573c219d54fe73e6cc6abee3cdad65d02d1d46d323b9a7f 27253 2023-12-20 13:47:58
 34124 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 1f8f96ac4bc9f12ea61c5b51a51649207040de8b79ae969400dbe30dada575ce 27254 2023-12-20 14:16:58
 34125 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 33ce11d8121fb2622bf81f6f6f9ceff3d23de45c9a962f7ab957038076654a97 27255 2023-12-20 14:17:58
 34127 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft fcaa2559641f7307781f199b9d52b0be8624b8ad13e6251abb659fc8ef9833c5 27256 2023-12-20 14:25:58
 34135 rsync://rpki.ripe.net/repository/DEFAULT/KpSo3VVK5wEHIJnHC2QHVV3d5mk.mft 6118c625af160954ce8aa24b9cb55333c3536a1bc4a45fe14eb698f9742d64ef 27257 2023-12-20 15:03:06
```

# Changelog

## main:

  * Add RRDP content filtering/dumping sub-command

## v0.2.1:
  * Set timestamp of downloaded files from `last-modified` header.
  * Process withdraws when reconstructing
  * Validate hashes when reconstructing

## v0.2.0:

  * Add `--limit-deltas` to limit the number of deltas to keep
