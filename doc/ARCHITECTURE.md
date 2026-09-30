---
title: mu2edaq-discovery
group: substrate
tier: A
audience: expert
summary: UDP multicast and broadcast service discovery for the Mu2e DAQ suite, providing the Python library and CLI, a C++ responder mirror, and the mu2edaq-discovery/1 wire protocol that sixteen sibling packages embed
---

# mu2edaq-discovery

> UDP multicast and broadcast service discovery for the Mu2e DAQ suite, providing the Python library and CLI, a C++ responder mirror, and the mu2edaq-discovery/1 wire protocol that sixteen sibling packages embed

| | |
|---|---|
| Repository | `Mu2e/mu2edaq-discovery` |
| Language | Python 3.9 (stdlib only), C++17 |
| Ports | 28999/udp (multicast group `239.255.42.99` and subnet broadcast) |
| Depends on | nothing at runtime; PyYAML and PyQt6/PySide6 are optional extras |

## Purpose

`mu2edaq-discovery` answers one question for the whole DAQ suite: *what is
running, on which node, on which port?* It is the substrate every other
Python package in `mu2edaq-main` sits on — sixteen of them construct a
`Responder` and run it in a daemon thread — and it is the only package whose
absence degrades every other one at once.

The design is intentionally the smallest thing that works. There is no
registry, no broker, no database, no persistent state and no authentication.
Each responder is authoritative only for itself; a scan is a snapshot of who
answered inside the timeout window; a dead service simply stops answering.
That property is what keeps it dependency-free, and dependency-free is what
lets it be imported by the AlmaLinux 9 system `python3` on a node with no
virtualenv.

## Architecture

```mermaid
sequenceDiagram
    autonumber
    participant CLI as mu2edaq-discover<br/>(client, ephemeral UDP port)
    participant NET as DAQ VLAN
    participant R1 as Responder A<br/>(daemon thread, 0.0.0.0:28999)
    participant R2 as Responder B<br/>(daemon thread, 0.0.0.0:28999)

    Note over CLI: build_query() -> qid = uuid4()
    CLI->>NET: DISCOVER to 239.255.42.99:28999 (multicast)
    CLI->>NET: DISCOVER to 255.255.255.255:28999 (broadcast)
    NET->>R1: both copies
    NET->>R2: broadcast only (IGMP snooping,<br/>R2 is on another switch)
    Note over R1,R2: decode() validates; matches_filter()<br/>then sleep(uniform(0, 250 ms))
    R1-->>CLI: ANNOUNCE unicast, qid echoed, id = A
    R1-->>CLI: ANNOUNCE unicast (2nd copy, same id)
    R2-->>CLI: ANNOUNCE unicast, qid echoed, id = B
    Note over CLI: drop qid mismatches; dedup by id;<br/>A counted once
    CLI->>NET: DISCOVER retransmission (retries=2)
    R1-->>CLI: ANNOUNCE (same id A, dropped as duplicate)
    Note over CLI: timeout expires -> sorted by (host, port)
```

The broadcast leg is the load-bearing detail. The Mu2e DAQ switches run IGMP
snooping with no querier, so each switch forwards the group only to ports it
has seen join and membership never propagates between switches. Measured in
September 2026, a multicast scan from `mu2e-mgr-01` found only itself; one
from `mu2e-trk-03` found only its own switch's tracker, calorimeter and CRV
nodes. Since 1.1.0 `discover()` sends the identical datagram to the group and
to the subnet broadcast and merges by `id`
(`src/mu2edaq_discovery/client.py:91-101`). Responders needed no change
because they bind `0.0.0.0` (`src/mu2edaq_discovery/responder.py:73`). The
real fix is a querier on the VLAN.

## Components

| Component | File | Role |
|---|---|---|
| Wire protocol | `src/mu2edaq_discovery/protocol.py` | Constants, `build_query`, `build_announce`, `encode`, `decode`, `matches_filter` |
| Responder | `src/mu2edaq_discovery/responder.py` | `threading.Thread` subclass embedded by consumers |
| Client | `src/mu2edaq_discovery/client.py` | `discover()` and `parse_broadcast_setting()` |
| CLI | `src/mu2edaq_discovery/cli.py` | `mu2edaq-discover`, table or JSON output |
| GUI | `src/mu2edaq_discovery/gui.py` | `mu2edaq-discover-gui`, Qt browser (PyQt6, PySide6 fallback) |
| C++ responder | `cpp/src/Responder.cpp`, `cpp/include/mu2edaq_discovery/*.hpp` | Responder-only mirror, no client |
| Protocol spec | `doc/PROTOCOL.md` | Normative description of `mu2edaq-discovery/1` |

Python is 891 lines across six modules; C++ is 649 lines of library, tests and
demo. Nothing in the runtime path imports anything outside the standard
library.

### Threading model

A `Responder` is a daemon thread (`responder.py:36`). Its loop has a 0.5 s
`recvfrom` timeout so it can observe the stop event
(`responder.py:80`, `:101`); `stop()` additionally pokes
`127.0.0.1:listen_port` with a zero-length datagram to break out of a blocking
receive immediately (`responder.py:56-58`). The C++ mirror uses the same
0.5 s `SO_RCVTIMEO` plus poke (`cpp/src/Responder.cpp:112-116`, `:126-134`).

Two sockets are used per responder: one bound listener that joins the group,
and one unbound sender with `IP_MULTICAST_TTL = 4` and `IP_MULTICAST_IF` set
(`responder.py:90-95`). Both are closed in a `finally`
(`responder.py:131-133`).

The GUI keeps `discover()` off the UI thread in a `QThread`
(`gui.py:134-159`) and marshals results back through Qt signals, per the
project's Qt threading rule. Consumers never call `discover()` from a
responder thread.

### Configuration resolution

Command line, then environment, then config file, then built-in default,
implemented in `cli.py:89-101` and mirrored in `gui.py:517-535`. The
`broadcast` setting is the one place the four sources could have drifted, so
it is funnelled through a single normaliser, `resolve_broadcast()`
(`cli.py:19-33`), which the GUI imports rather than re-implements
(`gui.py:31`).

## Interfaces

See [INTERFACES.md](INTERFACES.md). That file is the reference the other
forty-four package pages link to; the wire format, Python API, C++ API and
config schema are all specified there rather than repeated here.

## Configuration

`config/discovery.yaml` is an example, not an implicitly-loaded default:
nothing is read unless `--config` or `MU2EDAQ_DISCOVERY_CONFIG` names a path
(`cli.py:36-45`). Reading one requires PyYAML, which is otherwise not a
dependency; if it is missing the tool exits rather than falling back
(`cli.py:40-42`). See `discovery.yaml(5)`.

## Operations

There is no daemon and no systemd unit in this package. It ships two
user-invoked commands and a library. The operationally relevant facts are:

- **Not on PyPI.** Naming `mu2edaq-discovery` in a `requirements.txt` aborts
  the entire pip resolve for that file, not just that line. `mu2edaq-bigredbox`
  does exactly this (`mu2edaq-bigredbox/requirements.txt:10`). The supported
  path is `./mu2edaq-install-discovery.sh` at the superproject root, which
  prefers a prebuilt wheel from a wheelhouse and falls back to the sibling
  checkout, and is offline-safe.
- **`setup.cfg`, not PEP 621.** Metadata is in `setup.cfg` with a build floor
  of `setuptools>=40.8.0` (`pyproject.toml:8`), deliberately. AlmaLinux 9's
  system Python 3.9 creates venvs with setuptools 53; PEP 621 `[project]`
  support landed only in setuptools 61, so a `[project]` table builds as
  `UNKNOWN` there — no name, no version, no modules. The comment trail is at
  `setup.cfg:1-11` and `pyproject.toml:1-5`, and is restated in
  `mu2edaq-install-discovery.sh:30-36`. Do not move metadata back into
  `pyproject.toml`: setuptools >= 61 would then prefer the `[project]` table
  and the two would silently diverge.
- **System-wide importability.** `mu2edaq-controlroom-setup` launches
  `vnc-discovery-responder.py` under the bare system `python3`
  (`mu2edaq-controlroom-setup/server/start-vnc-session.sh:58`), not a venv, so
  on control-room nodes discovery must be importable system-wide. That script
  carries an embedded fallback responder for when it is not.

## Interactions with other packages

`mu2edaq-discovery` depends on no other package in the suite. The traffic is
entirely inbound. Sixteen Python packages construct a `Responder`
(`mu2edaq-dashboard`, `mu2edaq-fts`, `mu2edaq-diskwatcher`,
`mu2edaq-heartbeatmonitor`, `mu2edaq-reverse-proxy`, `mu2edaq-controlcenter`,
`mu2edaq-bigredbox`, `mu2edaq-runlog-db`, `mu2edaq-snapshot-viewer`,
`mu2edaq-dataformat-viewer`, `mu2edaq-downtime-logger`, `mu2edaq-file-reaper`,
`mu2edaq-phone-notification-system`, `mu2edaq-resource-manager`, and the
control-room VNC sidecar), and `mu2edaq-trigger-scalers` links the C++ library
via CMake `FetchContent` (`mu2edaq-trigger-scalers/CMakeLists.txt:85-90`,
`:120`). The manifest leaves `depended_on_by` empty per the review contract;
the aggregator computes it by inverting the other manifests.

`mu2edaq-config` carries a deployed `discovery.yaml` in each tagged
configuration tree.

## Review findings

Sixteen findings, staged in [ISSUES-PENDING.md](ISSUES-PENDING.md) because
issue creation was blocked mid-review after one issue
([#8](https://github.com/Mu2e/mu2edaq-discovery/issues/8)) had been opened.
The material ones:

- **S2** An ANNOUNCE that serializes past 1400 bytes raises inside the
  responder thread and kills it; the embedding application keeps running,
  silently undiscoverable (`responder.py:126`). Filed as #8.
- **S2** Python `start()` cannot report a socket failure — the socket is
  opened on the new thread — while the C++ `start()` throws to the caller.
  Two halves of one API with opposite failure contracts (`responder.py:89`
  against `cpp/src/Responder.cpp:80-120`).
- **S2** `started` is regenerated on every announcement instead of being
  fixed at construction, so a service's apparent start time tracks the
  current clock and uptime cannot be derived from a scan
  (`responder.py:83-86`). The C++ mirror gets this right.
- **S3** The C++ responder accepts DISCOVER messages the Python one rejects
  (non-object filter, non-string filter values, unknown filter keys,
  non-string `qid`) and does not size-check the ANNOUNCE it emits. Verified
  against a live responder on both sides.
- **S3** No CI of any kind: 60 passing pytest tests and a ctest suite, and
  nothing runs them.
- **S3** `setup.cfg:20` declares `license = BSD-3-Clause`; `LICENSE` is the
  MIT License.

## See also

- [INTERFACES.md](INTERFACES.md) — the reference other packages link to
- [PROTOCOL.md](PROTOCOL.md) — the normative wire specification
- `mu2edaq-discovery(7)`, `mu2edaq_discovery(3)`, `libmu2edaq_discovery(3)`,
  `discovery.yaml(5)`, `mu2edaq-discover(1)`, `mu2edaq-discover-gui(1)`
