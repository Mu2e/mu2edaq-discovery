"""mu2edaq-discover-gui: a lightweight Qt browser for discoverable resources.

Probes the network with the same DISCOVER query the CLI uses and shows
every ANNOUNCE reply in a sortable table. Instances of the same
resource class (the ``app`` field) are grouped under a class row;
resources that claim the same host and port are flagged in red.

Configuration precedence: command line > environment > config file >
defaults, matching mu2edaq-discover(1).
"""

import argparse
import json
import os
import sys

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    QT_API = "PyQt6"
except ImportError:  # pragma: no cover - exercised only on PySide-only hosts
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        QT_API = "PySide6"
    except ImportError:
        sys.exit(
            "error: a Qt binding is required for the GUI "
            "(pip install 'mu2edaq-discovery[gui]')"
        )

from . import protocol
from .client import discover

# Fields every ANNOUNCE carries, in display order. Anything else the
# responder publishes (including meta.* keys) is appended as a column
# discovered at runtime, so new parameters need no code change here.
CORE_FIELDS = ("name", "app", "host", "port", "scheme", "version",
               "pid", "started", "id")

# Fields that sort numerically rather than lexically.
NUMERIC_FIELDS = ("port", "pid")

CONFLICT_COLOR = QtGui.QColor(200, 30, 30)
APP_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "assets", "mu2edaq-discovery.png"
)


def application_icon():
    """Return the packaged application icon."""
    return QtGui.QIcon(APP_ICON_PATH)


def flatten(record):
    """Flatten an ANNOUNCE dict to {column: string value}.

    ``meta`` is expanded to ``meta.<key>`` columns; the protocol
    envelope fields are dropped since they are identical for every row.
    """
    flat = {}
    for key, value in record.items():
        if key in ("proto", "type", "qid"):
            continue
        if key == "meta" and isinstance(value, dict):
            for mkey, mvalue in value.items():
                flat["meta.%s" % mkey] = _as_text(mvalue)
        else:
            flat[key] = _as_text(value)
    return flat


def _as_text(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return "" if value is None else str(value)


def columns_for(records):
    """Return the column order for a result set: core fields first."""
    cols = [c for c in CORE_FIELDS]
    extra = set()
    for record in records:
        extra.update(flatten(record))
    for col in sorted(extra - set(cols)):
        cols.append(col)
    return cols


def conflict_keys(records):
    """Return the set of (host, port) pairs claimed by more than one resource."""
    seen = {}
    for record in records:
        key = (str(record.get("host", "")).lower(), record.get("port"))
        seen.setdefault(key, set()).add(record.get("id"))
    return {key for key, ids in seen.items() if len(ids) > 1}


def record_text(record, columns):
    """Plain text rendering of one record, one 'field: value' per line."""
    flat = flatten(record)
    width = max((len(c) for c in columns if c in flat), default=0)
    lines = []
    for col in columns:
        if col in flat:
            lines.append("%s : %s" % (col.ljust(width), flat[col]))
    return "\n".join(lines)


def record_json(record):
    """Pretty JSON rendering of one record."""
    return json.dumps(record, indent=2, sort_keys=True)


class _Item(QtWidgets.QTreeWidgetItem):
    """Tree item that sorts numeric columns by value, not by string."""

    def __init__(self, columns, record=None):
        super().__init__()
        self._columns = columns
        self.record = record

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        name = self._columns[column] if column < len(self._columns) else ""
        mine, theirs = self.text(column), other.text(column)
        if name in NUMERIC_FIELDS:
            try:
                return int(mine or -1) < int(theirs or -1)
            except ValueError:
                pass
        return mine.lower() < theirs.lower()


class DiscoveryWorker(QtCore.QThread):
    """Runs a blocking discover() off the UI thread."""

    finished_ok = QtCore.pyqtSignal(list) if QT_API == "PyQt6" else QtCore.Signal(list)
    failed = QtCore.pyqtSignal(str) if QT_API == "PyQt6" else QtCore.Signal(str)

    def __init__(self, options, filter=None, parent=None):
        super().__init__(parent)
        self.options = options
        self.filter = filter

    def run(self):
        try:
            results = discover(
                filter=self.filter,
                timeout=self.options["timeout"],
                retries=self.options["retries"],
                group=self.options["group"],
                port=self.options["port"],
                interface=self.options["interface"],
            )
        except Exception as exc:  # network/protocol errors reach the status bar
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(results)


class DiscoveryWindow(QtWidgets.QMainWindow):
    """Main window: toolbar, grouped resource tree, status bar."""

    def __init__(self, options):
        super().__init__()
        self.options = options
        self.columns = list(CORE_FIELDS)
        self.records = []
        self.worker = None

        self.setWindowTitle("Mu2e DAQ Resource Discovery")
        self.setWindowIcon(application_icon())
        self.resize(1100, 600)

        self._build_toolbar()

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(len(self.columns))
        self.tree.setHeaderLabels([c.upper() for c in self.columns])
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.header().setSectionsMovable(True)
        self.tree.header().setStretchLastSection(False)
        self.setCentralWidget(self.tree)

        self.status = self.statusBar()
        self.status.showMessage("Ready.")

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)

        self._set_empty("Probing for resources...")
        QtCore.QTimer.singleShot(0, self.refresh)

    # -- construction ------------------------------------------------------

    def _build_toolbar(self):
        bar = self.addToolBar("Discovery")
        bar.setMovable(False)

        self.refresh_action = QtGui.QAction("&Probe", self)
        self.refresh_action.setShortcut(QtGui.QKeySequence.StandardKey.Refresh)
        self.refresh_action.setStatusTip("Send a DISCOVER query now")
        self.refresh_action.triggered.connect(self.refresh)
        bar.addAction(self.refresh_action)
        bar.addSeparator()

        bar.addWidget(QtWidgets.QLabel(" Filter: "))
        self.filter_key = QtWidgets.QComboBox()
        self.filter_key.addItems(protocol.FILTER_KEYS)
        bar.addWidget(self.filter_key)
        self.filter_value = QtWidgets.QLineEdit()
        self.filter_value.setPlaceholderText("glob, e.g. vnc or mu2edaq*")
        self.filter_value.setMaximumWidth(220)
        self.filter_value.returnPressed.connect(self.refresh)
        bar.addWidget(self.filter_value)
        bar.addSeparator()

        self.auto_check = QtWidgets.QCheckBox("Auto")
        self.auto_check.setToolTip("Re-probe periodically")
        self.auto_check.toggled.connect(self._toggle_auto)
        bar.addWidget(self.auto_check)
        self.auto_interval = QtWidgets.QSpinBox()
        self.auto_interval.setRange(2, 3600)
        self.auto_interval.setValue(int(self.options["interval"]))
        self.auto_interval.setSuffix(" s")
        self.auto_interval.valueChanged.connect(self._toggle_auto)
        bar.addWidget(self.auto_interval)
        bar.addSeparator()

        expand = QtGui.QAction("&Expand All", self)
        expand.triggered.connect(lambda: self.tree.expandAll())
        bar.addAction(expand)
        collapse = QtGui.QAction("&Collapse All", self)
        collapse.triggered.connect(lambda: self.tree.collapseAll())
        bar.addAction(collapse)

        if self.options["interval_on"]:
            self.auto_check.setChecked(True)

    # -- probing -----------------------------------------------------------

    def _current_filter(self):
        value = self.filter_value.text().strip()
        if not value:
            return None
        return {self.filter_key.currentText(): value}

    def refresh(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.refresh_action.setEnabled(False)
        self.status.showMessage(
            "Probing %s:%d for %.1f s..." % (self.options["group"],
                                             self.options["port"],
                                             self.options["timeout"]))
        self.worker = DiscoveryWorker(self.options, self._current_filter(), self)
        self.worker.finished_ok.connect(self._on_results)
        self.worker.failed.connect(self._on_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(lambda: setattr(self, "worker", None))
        self.worker.start()

    def _toggle_auto(self):
        if self.auto_check.isChecked():
            self.timer.start(self.auto_interval.value() * 1000)
        else:
            self.timer.stop()

    def _on_error(self, message):
        self.refresh_action.setEnabled(True)
        self._set_empty("Discovery failed")
        self.status.showMessage("Error: %s" % message)

    def _on_results(self, records):
        self.refresh_action.setEnabled(True)
        self.records = records
        self.populate(records)

    # -- table -------------------------------------------------------------

    def populate(self, records):
        expanded = {self.tree.topLevelItem(i).text(0)
                    for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        sort_column = self.tree.sortColumn()
        sort_order = self.tree.header().sortIndicatorOrder()

        self.tree.setSortingEnabled(False)
        self.tree.clear()

        if not records:
            self.columns = list(CORE_FIELDS)
            self._reset_header()
            self._set_empty("No resources found")
            self.status.showMessage(
                "No resources responded on %s:%d." %
                (self.options["group"], self.options["port"]))
            return

        self.columns = columns_for(records)
        self._reset_header()
        conflicts = conflict_keys(records)

        groups = {}
        for record in records:
            groups.setdefault(record.get("app") or "(unknown)", []).append(record)

        conflicted = 0
        for app in sorted(groups):
            members = groups[app]
            parent = _Item(self.columns)
            parent.setText(0, "%s  (%d)" % (app, len(members)))
            parent.setText(1, app)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFirstColumnSpanned(False)
            self.tree.addTopLevelItem(parent)

            for record in members:
                flat = flatten(record)
                item = _Item(self.columns, record)
                for index, col in enumerate(self.columns):
                    item.setText(index, flat.get(col, ""))
                key = (str(record.get("host", "")).lower(), record.get("port"))
                if key in conflicts:
                    conflicted += 1
                    tip = ("Conflict: %s:%s is claimed by more than one resource"
                           % (record.get("host", ""), record.get("port", "")))
                    for index in range(len(self.columns)):
                        item.setForeground(index, CONFLICT_COLOR)
                        item.setToolTip(index, tip)
                    bold = item.font(0)
                    bold.setBold(True)
                    item.setFont(0, bold)
                parent.addChild(item)

            parent.setExpanded(not expanded or parent.text(0) in expanded)

        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(min(sort_column, len(self.columns) - 1), sort_order)
        for index in range(len(self.columns)):
            self.tree.resizeColumnToContents(index)

        message = "%d resource%s in %d class%s." % (
            len(records), "" if len(records) == 1 else "s",
            len(groups), "" if len(groups) == 1 else "es")
        if conflicted:
            message += "  %d host:port conflict%s flagged in red." % (
                conflicted, "" if conflicted == 1 else "s")
        self.status.showMessage(message)

    def _reset_header(self):
        self.tree.setColumnCount(len(self.columns))
        self.tree.setHeaderLabels([c.upper() for c in self.columns])

    def _set_empty(self, text):
        """Show a single placeholder row (no resources / probing / error)."""
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        item = _Item(self.columns)
        item.setText(0, text)
        item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
        font = item.font(0)
        font.setItalic(True)
        item.setFont(0, font)
        item.setForeground(0, QtGui.QColor(120, 120, 120))
        self.tree.addTopLevelItem(item)
        item.setFirstColumnSpanned(True)
        self.tree.setSortingEnabled(True)

    # -- context menu ------------------------------------------------------

    def _show_context_menu(self, point):
        menu = self.build_context_menu(self.tree.itemAt(point),
                                       self.tree.columnAt(point.x()))
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def build_context_menu(self, item, column):
        """Build the per-row context menu (separated out so tests can drive it)."""
        menu = QtWidgets.QMenu(self)

        record = getattr(item, "record", None) if item is not None else None
        if record is not None:
            text_action = menu.addAction("Copy Record (Plain Text)")
            text_action.triggered.connect(
                lambda: self._copy(record_text(record, self.columns),
                                   "record as text"))
            json_action = menu.addAction("Copy Record (JSON)")
            json_action.triggered.connect(
                lambda: self._copy(record_json(record), "record as JSON"))

            flat = flatten(record)
            if 0 <= column < len(self.columns):
                name = self.columns[column]
                if name in flat:
                    cell = menu.addAction('Copy "%s" (%s)' % (name, _elide(flat[name])))
                    cell.triggered.connect(
                        lambda: self._copy(flat[name], "field %s" % name))

            field_menu = menu.addMenu("Copy Field")
            for col in self.columns:
                if col not in flat:
                    continue
                action = field_menu.addAction("%s = %s" % (col, _elide(flat[col])))
                action.triggered.connect(
                    lambda _checked=False, c=col: self._copy(flat[c],
                                                             "field %s" % c))
            menu.addSeparator()

        elif item is not None and item.childCount():
            # A class row: offer the whole group.
            members = [item.child(i).record for i in range(item.childCount())
                       if getattr(item.child(i), "record", None) is not None]
            group_text = menu.addAction("Copy Class (Plain Text)")
            group_text.triggered.connect(
                lambda: self._copy(
                    "\n\n".join(record_text(r, self.columns) for r in members),
                    "%d records as text" % len(members)))
            group_json = menu.addAction("Copy Class (JSON)")
            group_json.triggered.connect(
                lambda: self._copy(json.dumps(members, indent=2, sort_keys=True),
                                   "%d records as JSON" % len(members)))
            menu.addSeparator()

        all_text = menu.addAction("Copy All Resources (Plain Text)")
        all_text.setEnabled(bool(self.records))
        all_text.triggered.connect(
            lambda: self._copy(
                "\n\n".join(record_text(r, self.columns) for r in self.records),
                "all records as text"))
        all_json = menu.addAction("Copy All Resources (JSON)")
        all_json.setEnabled(bool(self.records))
        all_json.triggered.connect(
            lambda: self._copy(json.dumps(self.records, indent=2, sort_keys=True),
                               "all records as JSON"))
        menu.addSeparator()
        probe = menu.addAction("Probe Again")
        probe.triggered.connect(self.refresh)
        return menu

    def _copy(self, text, what):
        QtWidgets.QApplication.clipboard().setText(text)
        self.status.showMessage("Copied %s to the clipboard." % what, 4000)

    def closeEvent(self, event):
        self.timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)


def _elide(text, limit=40):
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mu2edaq-discover-gui",
        description="Graphical browser for discoverable Mu2e DAQ resources.",
    )
    parser.add_argument("--filter", metavar="KEY=GLOB", default=None,
                        help="initial filter, e.g. --filter app=vnc (keys: %s)"
                             % ", ".join(protocol.FILTER_KEYS))
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds to wait for replies (default 2.0)")
    parser.add_argument("--retries", type=int, default=2,
                        help="number of query transmissions (default 2)")
    parser.add_argument("--group", default=None, help="multicast group")
    parser.add_argument("--port", type=int, default=None, help="UDP port")
    parser.add_argument("--interface", default=None,
                        help="local interface IP for multicast")
    parser.add_argument("--interval", type=float, default=None,
                        help="auto-probe interval in seconds (default 10)")
    parser.add_argument("--auto", action="store_true",
                        help="start with auto-probing enabled")
    parser.add_argument("--config", default=os.environ.get("MU2EDAQ_DISCOVERY_CONFIG"),
                        help="YAML config file")
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    options = {
        "group": (args.group or os.environ.get("MU2EDAQ_DISCOVERY_GROUP")
                  or cfg.get("group") or protocol.GROUP),
        "port": int(args.port or os.environ.get("MU2EDAQ_DISCOVERY_PORT")
                    or cfg.get("port") or protocol.PORT),
        "timeout": float(args.timeout or os.environ.get("MU2EDAQ_DISCOVERY_TIMEOUT")
                         or cfg.get("timeout") or 2.0),
        "retries": args.retries,
        "interface": args.interface,
        "interval": float(args.interval or os.environ.get("MU2EDAQ_DISCOVERY_INTERVAL")
                          or cfg.get("interval") or 10.0),
        "interval_on": args.auto,
    }

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("mu2edaq-discover-gui")
    app.setWindowIcon(application_icon())
    window = DiscoveryWindow(options)
    if args.filter:
        if "=" not in args.filter:
            sys.exit("error: --filter takes key=glob (keys: %s)"
                     % ", ".join(protocol.FILTER_KEYS))
        key, _, value = args.filter.partition("=")
        key = key.strip()
        if key not in protocol.FILTER_KEYS:
            sys.exit("error: unsupported filter key %r (keys: %s)"
                     % (key, ", ".join(protocol.FILTER_KEYS)))
        window.filter_key.setCurrentText(key)
        window.filter_value.setText(value.strip())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
