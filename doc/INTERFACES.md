---
title: mu2edaq-discovery interfaces
group: substrate
tier: A
audience: expert
summary: UDP multicast and broadcast service discovery for the Mu2e DAQ suite, providing the Python library and CLI, a C++ responder mirror, and the mu2edaq-discovery/1 wire protocol that sixteen sibling packages embed
---

# mu2edaq-discovery — interfaces

> This is the reference page for `mu2edaq-discovery/1`. Other packages'
> documentation should link here rather than restate the protocol or the API.
> The normative specification is [PROTOCOL.md](PROTOCOL.md); this page is the
> consumer-facing contract, including the parts of the behaviour that the
> specification does not state.

---

## 1. Wire protocol

### 1.1 Constants

| Constant | Value | Defined at |
|---|---|---|
| `PROTO` | `mu2edaq-discovery/1` | `src/mu2edaq_discovery/protocol.py:28` |
| `GROUP` | `239.255.42.99` (administratively scoped, 239/8) | `protocol.py:29` |
| `PORT` | `28999` (UDP, queries and announcements) | `protocol.py:30` |
| `BROADCAST` | `255.255.255.255` (limited broadcast) | `protocol.py:35` |
| `MAX_DATAGRAM` | `1400` bytes | `protocol.py:36` |
| `FILTER_KEYS` | `("app", "name", "host")` | `protocol.py:40` |

The C++ mirror repeats these in `cpp/include/mu2edaq_discovery/Responder.hpp:21-24`.
It does **not** define `BROADCAST` or `FILTER_KEYS`, because it has no client
and validates filter keys implicitly.

Port 28999 was chosen to collide with nothing already in the suite: 9999
(heartbeatmonitor), 37020 (bigredbox), 5555/5556 (dashboard ZMQ, trigger
scalers), 9876 (controlcenter), 7755 (dataformat-viewer), and the 5000–8088
HTTP range.

### 1.2 DISCOVER

Client to group, to broadcast, or unicast to one host. One UTF-8 JSON object
per datagram.

```json
{"proto": "mu2edaq-discovery/1",
 "type":  "DISCOVER",
 "qid":   "9f1c2e34-5d6a-4b7c-8e9f-0a1b2c3d4e5f",
 "filter": {"app": "vnc"}}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `proto` | string | yes | Must equal `mu2edaq-discovery/1` |
| `type` | string | yes | `DISCOVER` |
| `qid` | string | yes | UUID4 per query; echoed by responders so stale replies can be dropped |
| `filter` | object | no | Keys from `FILTER_KEYS` only; values are `fnmatch` globs. All named keys must match. Absent or `{}` matches everything |

Validation is `protocol.py:123-127` (`_validate_discover`) and
`protocol.py:113-120` (`_validate_filter`).

### 1.3 ANNOUNCE

Responder to the DISCOVER's source address and port, **always unicast**, after
a uniform random delay of 0–250 ms (`Responder.JITTER_MAX`,
`responder.py:31`, `:125`). The jitter exists so that a whole cluster
answering one query does not produce a synchronised burst.

```json
{"proto":   "mu2edaq-discovery/1",
 "type":    "ANNOUNCE",
 "qid":     "9f1c2e34-5d6a-4b7c-8e9f-0a1b2c3d4e5f",
 "id":      "c0ffee12-3456-4789-abcd-ef0123456789",
 "name":    "VNC mu2e-dl-01 :1 (daq-main)",
 "app":     "vnc",
 "host":    "mu2e-dl-01.fnal.gov",
 "port":    5901,
 "scheme":  "vnc",
 "version": "1.0",
 "pid":     12345,
 "started": "2026-06-12T15:04:05Z",
 "meta":    {"display": ":1", "geometry": "2560x1440"}}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `proto` | string | yes | `mu2edaq-discovery/1` |
| `type` | string | yes | `ANNOUNCE` |
| `id` | string | yes | UUID4 generated once per `Responder` object. **The deduplication key.** |
| `name` | string | yes | Human-readable label |
| `app` | string | yes | Class identifier; grouping and `--filter app=` key |
| `host` | string | yes | Advertised hostname, default `socket.getfqdn()` |
| `port` | **integer** | yes | The service's own port, not 28999. A string is rejected; a bool is rejected |
| `scheme` | string | yes | URL scheme hint (`http`, `vnc`, `tcp`, `udp`); defaults to `app` |
| `version` | string | yes | Free-form; defaults to `"0"` |
| `pid` | **integer** | yes | Responder process id |
| `started` | string | yes | ISO 8601 UTC, `%Y-%m-%dT%H:%M:%SZ` |
| `qid` | string | no | Present on a solicited reply, absent on an unsolicited announcement |
| `meta` | object | no | String keys **and** string values only. Non-string values are rejected |

Validation is `protocol.py:129-142` (`_validate_announce`). The `port`/`pid`
integer check explicitly excludes `bool`, since `isinstance(True, int)` is
true in Python (`protocol.py:133`).

`meta` is the extension point. The GUI discovers unknown `meta` keys at
runtime and renders each as a `meta.<key>` column (`gui.py:60-68`,
`:78-86`), so a responder can publish new detail with no client change.
Observed in the suite: `meta={"zmq_port": "5555"}` (dashboard),
`{"udp_port": ...}` (heartbeatmonitor), `{"gateway": ...}` (reverse-proxy),
`{"instance_id": ...}` (diskwatcher), `{"display": ":1", "geometry": ...}`
(VNC sidecar). Note every one of those stringifies its value — that is
required, not stylistic.

### 1.4 Unsolicited periodic ANNOUNCE

A responder with `announce_interval > 0` multicasts the same ANNOUNCE,
without `qid`, to the group at that interval (`responder.py:102-110`). No
package in the suite currently enables it; it exists for passive listeners
and as the migration path for `mu2edaq-heartbeatmonitor`'s `SystemRegistry`.
A client accepts such a message because the `qid` check is conditional
(`client.py:129-130`).

### 1.5 Transport

| Route | Destination | Reaches |
|---|---|---|
| Multicast | `239.255.42.99:28999` | Group members, as far as IGMP snooping and multicast routing allow |
| Broadcast | `255.255.255.255:28999`, or a subnet broadcast | Every host on the sender's subnet; not subject to IGMP snooping |
| Unicast | `host:28999` | That host |

A responder treats all three alike and always replies unicast to the source.
Clients since 1.1.0 send multicast and broadcast together and merge by `id`
(`client.py:91-101`). **The broadcast leg is not optional in practice on the
Mu2e DAQ VLAN**: the switches run IGMP snooping with no querier, so a
multicast-only scan sees only the scanner's own switch. `--no-broadcast`
restores pre-1.1.0 behaviour and is a diagnostic, not a normal mode.

Neither multicast nor broadcast crosses a router or the FNAL gateway. From
off site, run the scan on a cluster node:
`ssh -J mu2egateway01.fnal.gov <host> mu2edaq-discover --json`.

### 1.6 Size limit

1400 bytes, one Ethernet MTU with headers, so a datagram never fragments.
The check is on the **serialized** message, so a large `meta` map, a long
`name`, or a long FQDN can cross it at runtime with nothing at construction
time to warn you.

Enforcement is asymmetric, and consumers need to know this:

| Path | 1400 B enforced? | Where |
|---|---|---|
| Python `encode()` | yes, raises `ProtocolError` | `protocol.py:82-83` |
| Python `decode()` | yes, raises `ProtocolError` | `protocol.py:89-90` |
| Python receive | `recvfrom(MAX_DATAGRAM + 1)`, so an oversize datagram arrives truncated to 1401 B and then fails `decode()` | `responder.py:112`, `client.py:119` |
| C++ ANNOUNCE build | **no check at all** | `cpp/src/Responder.cpp:150-171` |
| C++ receive | `recvfrom(..., MAX_DATAGRAM, ...)`, silently truncating at 1400 B | `cpp/src/Responder.cpp:193` |

Consequence for a Python responder: an over-large ANNOUNCE raises inside the
responder thread and **kills it** — see §6. Keep `meta` small.

### 1.7 Address family

IPv4 only, in both implementations. `AF_INET` sockets, `ip_mreq` group
membership, `inet_aton`/`inet_addr` for every address. There is no IPv6
group, no `IPV6_JOIN_GROUP`, and no dual-stack path. A node reachable only
over IPv6 cannot participate.

### 1.8 Error handling on malformed input

Both responders swallow bad datagrams and keep serving. They do not agree on
what "bad" means, which matters for anyone writing a third implementation.
Verified against live responders on 2026-09-30:

| DISCOVER sent | Python responder | C++ responder |
|---|---|---|
| well-formed | replies | replies |
| `filter` is `[]`, not an object | silent | **replies** |
| filter key outside `app`/`name`/`host` | silent | **replies** (ignores the key) |
| filter value not a string (`{"app": 5}`) | silent | **replies** |
| `qid` not a string (`"qid": 123`) | silent | **replies** |
| `qid` absent | silent | **replies** (omits `qid` from the reply) |
| an ANNOUNCE, not a DISCOVER | silent | silent |
| non-UTF-8 / non-JSON bytes | silent | silent |

The Python side runs the full `decode()` validator before dispatch
(`responder.py:117-123`); the C++ side checks only `proto` and `type` and then
applies whatever filter it can interpret (`cpp/src/Responder.cpp:198-217`).
The Python behaviour is the specified one.

---

## 2. Python API

`import mu2edaq_discovery` — stdlib only, Python 3.9+, no third-party imports
on the runtime path. Public surface is `__init__.py:3-8`.

### 2.1 `Responder`

```python
class Responder(threading.Thread):
    JITTER_MAX = 0.250

    def __init__(self, name, app, port, scheme=None, version=None, meta=None,
                 host=None, group=protocol.GROUP, listen_port=protocol.PORT,
                 announce_interval=0, bind_interface=None)
    def start(self)                 # inherited from threading.Thread
    def stop(self, timeout=2.0)
    instance_id: str                # the stable ANNOUNCE `id`
```

Constructed as a daemon thread named `mu2edaq-discovery-responder`
(`responder.py:36`), so it never blocks interpreter shutdown.

| Parameter | Default | Notes |
|---|---|---|
| `name` | required | Display label |
| `app` | required | Class id; the grouping and filter key |
| `port` | required | **Your** service's port, coerced with `int()` |
| `scheme` | `app` | URL scheme hint |
| `version` | `"0"` | Free-form string |
| `meta` | `None` | `{str: str}`; counts against the 1400 B budget |
| `host` | `socket.getfqdn()` | Re-resolved on **every** announcement, not cached |
| `group` | `239.255.42.99` | |
| `listen_port` | `28999` | |
| `announce_interval` | `0` | Seconds; 0 means solicited-only |
| `bind_interface` | `0.0.0.0` | Local IPv4 for group membership and `IP_MULTICAST_IF` |

**Thread-safety.** All mutable state is confined to the responder thread. The
`_announce_kwargs` dict is written once in `__init__` and thereafter only
read (`responder.py:38-41`, `:83-86`); coordination is a single
`threading.Event`. It is therefore safe to `start()` and `stop()` from the
owning thread, and safe for the responder to run alongside an arbitrary
application. It is **not** an API for concurrent mutation: there is no
supported way to change `name`, `port` or `meta` after construction, and no
lock would protect you if you reached into `_announce_kwargs` to try.

`stop()` sets the event, sends a zero-length datagram to
`127.0.0.1:listen_port` to break the blocking `recvfrom` immediately, and
joins with `timeout` (`responder.py:51-61`). Both sockets are closed in a
`finally` (`responder.py:131-133`), so socket cleanup is correct on the
normal path and on an exception. Calling `stop()` on a responder that was
never started raises `RuntimeError: cannot join thread before it is started`
— guard it if your shutdown path can run before your startup path completes.

**`start()` cannot fail.** The socket is opened inside `run()`
(`responder.py:89`), on the new thread. A bind conflict or a refused group
membership therefore raises *in the thread*, prints a traceback, and leaves
`start()` having returned normally. The thread is dead and the application
has no indication. If your service must know, poll `is_alive()` after a short
delay. The C++ mirror does not have this problem (§3).

### 2.2 `discover()`

```python
def discover(filter=None, timeout=2.0, retries=2, group=protocol.GROUP,
             port=protocol.PORT, interface=None, broadcast=True) -> list[dict]
```

Blocking. Sends one DISCOVER to `group` and one to each broadcast address,
`retries` times spread across `timeout`; collects until `timeout` seconds
have elapsed **in total**, so the call takes `timeout` seconds whether or not
anything answers. Drops replies whose `qid` is present and does not match,
deduplicates by `id`, and returns the ANNOUNCE dicts sorted by
`(host, port)` (`client.py:103-136`).

`interface` is the local IPv4 to send from; it sets `IP_MULTICAST_IF` and
binds the socket, which also decides which subnet the broadcast leaves on
(`client.py:76-83`).

A broadcast address that is invalid from this host is skipped without
spoiling the multicast leg (`client.py:94-101`).

`discover()` blocks the calling thread. In a Qt application run it in a
`QThread` and marshal results back by signal — `gui.py:134-159` is the
reference implementation.

### 2.3 `parse_broadcast_setting()`

```python
def parse_broadcast_setting(value, default=(protocol.BROADCAST,)) -> list[str]
```

The single normaliser the CLI, the GUI, the environment, the config file and
the API all share, so the spellings cannot drift (`client.py:29-52`).
Accepts `None` (the default), a bool, a list/tuple/set, or a string:
`""`/`off`/`no`/`false`/`none`/`0` for none; `on`/`yes`/`true`/`1`/`default`
for the default; otherwise comma- or whitespace-separated addresses. Anything
else raises `ValueError`.

### 2.4 `protocol`

```python
PROTO, GROUP, PORT, BROADCAST, MAX_DATAGRAM, FILTER_KEYS
class ProtocolError(ValueError)
build_query(filter=None, qid=None) -> dict
build_announce(name, app, port, instance_id, qid=None, host=None,
               scheme=None, version=None, started=None, meta=None) -> dict
encode(msg) -> bytes          # raises ProtocolError if > MAX_DATAGRAM
decode(data) -> dict          # raises ProtocolError on anything invalid
matches_filter(announce, filter) -> bool
```

`ProtocolError` subclasses `ValueError`, so `except ValueError` catches it.

---

## 3. C++ mirror

`cpp/` is a **responder only**. There is no C++ client; scans are run from
`mu2edaq-discover(1)`. C++17 standard library plus POSIX sockets, with an
internal JSON parser in `Json.hpp`. Linux and macOS; Windows needs a Winsock
backend and has none. The only link dependency is `Threads::Threads`.

```cpp
#include <mu2edaq_discovery/Responder.hpp>

mu2edaq_discovery::Responder::Options opt;
opt.name = "Trigger Scalers";
opt.app  = "trigger-scalers";
opt.port = 5557;
opt.scheme = "udp";
mu2edaq_discovery::Responder responder(opt);
responder.start();   // throws std::system_error on socket failure
// ...
responder.stop();    // idempotent; also called by ~Responder
```

Consume it via CMake `FetchContent` with `SOURCE_SUBDIR cpp`; tests and
examples build only when it is the top-level project
(`cpp/CMakeLists.txt:22-27`). Link
`mu2edaq_discovery::mu2edaq_discovery`.

### Where the mirror matches Python

Group, port, datagram ceiling and protocol string; the 0–250 ms reply jitter;
unicast reply to the datagram source; `0.0.0.0` bind with `SO_REUSEADDR` and
`SO_REUSEPORT`; `IP_MULTICAST_TTL = 4`; the 0.5 s receive timeout plus
loopback poke for clean shutdown; `scheme` defaulting to `app`; malformed
datagrams ignored rather than fatal.

### Where it does not — read this before writing a third implementation

| | Python | C++ |
|---|---|---|
| `start()` failure | silent, thread dies (`responder.py:89`) | **throws `std::system_error` to the caller** (`Responder.cpp:80-120`) |
| `started` timestamp | regenerated per announcement (`protocol.py:70`) | **fixed at construction** (`Responder.cpp:72`) — the correct behaviour |
| `host` resolution | `getfqdn()` per announcement (`protocol.py:65`) | resolved once at construction (`Responder.cpp:74`) |
| ANNOUNCE size check | enforced, raises | **absent** (`Responder.cpp:150-171`) |
| DISCOVER validation | full validator, rejects malformed | `proto` and `type` only (`Responder.cpp:200-205`) |
| Periodic announce timing | evaluated before the blocking receive (`responder.py:102`) | evaluated after, so it can slip by up to 0.5 s (`Responder.cpp:224-236`) |
| `qid` field position | after `pid` | after `started` — cosmetic, JSON order is not significant |
| Client | provided | none |

The `start()` and `started` rows are the ones that change how a consumer must
write its code.

### There is a third and a fourth copy

`mu2edaq-controlroom-setup/server/vnc-discovery-responder.py:28-100` carries a
hand-copied minimal responder used when `mu2edaq_discovery` is not importable,
so a VNC session is discoverable on a host with no virtualenv.
`mu2edaq-resource-manager/server/discovery.py:49` has its own
`DiscoveryResponder` alongside a real `Responder`. Neither is generated from
this package; both must be kept in step by hand.

---

## 4. Config schema

`discovery.yaml`, read only when named by `--config` or
`MU2EDAQ_DISCOVERY_CONFIG`. **There is no default path** — absent both, no
file is read and the built-in defaults apply (`cli.py:36-38`). The packaged
`config/discovery.yaml` is an example.

```yaml
discovery:
  group: 239.255.42.99      # multicast group
  port: 28999               # UDP port, queries and announcements
  timeout: 2.0              # seconds a query waits for replies
  interval: 10.0            # GUI auto-probe interval; ignored by the CLI
  broadcast: [255.255.255.255]   # list, string, or false for multicast only
```

A document with no top-level `discovery:` key is accepted and the whole
document is used as the mapping (`cli.py:45`), which lets a site nest this
section inside a larger tree. Unrecognised keys are ignored. PyYAML is
required to read a file at all and is not otherwise a dependency; if it is
missing the tool exits rather than falling back (`cli.py:39-42`).

### Precedence

Command line > environment > config file > built-in default, per the project
convention (`cli.py:89-101`, `gui.py:517-535`).

| Variable | Overrides | Read by |
|---|---|---|
| `MU2EDAQ_DISCOVERY_GROUP` | `group` | CLI, GUI |
| `MU2EDAQ_DISCOVERY_PORT` | `port` | CLI, GUI |
| `MU2EDAQ_DISCOVERY_TIMEOUT` | `timeout` | CLI, GUI |
| `MU2EDAQ_DISCOVERY_INTERVAL` | `interval` | **GUI only** |
| `MU2EDAQ_DISCOVERY_BROADCAST` | `broadcast` | CLI, GUI |
| `MU2EDAQ_DISCOVERY_CONFIG` | `--config` default | CLI, GUI |

Responders embedded in applications read **none** of this. Their group, port
and interface come from their own package's configuration and are passed to
the constructor. A consumer that wants `MU2EDAQ_DISCOVERY_PORT` honoured must
read it itself.

**Caveat.** Each setting is resolved with an `or` chain, so a configured `0`
or `0.0` is falsy and silently becomes the built-in default.
`--timeout 0` waits 2 s, not 0 s (measured). `--port 0` uses 28999.

---

## 5. How a consumer package is expected to use this

### 5.1 Python service

```python
from mu2edaq_discovery import Responder

responder = Responder(
    name="Mu2e DAQ Dashboard",   # what a shifter should see
    app="dashboard",             # stable class id; keep it stable across releases
    port=5001,                   # YOUR port
    scheme="http",
    version=__version__,
    meta={"zmq_port": str(ZMQ_PORT)},   # values MUST be str()
)
responder.start()
try:
    serve_forever()
finally:
    responder.stop()
```

Rules, in order of how often they are got wrong:

1. **Start the responder only after your own listening socket is bound.**
   Otherwise discovery advertises a port that is not accepting connections and
   a shifter clicks a dead link.
2. **Every `meta` value must be a string.** An int or a bool makes the
   ANNOUNCE fail validation at the far end and your service vanishes from
   scans with no local error.
3. **Keep `meta` small.** It counts against 1400 bytes, and overflowing it
   kills the responder thread (§6).
4. **Make the import optional.** The established pattern in the suite is a
   `try/except ImportError` around the import with discovery treated as
   best-effort, because the package is not on PyPI and may be absent.
5. **`stop()` in a `finally`.** It is a daemon thread so the process will exit
   regardless, but an explicit stop closes the sockets and frees the port for
   a restart.
6. **Choose `app` once.** It is the grouping key in the GUI and the
   `--filter app=` selector in every runbook. Renaming it breaks both.

### 5.2 C++ service

As §3. The reference consumer is `mu2edaq-trigger-scalers`
(`CMakeLists.txt:85-90`, `:120`; `src/main.cpp:91-108`), which wraps `start()`
in a `try/catch` and logs rather than aborting — discovery is never allowed to
stop the application.

### 5.3 Installing it

**`mu2edaq-discovery` is not on PyPI.** Naming it in a `requirements.txt`
aborts the whole pip resolve for that file, not just that line;
`mu2edaq-bigredbox/requirements.txt:10` currently does this. The supported
path is the superproject script:

```bash
./mu2edaq-install-discovery.sh                      # into the active venv
./mu2edaq-install-discovery.sh --python /path/venv/bin/python
./mu2edaq-install-discovery.sh --editable           # editable sibling checkout
./mu2edaq-install-discovery.sh --build-wheel        # once, on a networked box
./mu2edaq-install-discovery.sh --wheel-dir /mnt/wheels   # then, offline
```

It prefers a prebuilt wheel from the wheelhouse and falls back to the sibling
checkout, and is offline-safe. The right comment to copy into a consumer's
`requirements.txt` is the one `mu2edaq-dashboard`, `mu2edaq-controlcenter`,
`mu2edaq-resource-manager` and `mu2edaq-runlog-db` already use: a commented
block naming the script, not a resolvable requirement line.

### 5.4 Why `setup.cfg` and not PEP 621 — do not "modernise" this

Metadata is in `setup.cfg`, with `pyproject.toml` holding only
`[build-system]` and a floor of `setuptools>=40.8.0` (`pyproject.toml:8`).
This is deliberate and load-bearing. The production platform is AlmaLinux 9,
whose system Python 3.9 creates venvs with **setuptools 53**. PEP 621
`[project]` support landed in setuptools 61, so a `[project]` table builds as
`UNKNOWN` there — no name, no version, no modules, and a silently broken
install. `setup.cfg` has been read since setuptools 30.3 and builds correctly
on both the AL9 stock toolchain and current setuptools.

The comment trail is in three places, all consistent: `setup.cfg:1-11`,
`pyproject.toml:1-5`, and `mu2edaq-install-discovery.sh:30-36`. The last adds
the operational detail: building a wheel still needs the `wheel` package in
the target environment; AL9 has it system-wide as `python3-wheel`, so
`python3 -m venv --system-site-packages` gets it free while a plain venv does
not — which is what the wheelhouse path exists to sidestep.

**If you add a `[project]` table, setuptools >= 61 will prefer it over
`setup.cfg` and the two will drift silently.** Keep `setup.cfg` the single
source of truth.

### 5.5 Deployment constraint: system-wide importability

`mu2edaq-trigger-scalers` links the **C++** responder, but the control room
runs a Python discovery sidecar outside any virtualenv:
`mu2edaq-controlroom-setup/server/start-vnc-session.sh:58` launches
`vnc-discovery-responder.py` with the bare system `python3`. On any node
where that runs, `mu2edaq_discovery` must be importable **system-wide**, not
only inside a package venv. That is why the sidecar carries an embedded
fallback responder, and why the stdlib-only, Python 3.9, `setup.cfg`
constraints above are hard requirements rather than preferences: the package
has to install into the AL9 system interpreter.

The same argument applies to any future Python sidecar run from a systemd
unit or a session wrapper rather than a venv-aware start script.

---

## 6. Behaviour a consumer must know about

These are review findings that change how you should write calling code.
Details and evidence in [ISSUES-PENDING.md](ISSUES-PENDING.md).

1. **An oversize ANNOUNCE kills the responder thread.** `encode()` is called
   in the receive loop with no `try/except` (`responder.py:126`); the
   `ProtocolError` escapes `run()` and the thread exits. Your application
   keeps running and is silently undiscoverable from that moment. Every
   `OSError` on the same send path *is* guarded; only the encode is not. Keep
   `meta` well under the budget. Tracked as
   [#8](https://github.com/Mu2e/mu2edaq-discovery/issues/8).
2. **`start()` cannot report failure** (§2.1). Poll `is_alive()` if you care.
3. **`started` is not a start time.** It is regenerated on every announcement
   (`protocol.py:70` via `responder.py:83-86`), so it always reads as
   "now" and uptime cannot be derived from a scan. Do not build an uptime or
   restart-detection feature on it. The C++ mirror does fix the timestamp at
   construction, so the field means different things depending on which
   implementation answered.
4. **`host` is re-resolved per announcement.** `socket.getfqdn()` runs on
   every reply (`protocol.py:65`), which can block on a slow resolver inside
   the responder thread. Pass an explicit `host=` on a node with unreliable
   DNS.
5. **The jitter sleep blocks the receive loop.** `time.sleep()` up to 250 ms
   happens inline (`responder.py:125`), so a responder answers at most about
   four queries a second and a burst of queries queues in the socket buffer.
   Fine for operator scans; do not poll it in a tight loop.
6. **Anything on the subnet can forge an ANNOUNCE.** No authentication, no
   integrity protection. A scan result is a claim, not a fact. Do not use
   discovery output as an authorisation input, and do not expose 28999 off
   the DAQ VLAN.

---

## 7. Command-line surface

| Command | Kind | Man page |
|---|---|---|
| `mu2edaq-discover` | cli | `man/man1/mu2edaq-discover.1` |
| `mu2edaq-discover-gui` | gui | `man/man1/mu2edaq-discover-gui.1` |

Declared at `setup.cfg:55-59` as a `console_scripts` and a `gui_scripts`
entry point respectively. Both man pages correspond to a declared entry
point; there are no orphan pages and no undocumented executables.
`bootstrap.sh`, `start-mu2edaq-discover-gui.sh` and
`stop-mu2edaq-discover-gui.sh` are repository-local helpers, not installed
commands, and are documented in the FILES section of
`mu2edaq-discover-gui(1)`.

```bash
mu2edaq-discover                                   # table of everything
mu2edaq-discover --filter app=vnc --json           # VNC sessions, as JSON
mu2edaq-discover --no-broadcast                    # what IGMP snooping hides
mu2edaq-discover --broadcast 131.225.245.255 --broadcast 10.226.9.255
mu2edaq-discover-gui --auto --interval 15
```

Exit status: 0 on success including an empty result; 1 on a bad filter, an
unreadable config, missing PyYAML with `--config`, or a protocol error; 2 from
the argument parser on an invalid command line.

---

## See also

- [PROTOCOL.md](PROTOCOL.md) — normative wire specification
- [ARCHITECTURE.md](ARCHITECTURE.md) — components, threading, data flow
- `mu2edaq-discovery(7)` — protocol overview as a man page
- `mu2edaq_discovery(3)`, `libmu2edaq_discovery(3)` — API man pages
- `discovery.yaml(5)` — config file format
