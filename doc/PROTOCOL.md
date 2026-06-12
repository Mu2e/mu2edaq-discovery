# mu2edaq-discovery protocol specification

Version: `mu2edaq-discovery/1`

## Overview

A lightweight UDP multicast query/response protocol that lets Mu2e DAQ
applications announce themselves and lets operators discover which
applications are running, on which node, and on which port.

| Parameter | Value |
|---|---|
| Multicast group | `239.255.42.99` (administratively scoped) |
| UDP port | `28999` |
| Encoding | single UTF-8 JSON datagram |
| Max datagram size | 1400 bytes (fits one MTU) |
| Protocol identifier | `"proto": "mu2edaq-discovery/1"` in every message |

The port was chosen to avoid every port already in use in the suite
(9999 heartbeatmonitor, 37020 bigredbox, 5555/5556 dashboard-ZMQ and
trigger-scalers, 9876 controlcenter, 7755 dataformat-viewer, and the
5000–8088 HTTP range).

## Messages

### DISCOVER (query)

Sent by a client to the multicast group:

```json
{
  "proto": "mu2edaq-discovery/1",
  "type": "DISCOVER",
  "qid": "9f1c2e34-5d6a-4b7c-8e9f-0a1b2c3d4e5f",
  "filter": {"app": "vnc"}
}
```

- `qid` — a UUID4 generated per query. Responders echo it so clients
  can discard stale replies.
- `filter` — optional. Keys may be `app`, `name`, `host`; values are
  `fnmatch`-style globs matched against the corresponding ANNOUNCE
  fields. A missing filter matches everything. Responders that do not
  match MUST NOT reply.

### ANNOUNCE (response / unsolicited)

Sent by a responder **unicast back to the query's source address and
port**, after a random 0–250 ms jitter (avoids reply storms):

```json
{
  "proto": "mu2edaq-discovery/1",
  "type": "ANNOUNCE",
  "qid": "9f1c2e34-5d6a-4b7c-8e9f-0a1b2c3d4e5f",
  "id": "c0ffee12-3456-4789-abcd-ef0123456789",
  "name": "VNC mu2e-dl-01 :1 (daq-main)",
  "app": "vnc",
  "host": "mu2e-dl-01.fnal.gov",
  "port": 5901,
  "scheme": "vnc",
  "version": "1.0",
  "pid": 12345,
  "started": "2026-06-12T15:04:05Z",
  "meta": {"display": ":1", "geometry": "2560x1440", "account": "mu2edaq"}
}
```

- `id` — a UUID4 generated **once per process**. Clients deduplicate
  replies by `id` (queries are retransmitted).
- `meta` — free-form string map for application-specific detail.

### Periodic announce (optional)

A responder MAY also multicast the same ANNOUNCE message (without
`qid`) to the group at a configured interval. This supports passive
listeners and provides a migration path for `mu2edaq-heartbeatmonitor`:
its `SystemRegistry` can add a second listener on 28999 and ingest
ANNOUNCE messages alongside its port-9999 heartbeats.

## Client behavior

1. Open a UDP socket bound to an ephemeral port.
2. Send DISCOVER to `239.255.42.99:28999`; retransmit `retries` times
   spread across the timeout window (default: 2 sends over 2 s).
3. Collect ANNOUNCE datagrams until the timeout; ignore messages whose
   `qid` is present but does not match; deduplicate by `id`.

Multicast does not traverse the FNAL gateway. Off-site clients run the
query on a cluster node over ssh (`mu2edaq-discover --json`) and parse
the output.

## C++ port (future work)

The protocol is deliberately stdlib-only JSON over plain sockets so a
C++ implementation (Qt `QUdpSocket` or BSD sockets + a JSON library)
is mechanical. Until it exists, C++ applications (e.g.
mu2edaq-trigger-scalers) can run the Python `mu2edaq-discover`
sidecar / a `Responder` wrapper process from their start scripts.
