"""Command line interface: mu2edaq-discover.

Configuration precedence: command line > environment > config file > defaults.
Environment variables: MU2EDAQ_DISCOVERY_GROUP, MU2EDAQ_DISCOVERY_PORT,
MU2EDAQ_DISCOVERY_TIMEOUT. Config file (YAML, optional): --config or
MU2EDAQ_DISCOVERY_CONFIG; PyYAML is only required when a config file is used.
"""

import argparse
import json
import os
import sys

from . import protocol
from .client import discover


def _load_config(path):
    if not path:
        return {}
    try:
        import yaml
    except ImportError:
        sys.exit("error: PyYAML is required to read config files (pip install pyyaml)")
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("discovery", data)


def _parse_filter(pairs):
    filt = {}
    for pair in pairs or []:
        if "=" not in pair:
            sys.exit("error: --filter takes key=glob (keys: %s)" %
                     ", ".join(protocol.FILTER_KEYS))
        key, _, value = pair.partition("=")
        filt[key.strip()] = value.strip()
    return filt or None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mu2edaq-discover",
        description="Query the network for mu2edaq services via UDP multicast.",
    )
    parser.add_argument("--filter", action="append", metavar="KEY=GLOB",
                        help="filter results, e.g. --filter app=vnc (repeatable)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds to wait for replies (default 2.0)")
    parser.add_argument("--retries", type=int, default=2,
                        help="number of query transmissions (default 2)")
    parser.add_argument("--group", default=None, help="multicast group")
    parser.add_argument("--port", type=int, default=None, help="UDP port")
    parser.add_argument("--interface", default=None,
                        help="local interface IP for multicast")
    parser.add_argument("--config", default=os.environ.get("MU2EDAQ_DISCOVERY_CONFIG"),
                        help="YAML config file")
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="output JSON")
    fmt.add_argument("--table", action="store_true", help="output a table (default)")
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    group = (args.group or os.environ.get("MU2EDAQ_DISCOVERY_GROUP")
             or cfg.get("group") or protocol.GROUP)
    port = int(args.port or os.environ.get("MU2EDAQ_DISCOVERY_PORT")
               or cfg.get("port") or protocol.PORT)
    timeout = float(args.timeout or os.environ.get("MU2EDAQ_DISCOVERY_TIMEOUT")
                    or cfg.get("timeout") or 2.0)

    try:
        results = discover(
            filter=_parse_filter(args.filter), timeout=timeout,
            retries=args.retries, group=group, port=port,
            interface=args.interface,
        )
    except protocol.ProtocolError as exc:
        sys.exit("error: %s" % exc)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if not results:
            print("No services found.")
            return 0
        cols = ("name", "app", "host", "port", "id", "started")
        widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in results))
                  for c in cols}
        header = "  ".join(c.upper().ljust(widths[c]) for c in cols)
        print(header)
        print("-" * len(header))
        for r in results:
            print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
