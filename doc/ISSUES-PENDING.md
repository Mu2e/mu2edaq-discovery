# Staged issues — mu2edaq-discovery

Sixteen findings from the September 2026 DAQ mega-review
(`mu2e-sept-mega-review`, 2026-09-30).

`Mu2e/mu2edaq-discovery` **is** a usable remote and issues are enabled — four
prior issues (#4–#7) exist, all closed. Issue creation succeeded once
(DISC-001 became
[#8](https://github.com/Mu2e/mu2edaq-discovery/issues/8)) and was then
blocked by this session's permission classifier, as was `gh issue edit` and
`gh label create`. The remaining fifteen are staged here verbatim in the
CONTRACT.md §6 body format, with fingerprints, ready to file unchanged.

**Dedup performed** against `gh issue list --state all --limit 300`: issues
#4, #5, #6, #7 are all CLOSED and none carries a mega-review fingerprint.
DISC-005 and DISC-006 touch the same C++ file as the closed #4 (malformed
numeric JSON) and #7 (bind_interface on announcements), but describe
different defects with no significant title-token overlap, so they are filed
fresh with a `Related` back-reference rather than commented onto a closed
issue.

**Still to do when filing is unblocked:**

```bash
REPO=Mu2e/mu2edaq-discovery
gh label create mega-review -R "$REPO" -c 6F42C1 \
  -d "Filed by the Sept 2026 DAQ mega-review" 2>/dev/null || true
gh issue edit 8 -R "$REPO" --body-file <DISC-001 body below> \
  --add-label mega-review --add-label bug     # #8 was filed with a stub body
# then the remaining fifteen, sleeping 4 s between calls
```

---

## DISC-001 — FILED as [#8](https://github.com/Mu2e/mu2edaq-discovery/issues/8)

> Filed with a placeholder body before filing was blocked. The body below is
> the intended one; apply it with `gh issue edit 8 --body-file`.

**Title:** `[responder] an oversized ANNOUNCE kills the responder thread for the life of the process`

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/mu2edaq_discovery/responder.py:126`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`Responder.run()` calls `protocol.encode()` inside the receive loop with no
`try/except`. `encode()` raises `ProtocolError` when the serialized ANNOUNCE
exceeds `MAX_DATAGRAM` (1400 B). Because the responder is a
`threading.Thread`, the exception propagates out of `run()`, prints a
traceback to stderr, and the thread exits. The embedding application keeps
running and is silently undiscoverable from that moment on.

## Evidence
```
$ python - <<'PY'
from mu2edaq_discovery import Responder, protocol
import socket, time
r = Responder(name="big", app="big", port=1, meta={"blob": "z"*1500},
              listen_port=28997, bind_interface="127.0.0.1")
r.start(); time.sleep(0.3)
print("alive before query:", r.is_alive())
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(protocol.encode(protocol.build_query()), ("127.0.0.1", 28997))
time.sleep(0.8)
print("alive after query :", r.is_alive())
PY
Exception in thread mu2edaq-discovery-responder:
  File ".../responder.py", line 126, in run
    reply = protocol.encode(self._announce(qid=msg.get("qid")))
  File ".../protocol.py", line 83, in encode
    raise ProtocolError("message exceeds %d bytes" % MAX_DATAGRAM)
mu2edaq_discovery.protocol.ProtocolError: message exceeds 1400 bytes
alive before query: True
alive after query : False
```

The size check is on the *serialized* message, so a `meta` map, a long `name`
or a long FQDN can cross the limit at runtime with nothing at construction
time to warn about it. Every `OSError` on the send path in the same loop *is*
guarded (`responder.py:108-109`, `:129-130`); only the encode is not.

## Why it matters
Sixteen packages in the suite embed `Responder` in a daemon thread and none
checks `is_alive()`. A node whose responder died this way disappears from
`mu2edaq-discover` scans and from the control room browser while the service
itself is healthy, which reads to a shifter as a node outage.

## Suggested fix
Guard the encode in the loop, log once, and continue serving:

```python
try:
    reply = protocol.encode(self._announce(qid=msg.get("qid")))
except protocol.ProtocolError:
    continue
```

Better still, also validate the size once in `Responder.__init__` so an
over-large `meta` fails fast at construction rather than on the first query.

## Related
- Mu2e/mu2edaq-discovery#5

<!-- mega-review-fingerprint: 2f5b125d -->

---

## DISC-002

**Title:** `[responder] Python start() cannot report a socket failure; the C++ mirror can`

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/mu2edaq_discovery/responder.py:89`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`Responder.start()` is `threading.Thread.start()`; the socket is opened in
`run()`, on the new thread. Any failure there — port already bound by a
process that did not set `SO_REUSEPORT`, `IP_ADD_MEMBERSHIP` refused on an
interface with no multicast — raises inside the thread. `start()` has already
returned successfully, so the caller cannot learn that discovery is not
running.

## Evidence
```
$ python - <<'PY'
import socket, time
from mu2edaq_discovery import Responder
blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
blocker.bind(("", 28994))
r = Responder(name="x", app="x", port=1, listen_port=28994,
              bind_interface="127.0.0.1")
r.start()
print("start() returned normally")
time.sleep(0.5)
print("thread alive:", r.is_alive())
PY
Exception in thread mu2edaq-discovery-responder:
  File ".../responder.py", line 73, in _open_socket
    sock.bind(("", self.listen_port))
OSError: [Errno 48] Address already in use
start() returned normally
thread alive: False
```

The C++ mirror does the opposite and is the better model: `Responder::start()`
opens and binds on the calling thread and throws `std::system_error` before
spawning (`cpp/src/Responder.cpp:80-120`). `mu2edaq-trigger-scalers` relies on
exactly that (`src/main.cpp:104-108` catches and logs).

## Why it matters
The Python and C++ halves of one documented API have opposite failure
contracts. A Python service whose responder fails to bind reports nothing and
never appears in a scan; the sixteen embedding packages have no `is_alive()`
check because the API gives them no reason to expect one.

## Suggested fix
Move `self._sock = self._open_socket()` from `run()` into an overridden
`start()`, before `super().start()`, so the `OSError` reaches the caller and
matches the C++ contract. If that is too disruptive, document prominently
that `start()` cannot fail and that callers must poll `is_alive()`.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: 09c093b6 -->

---

## DISC-003

**Title:** `[protocol] the started field is regenerated per announcement, so it is not a start time`

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/mu2edaq_discovery/protocol.py:70`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`Responder._announce()` calls `protocol.build_announce()` afresh for every
reply (`responder.py:83-86`), and `build_announce()` defaults `started` to
`datetime.now(timezone.utc)` (`protocol.py:70`). Nothing caches it. The
advertised start time therefore always reads as "now", not as when the
service started.

## Evidence
```
$ python - <<'PY'
import time
from mu2edaq_discovery import Responder
r = Responder(name="t", app="t", port=1, host="h.example")
a1 = r._announce(); print("started #1:", a1["started"])
time.sleep(2.1)
a2 = r._announce(); print("started #2:", a2["started"])
print("id stable:", a1["id"] == a2["id"])
PY
started #1: 2026-09-30T20:15:00Z
started #2: 2026-09-30T20:15:02Z
id stable: True
```

`id` is correctly fixed at construction (`responder.py:37`); `started` is
not. The C++ mirror gets this right — `started_ = iso8601_utc_now()` runs once
in the constructor (`cpp/src/Responder.cpp:72`) — so the same field means
different things depending on which implementation answered.

## Why it matters
`doc/PROTOCOL.md:64` documents `started` as the service start time and
`mu2edaq-discover` prints it in a `STARTED` column, where an operator reads it
as uptime. A service that has been up for three days and one restarted ten
seconds ago are indistinguishable, so the column is actively misleading during
an incident, and no restart-detection or uptime feature can be built on it.

## Suggested fix
Compute the timestamp once in `Responder.__init__`, alongside `instance_id`,
and pass it through `_announce_kwargs` — mirroring `cpp/src/Responder.cpp:72`.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: 35690e38 -->

---

## DISC-004

**Title:** `[responder] socket.getfqdn() is re-resolved on every announcement inside the responder thread`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/mu2edaq_discovery/protocol.py:65`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
When `host` is not given explicitly, `build_announce()` calls
`socket.getfqdn()` (`protocol.py:65`), and because `_announce()` rebuilds the
message for every reply this runs once per query answered rather than once per
process.

## Evidence
```
$ python - <<'PY'
import socket
from mu2edaq_discovery import Responder
calls = []
orig = socket.getfqdn
socket.getfqdn = lambda *a: (calls.append(1), orig(*a))[1]
r = Responder(name="t", app="t", port=1)
r._announce(); r._announce()
socket.getfqdn = orig
print("getfqdn calls for 2 announces:", len(calls))
PY
getfqdn calls for 2 announces: 2
```

The C++ mirror resolves the FQDN once in the constructor
(`cpp/src/Responder.cpp:74`).

## Why it matters
`getfqdn()` can block on a reverse DNS lookup. It runs on the responder
thread, inside the receive loop, so a slow or unreachable resolver stalls the
loop and the responder misses queries it would otherwise have answered. On the
DAQ network this is latent rather than active, but it makes the responder's
worst-case latency a function of DNS health for no benefit — the hostname does
not change during a process's life.

## Suggested fix
Resolve once in `Responder.__init__` and store the result in
`_announce_kwargs`, matching the C++ behaviour. Callers who need a different
name already pass `host=`.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: c0f78fd4 -->

---

## DISC-005

**Title:** `[cpp] the C++ responder answers malformed DISCOVER messages that the Python responder rejects`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `cpp/src/Responder.cpp:198`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The C++ responder validates only `proto` and `type` before dispatching
(`Responder.cpp:200-205`) and then applies whatever `filter` it can interpret
(`Responder.cpp:139-148`). The Python responder runs the full `decode()`
validator first (`responder.py:117-123`) and stays silent on anything
malformed. The two implementations therefore answer a different set of
messages for the same protocol version.

## Evidence
Both responders run on a private loopback port; each row is one DISCOVER
datagram sent by hand.

```
DISCOVER sent                         Python      C++
------------------------------------  ----------  ----------
well-formed                           replies     replies
"filter": []  (not an object)         silent      REPLIES
filter key outside app/name/host      silent      REPLIES
"filter": {"app": 5}  (not a string)  silent      REPLIES
"qid": 123    (not a string)          silent      REPLIES
"qid" absent                          silent      REPLIES
an ANNOUNCE, not a DISCOVER           silent      silent
non-UTF-8 / non-JSON bytes            silent      silent
```

`Responder.cpp:143-144` returns `true` for any filter key it cannot read, so
an unknown key is ignored rather than treated as a non-match; `qid` is taken
with `as_string()`, which returns `""` for a non-string rather than failing
(`Json.hpp:60-62`).

## Why it matters
`doc/PROTOCOL.md:44` says "Responders that do not match MUST NOT reply", and a
DISCOVER naming a filter key the responder does not know is, by that rule, a
non-match. A future filter key would be silently ignored by every C++
responder while being honoured by every Python one, so a filtered scan would
return a superset from the C++ nodes. It also means the divergence is not
visible until someone extends the protocol.

## Suggested fix
Mirror `protocol._validate_discover` and `_validate_filter` in
`Responder::matches_filter` and its caller: reject a non-object `filter`, a
non-string `qid`, a non-string filter value, and any key outside
`app`/`name`/`host`, and stay silent in each case. Add the eight rows above to
`cpp/tests/test_responder.cpp`.

## Related
- Mu2e/mu2edaq-discovery#4
- Mu2e/mu2edaq-discovery#5

<!-- mega-review-fingerprint: e09d5d64 -->

---

## DISC-006

**Title:** `[cpp] the C++ responder never checks its ANNOUNCE against the 1400-byte limit`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `cpp/src/Responder.cpp:170`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`MAX_DATAGRAM` is declared (`cpp/include/mu2edaq_discovery/Responder.hpp:24`)
and used to size the receive buffer, but `build_announce()` returns
`Json(...).dump()` with no length check and `run()` hands it straight to
`sendto()` (`Responder.cpp:214-215`). A large `meta` map produces an
over-1400-byte datagram that is emitted anyway.

## Evidence
```
$ grep -n 'MAX_DATAGRAM' cpp/src/Responder.cpp cpp/include/mu2edaq_discovery/Responder.hpp
cpp/include/mu2edaq_discovery/Responder.hpp:24:constexpr int MAX_DATAGRAM = 1400;
cpp/src/Responder.cpp:190:        char buf[MAX_DATAGRAM + 1];
cpp/src/Responder.cpp:193:        ssize_t n = ::recvfrom(sock_, buf, MAX_DATAGRAM, 0,
```

The only uses are the receive buffer. `build_announce()`
(`Responder.cpp:150-171`) has none. The Python equivalent enforces it in both
directions (`protocol.py:82-83`, `:89-90`).

Compounding it, the C++ receive path passes `MAX_DATAGRAM` (not `+1`) to
`recvfrom`, so an oversize datagram is silently truncated to exactly 1400
bytes and then usually fails to parse, whereas Python reads `MAX_DATAGRAM + 1`
specifically so the overflow is detectable.

## Why it matters
A C++ responder with a large `meta` emits a datagram that fragments at the IP
layer or is dropped, and the failure appears as an intermittently invisible
service with nothing logged locally. The Python responder fails loudly in the
same situation (too loudly — see #8), so the two have opposite failure modes
for the same mistake.

## Suggested fix
Check `reply.size() > MAX_DATAGRAM` in `run()` before `sendto()`, and refuse
over-large `Options` in the constructor by building one announcement and
measuring it — a constructor throw is the natural place, since `start()`
already throws. Also read with `MAX_DATAGRAM + 1` so truncation is detectable.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: 85c68477 -->

---

## DISC-007

**Title:** `[ci] 60 pytest tests and a ctest suite with no CI to run them`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** enhancement
**Location:** `.github/workflows` (absent)
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The package has a substantial test suite — 60 pytest tests across four files
and three ctest targets — and nothing runs any of it automatically.

## Evidence
```
$ ls -d .github
ls: .github: No such file or directory

$ venv/bin/python -m pytest -q
............................................................  [100%]
60 passed in 13.51s

$ grep -c 'add_test' cpp/CMakeLists.txt
3
```

## Why it matters
This is the package sixteen others depend on, and it is the one where a
regression propagates furthest. Two of the four closed issues (#4, #6) are
defects a test run would have caught, and #4 was important enough that
`cpp/CMakeLists.txt:40` carries a comment marking its regression test. There
is no gate stopping the next one from being merged.

Supporting detail for whoever writes the workflow: the loopback tests skip
themselves where multicast on 127.0.0.1 is unavailable
(`tests/test_loopback.py:33-36`), and the C++ responder test signals a skip
with return code 77 (`cpp/CMakeLists.txt:48`), so both suites are already
CI-sandbox-safe.

## Suggested fix
A single `.github/workflows/test.yml`: matrix over Python 3.9 and 3.12,
`pip install -e '.[dev,yaml]'`, `pytest`; plus a job running
`cmake -S cpp -B cpp/build && cmake --build cpp/build && ctest --test-dir cpp/build`.
Pin at least one leg to a `python:3.9` container so the AlmaLinux 9 floor that
`setup.cfg:1-11` exists to protect is actually exercised.

<!-- mega-review-fingerprint: 070e0f73 -->

---

## DISC-008

**Title:** `[packaging] setup.cfg declares BSD-3-Clause but LICENSE is MIT`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `setup.cfg:20`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The package metadata and the shipped licence file name different licences.

## Evidence
```
$ grep -n 'license' setup.cfg
20:license = BSD-3-Clause
21:license_files = LICENSE
25:classifiers =
28:    License :: OSI Approved :: BSD License

$ head -3 LICENSE
MIT License

Copyright (c) 2026 Fermi Forward Discovery Group, LLC
```

`git log` shows `89b0910 Add MIT LICENSE` landing after the metadata was
written, so the `setup.cfg` line was simply not updated.

## Why it matters
Every built wheel and sdist carries `License: BSD-3-Clause` in its metadata
and an MIT `LICENSE` in its payload. Anything that audits licences from
package metadata — and Fermilab software releases are audited — records the
wrong licence for this package and, transitively, for the sixteen that vendor
or depend on it.

## Suggested fix
One line: `license = MIT` at `setup.cfg:20`, and change the classifier at
`setup.cfg:28` to `License :: OSI Approved :: MIT License`. Confirm MIT is the
intended licence first, since the alternative fix is to replace `LICENSE`.

<!-- mega-review-fingerprint: 2d6fec64 -->

---

## DISC-009

**Title:** `[responder] the reply jitter sleeps inline, capping a responder at about four queries a second`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** enhancement
**Location:** `src/mu2edaq_discovery/responder.py:125`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The anti-storm jitter is a blocking `time.sleep(random.uniform(0, 0.250))`
executed in the receive loop, before the reply is sent and before the next
`recvfrom`.

## Evidence
```
$ sed -n '111,130p' src/mu2edaq_discovery/responder.py
                try:
                    data, addr = self._sock.recvfrom(protocol.MAX_DATAGRAM + 1)
                except socket.timeout:
                    continue
...
                time.sleep(random.uniform(0, self.JITTER_MAX))
                reply = protocol.encode(self._announce(qid=msg.get("qid")))
```

Mean sleep 125 ms, so the steady-state ceiling is about 8 queries/s and the
worst case about 4/s. The C++ mirror has the identical structure
(`cpp/src/Responder.cpp:211-215`).

## Why it matters
Very little today: operator scans are two datagrams every few seconds. It is
worth recording because the periodic-announce timer shares the loop, so a
backlog of queries also delays unsolicited announcements, and because anyone
who later builds a polling monitor on top of discovery will hit the ceiling
without an obvious cause. Logged as S4 rather than S3 because there is no
current consumer that polls.

## Suggested fix
None required now. If it ever matters, schedule the reply at
`monotonic() + jitter` in a small pending-reply list and keep receiving, or
send from a short-lived thread. Documenting the ceiling in
`doc/PROTOCOL.md` would be enough for the moment.

<!-- mega-review-fingerprint: 199784c7 -->

---

## DISC-010

**Title:** `[responder] stop() raises RuntimeError when the responder was never started`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `src/mu2edaq_discovery/responder.py:61`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`stop()` calls `self.join()` unconditionally. On a `Responder` that was
constructed but never started, `threading.Thread.join()` raises.

## Evidence
```
$ python -c "
from mu2edaq_discovery import Responder
Responder(name='t', app='t', port=1).stop()"
RuntimeError: cannot join thread before it is started
```

The C++ mirror guards this: `if (!thread_.joinable()) return;`
(`cpp/src/Responder.cpp:123`).

## Why it matters
The documented usage pattern is `start()` then `stop()` in a `finally`
(`README.md:28-33`). A service that fails during initialisation after
constructing the responder but before starting it hits the `finally`, and the
`RuntimeError` masks the original startup exception in the traceback. Minor,
but it turns one clear failure into two confusing ones.

## Suggested fix
`if not self.is_alive() and not self.ident: return` at the top of `stop()`,
or wrap the `join()` in `try/except RuntimeError`. Mirror the C++ guard.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: e7ebbf36 -->

---

## DISC-011

**Title:** `[docs] the protocol specification does not state that mu2edaq-discovery is IPv4-only`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `doc/PROTOCOL.md:11`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
Both implementations are IPv4-only by construction, and no document says so.
`doc/PROTOCOL.md`'s parameter table gives a group and a port without naming
the address family, and the transport section discusses routing without
mentioning that IPv6 has no path at all.

## Evidence
```
$ grep -cn 'AF_INET6\|IPV6\|ip_mreq6\|inet_pton' src/mu2edaq_discovery/*.py cpp/src/*.cpp cpp/include/mu2edaq_discovery/*.hpp
0

$ grep -n 'AF_INET\|inet_aton' src/mu2edaq_discovery/responder.py
66:        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
76:            socket.inet_aton(self.group),
77:            socket.inet_aton(self.bind_interface),
90:        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
94:            socket.inet_aton(self.bind_interface),
```

`inet_aton` and `inet_addr` accept IPv4 dotted-quad only, so passing an IPv6
`group` or `bind_interface` fails rather than degrading.

## Why it matters
This is a constraint a reader of the specification would want stated, not
inferred. It also bounds the effort of any future IPv6 work: it is not a
configuration change but new socket setup, a new group, `IPV6_JOIN_GROUP`, and
a second broadcast story (IPv6 has no broadcast — the equivalent is the
all-nodes link-local multicast address).

## Suggested fix
Add an "Address family" line to the parameter table at `doc/PROTOCOL.md:11-17`
and a short paragraph in the Transport section. `man/man7/mu2edaq-discovery.7`
and `doc/INTERFACES.md` already state it; the specification should agree.

<!-- mega-review-fingerprint: adbaae7a -->

---

## DISC-012

**Title:** `[cpp] the C++ project version is pinned at 1.0.0 while the Python package is 1.1.0`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `cpp/CMakeLists.txt:2`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The two halves of one package carry different version numbers, and nothing
keeps them in step.

## Evidence
```
$ grep -n 'VERSION 1' cpp/CMakeLists.txt
2:project(mu2edaq_discovery_cpp VERSION 1.0.0 LANGUAGES CXX)

$ grep -n '__version__\|^version' src/mu2edaq_discovery/__init__.py setup.cfg
src/mu2edaq_discovery/__init__.py:7:__version__ = "1.1.0"
setup.cfg:15:version = 1.1.0
```

`git tag` shows the repository is at `t01.00.00`, so neither number matches
the release tag convention either.

## Why it matters
`mu2edaq-trigger-scalers` consumes the C++ library through `FetchContent` with
`GIT_TAG main` (`mu2edaq-trigger-scalers/CMakeLists.txt:87`), so the CMake
version is the only version signal a C++ consumer has, and it is wrong. A
consumer that ever writes `find_package(mu2edaq_discovery 1.1)` would fail
against a library that implements 1.1.0 behaviour.

Note the *wire* protocol version is a separate and correct constant
(`mu2edaq-discovery/1`), unaffected by this.

## Suggested fix
Set `VERSION 1.1.0` in `cpp/CMakeLists.txt:2` and add a release-checklist line
that the three version strings — `setup.cfg`, `__init__.py`,
`cpp/CMakeLists.txt` — move together. Pinning `GIT_TAG` in
`mu2edaq-trigger-scalers` to a release tag instead of `main` is a separate
improvement, filed against that package.

<!-- mega-review-fingerprint: eebe06f1 -->

---

## DISC-013

**Title:** `[cli] --timeout 0 silently waits two seconds because options are resolved with an or chain`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `src/mu2edaq_discovery/cli.py:92`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
Every numeric setting is resolved with a chain of `or`, so an explicitly
supplied `0` is falsy and falls through to the next source and ultimately to
the built-in default.

## Evidence
```
$ grep -n 'or os.environ' src/mu2edaq_discovery/cli.py
90:    group = (args.group or os.environ.get("MU2EDAQ_DISCOVERY_GROUP")
92:    port = int(args.port or os.environ.get("MU2EDAQ_DISCOVERY_PORT")
94:    timeout = float(args.timeout or os.environ.get("MU2EDAQ_DISCOVERY_TIMEOUT")

$ time mu2edaq-discover --timeout 0.5 --retries 1 --no-broadcast --group 239.255.42.97
0.603 total
$ time mu2edaq-discover --timeout 0 --retries 1 --no-broadcast --group 239.255.42.97
2.099 total
```

The same pattern is duplicated in `gui.py:519-528`, where `interval` has it
too.

## Why it matters
Small, but it is a silent override of an explicit instruction: the user asked
for zero and got the default with no warning. `--timeout 0` is a reasonable
thing for a script to pass when it only wants the send side, and `--port 0` is
plausible in a test harness. The duplication between `cli.py` and `gui.py`
means a fix must be made twice, which is the more durable problem.

## Suggested fix
Resolve with explicit `is not None` tests rather than `or`, and factor the
resolution into one helper the CLI and the GUI share, as `resolve_broadcast()`
(`cli.py:19-33`) already does for the broadcast setting.

<!-- mega-review-fingerprint: 56e94ea1 -->

---

## DISC-014

**Title:** `[docs] README points at man/mu2edaq-discover.1 but the pages now live in man/man1/`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `README.md:127`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
This review moved the two man pages from a flat `man/` into `man/man1/` for
consistency with the rest of the suite, and added `man3`, `man5` and `man7`
pages. `README.md` still gives the old flat paths.

## Evidence
```
$ grep -n 'man/' README.md
91:see `man ./man/mu2edaq-discover-gui.1`. Stop a running instance with
127:`man ./man/mu2edaq-discover.1`, `man ./man/mu2edaq-discover-gui.1`
```

## Why it matters
Copy-pasting either line now fails. Trivial, and fixed in the same review, but
recorded so the fingerprint exists if the paths regress.

## Suggested fix
Already applied in the mega-review docs commit: the README's man section now
lists all six pages under their `man/manN/` paths. No further action unless
the layout changes again.

<!-- mega-review-fingerprint: c70b55e8 -->

---

## DISC-015

**Title:** `[protocol] the wire format is implemented four times with no generator or conformance test`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** enhancement
**Location:** `doc/PROTOCOL.md:1`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`mu2edaq-discovery/1` is implemented four separate times: the Python
`protocol.py`, the C++ `Responder.cpp`, a hand-copied fallback responder in
`mu2edaq-controlroom-setup`, and a second responder class in
`mu2edaq-resource-manager`. Nothing tests them against each other.

## Evidence
```
$ grep -rn 'mu2edaq-discovery/1' --include=*.py --include=*.cpp --include=*.hpp .. \
    | grep -v '^../mu2edaq-discovery/src' | grep -v venv
../mu2edaq-controlroom-setup/server/vnc-discovery-responder.py:34:    GROUP, PORT, PROTO, MAX_DGRAM = "239.255.42.99", 28999, "mu2edaq-discovery/1", 1400
../mu2edaq-discovery/cpp/include/mu2edaq_discovery/Responder.hpp:21:constexpr const char* PROTO = "mu2edaq-discovery/1";

$ grep -n 'class.*Responder' ../mu2edaq-controlroom-setup/server/vnc-discovery-responder.py \
    ../mu2edaq-resource-manager/server/discovery.py
../mu2edaq-controlroom-setup/server/vnc-discovery-responder.py:38:    class Responder(threading.Thread):
../mu2edaq-resource-manager/server/discovery.py:49:class DiscoveryResponder(threading.Thread):
```

The `vnc-discovery-responder.py` copy carries its own comment admitting the
problem: "Keep in sync with the mu2edaq-discovery package".

DISC-005 documents one concrete consequence — the Python and C++ responders
already disagree about which malformed DISCOVER messages deserve a reply, and
that divergence went unnoticed because nothing compares them.

## Why it matters
Four hand-maintained copies of one wire format, with no cross-implementation
test, is how a protocol quietly forks. The copies exist for good reasons (the
VNC sidecar must work with no virtualenv), so consolidation is not the answer;
a conformance test is.

## Suggested fix
Add a conformance corpus to this repository: a directory of DISCOVER datagrams
with the expected reply-or-silence for each, plus a tiny driver that points at
a `host:port` and reports pass or fail. Both the Python and the C++ test
suites can then run it against their own responder, and the two out-of-tree
copies can be checked manually before a release. The eight rows in DISC-005
are the starting corpus.

## Related
- Mu2e/mu2edaq-discovery#8

<!-- mega-review-fingerprint: f36464fd -->

---

## DISC-016

**Title:** `[packaging] mu2edaq-bigredbox names mu2edaq-discovery in requirements.txt, which aborts the whole pip resolve`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `mu2edaq-bigredbox/requirements.txt:10` (file this against `Mu2e/mu2edaq-bigredbox`)
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`mu2edaq-discovery` is not published on PyPI. Naming it as a bare requirement
makes pip fail to resolve the *entire* requirements file, not just that line,
so none of the package's dependencies install.

## Evidence
```
$ grep -n 'mu2edaq-discovery' */requirements.txt
mu2edaq-bigredbox/requirements.txt:10:mu2edaq-discovery
mu2edaq-controlcenter/requirements.txt:7:# best-effort (see the try/except around `from mu2edaq_discovery import
mu2edaq-dashboard/requirements.txt:8:# best-effort (see the try/except around `from mu2edaq_discovery import
mu2edaq-resource-manager/requirements.txt:9:# best-effort (see the try/except around `from mu2edaq_discovery import
mu2edaq-runlog-db/requirements.txt:10:# best-effort (see the try/except around `from mu2edaq_discovery import
```

Four sibling packages get this right with a commented block; `bigredbox` is
the outlier with an uncommented requirement line.

## Why it matters
A fresh `pip install -r requirements.txt` for `mu2edaq-bigredbox` fails
outright on a node with no local index, which is every DAQ node. The failure
message names the missing package and reads as a network problem rather than a
packaging error, so it costs real time to diagnose.

## Suggested fix
Replace `mu2edaq-discovery` at line 10 with the commented block the other four
packages use, naming `./mu2edaq-install-discovery.sh` as the supported install
path. Filed here because it was found while reviewing this package; the fix
belongs in `Mu2e/mu2edaq-bigredbox`.

<!-- mega-review-fingerprint: b7cc489a -->
