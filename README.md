# mu2edaq-discovery

UDP multicast and broadcast service discovery for Mu2e DAQ applications.
Provides a tiny, stdlib-only Python library and a CLI so operators can see
which DAQ applications are running, where (node and port), and who they are.

See [doc/PROTOCOL.md](doc/PROTOCOL.md) for the wire protocol
(`mu2edaq-discovery/1`, multicast `239.255.42.99:28999`, JSON
query/response).

## Install

```bash
./bootstrap.sh             # creates venv/ and installs the package + dev deps
./bootstrap.sh --gui       # ...and PyQt6, for mu2edaq-discover-gui
# or, into an existing environment:
pip install -e .
```

Runtime has **zero dependencies** (Python >= 3.9, stdlib only). PyYAML
is only needed if you point the CLI at a YAML config file.

## Embedding a responder (applications)

```python
from mu2edaq_discovery import Responder

r = Responder(name="Mu2e DAQ Dashboard", app="dashboard", port=5001,
              scheme="http", meta={"zmq_port": "5555"})
r.start()          # daemon thread; answers DISCOVER queries
...
r.stop()           # on shutdown
```

Start the responder **after** your service's listening socket is bound,
so discovery never advertises a port that isn't accepting connections.

## Querying

```python
from mu2edaq_discovery import discover
services = discover(filter={"app": "vnc"}, timeout=2.0)
# broadcast=True (default) also broadcasts to 255.255.255.255;
# broadcast=["131.225.245.255"] names the subnets; broadcast=False is multicast only.
```

Or from the shell:

```bash
mu2edaq-discover                          # table of everything
mu2edaq-discover --filter app=vnc         # only VNC sessions
mu2edaq-discover --json | python3 -m json.tool
```

Configuration precedence: command line > environment
(`MU2EDAQ_DISCOVERY_GROUP`, `MU2EDAQ_DISCOVERY_PORT`,
`MU2EDAQ_DISCOVERY_TIMEOUT`, `MU2EDAQ_DISCOVERY_INTERVAL`,
`MU2EDAQ_DISCOVERY_BROADCAST`) > config file
(`--config` / `MU2EDAQ_DISCOVERY_CONFIG`, see `config/discovery.yaml`) >
defaults.

## GUI

A lightweight Qt browser for discoverable resources:

```bash
./start-mu2edaq-discover-gui.sh        # sets up venv/ (with PyQt6) and launches
# or, in an existing environment:
pip install -e '.[gui]'
mu2edaq-discover-gui --auto --interval 15
```

* Every published parameter is a column — the core fields first, then a
  `meta.<key>` column for each extra parameter a responder advertises,
  discovered at run time.
* Click a header to sort by that field (`port` and `pid` sort
  numerically); drag headers to reorder columns.
* Instances of the same class (`app`) are grouped under a bold class row
  with an instance count.
* Resources claiming the same `host:port` are flagged in **bold red**
  with a tooltip, and counted in the status bar.
* If nothing answers, the table shows a single *No resources found* row.
* Right-click a row to copy the record as plain text, as JSON, just the
  field under the cursor, or any single field from the **Copy Field**
  submenu. Class rows copy the whole group; *Copy All Resources* copies
  everything.
* Toolbar: **Probe** (F5), filter by `app`/`name`/`host` glob, **Auto**
  re-probe at an adjustable interval, expand/collapse all.

The GUI takes the same options and configuration precedence as the CLI;
see `man ./man/mu2edaq-discover-gui.1`. Stop a running instance with
`./stop-mu2edaq-discover-gui.sh`.

### Why the query is broadcast as well as multicast

Measured on the DAQ VLAN in September 2026: every node on one `/24`, every
responder up, yet a multicast scan from `mu2e-mgr-01` found only itself, one
from `mu2e-trk-03` found only the tracker, calorimeter and CRV nodes on its own
switch, and one from `mu2e-trk-11` found a third island. The switches run IGMP
snooping with no querier, so each forwards the group only to ports it has seen
join, and membership never propagates between switches. Broadcast is not
subject to snooping and floods the whole VLAN, and a unicast datagram to any
node's port 28999 is answered at once.

Since 1.1.0 `discover()` therefore sends the same DISCOVER to the multicast
group *and* to the subnet broadcast (`255.255.255.255` by default), merging
replies by responder id. Responders needed no change. `--broadcast ADDR`
(repeatable) chooses other addresses, for instance one per subnet of a
multi-homed node; `--no-broadcast` restores multicast-only. The network fix is
an IGMP querier on the VLAN, which would let plain multicast work everywhere.

Note: neither multicast nor broadcast traverses a router or the FNAL gateway.
From off-site, run the query on a cluster node: `ssh -J mu2egateway01.fnal.gov
<host> mu2edaq-discover --json`.

## Tests

```bash
venv/bin/pytest          # protocol unit tests + loopback multicast round-trip
```

The loopback tests skip automatically in environments where multicast
on 127.0.0.1 is unavailable.

## Man pages

`man ./man/mu2edaq-discover.1`, `man ./man/mu2edaq-discover-gui.1`
