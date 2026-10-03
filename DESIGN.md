# Design

## Full capture, not a relying party

These tools archive RRDP repositories as published. Unlike a relying party
(e.g. rpki-client), sync keeps the complete notification file and fetches every
delta it lists; `limit_deltas` per repository is the only cap.

We do follow rpki-client where it protects the host: HTTP responses are limited
to 2 GiB (`MAX_CONTENTLEN`), redirects must stay in the origin of the request,
and snapshot/delta URIs must be in the origin of the notification. We
deliberately do *not* apply its `MAX_RRDP_DELTAS` window of 300 deltas.
Notification files are limited to 16 MiB, because they are parsed in memory
(rpki-client parses them as a stream).
