"""Tests for the discovery GUI: table building, grouping, conflicts, copying.

Skipped automatically when no Qt binding is installed. Runs headless via
the offscreen platform plugin.
"""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6", reason="GUI tests need a Qt binding")

from PyQt6 import QtCore, QtWidgets  # noqa: E402

from mu2edaq_discovery import gui  # noqa: E402


def make_record(id, name, app, host, port, **extra):
    record = {
        "proto": "mu2edaq-discovery/1", "type": "ANNOUNCE", "qid": "q",
        "id": id, "name": name, "app": app, "host": host, "port": port,
        "scheme": app, "version": "1", "pid": 100,
        "started": "2026-01-01T00:00:00Z",
    }
    record.update(extra)
    return record


RECORDS = [
    make_record("a", "VNC one", "vnc", "mu2edaq01", 5901, meta={"user": "anorman"}),
    make_record("b", "VNC two", "vnc", "mu2edaq01", 5901),
    make_record("c", "Dashboard", "dashboard", "mu2edaq02", 8080,
                meta={"zmq_port": "5555"}),
]

OPTIONS = {"group": "239.255.42.99", "port": 28999, "timeout": 0.1,
           "retries": 1, "interface": None, "interval": 10.0,
           "interval_on": False}


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    win = gui.DiscoveryWindow(OPTIONS)
    yield win
    win.close()


# -- pure helpers ---------------------------------------------------------

def test_application_icon_is_packaged(qapp):
    # QIcon needs a live QApplication; without the fixture Qt aborts.
    assert os.path.isfile(gui.APP_ICON_PATH)
    assert not gui.application_icon().isNull()


def test_flatten_expands_meta_and_drops_envelope():
    flat = gui.flatten(RECORDS[0])
    assert flat["meta.user"] == "anorman"
    assert flat["port"] == "5901"
    assert "proto" not in flat and "type" not in flat and "qid" not in flat


def test_columns_core_first_then_discovered_parameters():
    cols = gui.columns_for(RECORDS)
    assert cols[:len(gui.CORE_FIELDS)] == list(gui.CORE_FIELDS)
    assert cols[len(gui.CORE_FIELDS):] == ["meta.user", "meta.zmq_port"]


def test_conflict_keys_finds_shared_host_port():
    assert gui.conflict_keys(RECORDS) == {("mu2edaq01", 5901)}


def test_conflict_keys_ignores_same_instance_seen_twice():
    assert gui.conflict_keys([RECORDS[0], dict(RECORDS[0])]) == set()


def test_record_text_and_json_round_trip():
    cols = gui.columns_for(RECORDS)
    text = gui.record_text(RECORDS[0], cols)
    assert "name      : VNC one" in text
    assert "meta.user : anorman" in text
    assert "proto" not in text
    assert json.loads(gui.record_json(RECORDS[0])) == RECORDS[0]


# -- table ----------------------------------------------------------------

def test_populate_groups_by_class(window):
    window.populate(RECORDS)
    assert window.tree.topLevelItemCount() == 2
    groups = {window.tree.topLevelItem(i).text(1): window.tree.topLevelItem(i)
              for i in range(2)}
    assert groups["vnc"].childCount() == 2
    assert groups["dashboard"].childCount() == 1
    assert "2 classes" in window.statusBar().currentMessage()


def test_conflicting_rows_are_red(window):
    window.populate(RECORDS)
    for i in range(window.tree.topLevelItemCount()):
        parent = window.tree.topLevelItem(i)
        for j in range(parent.childCount()):
            child = parent.child(j)
            red = child.foreground(0).color() == gui.CONFLICT_COLOR
            assert red == (child.record["host"] == "mu2edaq01")


def test_empty_result_shows_no_resources_row(window):
    window.populate([])
    assert window.tree.topLevelItemCount() == 1
    item = window.tree.topLevelItem(0)
    assert item.text(0) == "No resources found"
    assert getattr(item, "record", None) is None
    assert "No resources responded" in window.statusBar().currentMessage()


def test_window_starts_with_auto_refresh_enabled(qapp):
    options = dict(OPTIONS, interval_on=True)
    window = gui.DiscoveryWindow(options)
    try:
        assert window.timer.isActive()
        assert window.timer.interval() == 10000
    finally:
        window.close()


def test_port_column_sorts_numerically(window):
    records = [make_record("x", "a", "vnc", "h1", 9),
               make_record("y", "b", "vnc", "h2", 100)]
    window.populate(records)
    port_col = window.columns.index("port")
    window.tree.sortByColumn(port_col, QtCore.Qt.SortOrder.AscendingOrder)
    parent = window.tree.topLevelItem(0)
    assert [parent.child(i).text(port_col) for i in range(2)] == ["9", "100"]


# -- context menu ---------------------------------------------------------

def _actions(menu):
    return {a.text(): a for a in menu.actions()}


def trigger(menu, label):
    _actions(menu)[label].trigger()


def test_context_menu_copies_plain_text_record(window, qapp):
    window.populate(RECORDS)
    item = window.tree.topLevelItem(0).child(0)
    menu = window.build_context_menu(item, 0)
    trigger(menu, "Copy Record (Plain Text)")
    assert qapp.clipboard().text() == gui.record_text(item.record, window.columns)


def test_context_menu_copies_json_record(window, qapp):
    window.populate(RECORDS)
    item = window.tree.topLevelItem(0).child(0)
    menu = window.build_context_menu(item, 0)
    trigger(menu, "Copy Record (JSON)")
    assert json.loads(qapp.clipboard().text()) == item.record


def test_context_menu_copies_single_field(window, qapp):
    window.populate(RECORDS)
    item = window.tree.topLevelItem(0).child(0)
    host_col = window.columns.index("host")
    menu = window.build_context_menu(item, host_col)
    trigger(menu, 'Copy "host" (%s)' % item.record["host"])
    assert qapp.clipboard().text() == item.record["host"]


def test_copy_field_submenu_covers_every_published_parameter(window, qapp):
    window.populate(RECORDS)
    item = window.tree.topLevelItem(1).child(0)  # a vnc instance
    menu = window.build_context_menu(item, 0)
    submenu = _actions(menu)["Copy Field"].menu()
    labels = [a.text() for a in submenu.actions()]
    flat = gui.flatten(item.record)
    assert len(labels) == len(flat)
    port_action = next(a for a in submenu.actions() if a.text().startswith("port ="))
    port_action.trigger()
    assert qapp.clipboard().text() == str(item.record["port"])


def test_class_row_menu_copies_whole_group(window, qapp):
    window.populate(RECORDS)
    vnc = next(window.tree.topLevelItem(i) for i in range(2)
               if window.tree.topLevelItem(i).text(1) == "vnc")
    menu = window.build_context_menu(vnc, 0)
    trigger(menu, "Copy Class (JSON)")
    assert len(json.loads(qapp.clipboard().text())) == 2


def test_menu_on_empty_table_has_no_record_actions(window):
    window.populate([])
    menu = window.build_context_menu(window.tree.topLevelItem(0), 0)
    labels = _actions(menu)
    assert "Copy Record (JSON)" not in labels
    assert labels["Copy All Resources (JSON)"].isEnabled() is False
