"""Wire protocol for mu2edaq-discovery.

UDP multicast query/response. All messages are single UTF-8 JSON
datagrams no larger than MAX_DATAGRAM bytes.

Query (client -> multicast GROUP:PORT):
    {"proto": "mu2edaq-discovery/1", "type": "DISCOVER",
     "qid": "<uuid4>", "filter": {"app": "vnc"}}

Response (responder -> unicast back to the query source):
    {"proto": "mu2edaq-discovery/1", "type": "ANNOUNCE",
     "qid": "<echoed>", "id": "<stable uuid4>", "name": ..., "app": ...,
     "host": ..., "port": ..., "scheme": ..., "version": ..., "pid": ...,
     "started": "<ISO8601 UTC>", "meta": {...}}

A periodic ANNOUNCE (no qid) may also be multicast to the group for
passive listeners.
"""

import fnmatch
import json
import os
import socket
import uuid
from datetime import datetime, timezone

PROTO = "mu2edaq-discovery/1"
GROUP = "239.255.42.99"
PORT = 28999
MAX_DATAGRAM = 1400

# Filter keys that may appear in a DISCOVER message; values are
# fnmatch-style globs matched against the corresponding ANNOUNCE fields.
FILTER_KEYS = ("app", "name", "host")


class ProtocolError(ValueError):
    pass


def build_query(filter=None, qid=None):
    """Return a DISCOVER message dict."""
    msg = {"proto": PROTO, "type": "DISCOVER", "qid": qid or str(uuid.uuid4())}
    if filter:
        bad = set(filter) - set(FILTER_KEYS)
        if bad:
            raise ProtocolError("unsupported filter keys: %s" % ", ".join(sorted(bad)))
        msg["filter"] = dict(filter)
    return msg


def build_announce(name, app, port, instance_id, qid=None, host=None,
                   scheme=None, version=None, started=None, meta=None):
    """Return an ANNOUNCE message dict."""
    msg = {
        "proto": PROTO,
        "type": "ANNOUNCE",
        "id": instance_id,
        "name": name,
        "app": app,
        "host": host or socket.getfqdn(),
        "port": int(port),
        "scheme": scheme or app,
        "version": version or "0",
        "pid": os.getpid(),
        "started": started or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if qid is not None:
        msg["qid"] = qid
    if meta:
        msg["meta"] = dict(meta)
    return msg


def encode(msg):
    """Serialize a message dict to datagram bytes."""
    data = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_DATAGRAM:
        raise ProtocolError("message exceeds %d bytes" % MAX_DATAGRAM)
    return data


def decode(data):
    """Parse datagram bytes into a message dict, or raise ProtocolError."""
    if len(data) > MAX_DATAGRAM:
        raise ProtocolError("datagram exceeds %d bytes" % MAX_DATAGRAM)
    try:
        msg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("malformed datagram: %s" % exc)
    if not isinstance(msg, dict):
        raise ProtocolError("message is not a JSON object")
    if msg.get("proto") != PROTO:
        raise ProtocolError("unknown protocol: %r" % msg.get("proto"))
    if msg.get("type") not in ("DISCOVER", "ANNOUNCE"):
        raise ProtocolError("unknown message type: %r" % msg.get("type"))
    return msg


def matches_filter(announce, filter):
    """True if an ANNOUNCE message satisfies a DISCOVER filter."""
    if not filter:
        return True
    for key, pattern in filter.items():
        if key not in FILTER_KEYS:
            return False
        value = str(announce.get(key, ""))
        if not fnmatch.fnmatch(value, str(pattern)):
            return False
    return True
