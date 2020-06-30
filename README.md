A collection of RRDP utilities
------------------------------

```
$ wget https://rrdp.ripe.net/56a98049-6402-4b58-ac6f-c3c395293498/576/snapshot.xml
...
$ mkdir repo_state
...
$ python rrdp_reconstruct snapshot.xml repo_state
$ ls repo_state
repository ta
$ ls repo_state/ta
ripe-ncc-ta.cer
```
