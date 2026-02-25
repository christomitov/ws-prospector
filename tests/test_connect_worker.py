"""Tests for connect action detection logic."""

from linkedin_leads.connect_worker import ConnectWorker


class _DummyStore:
    pass


def _worker() -> ConnectWorker:
    return ConnectWorker(user_data_dir="/tmp", store=_DummyStore())


def test_looks_like_connect_action_from_invite_aria_label():
    worker = _worker()
    assert worker._looks_like_connect_action("Invite Basil Y. to connect", "", "")


def test_looks_like_connect_action_from_text_only():
    worker = _worker()
    assert worker._looks_like_connect_action("", "Connect", "")


def test_looks_like_connect_action_from_invite_href():
    worker = _worker()
    assert worker._looks_like_connect_action("", "", "/preload/custom-invite/ACoA...")


def test_looks_like_connect_action_rejects_follow():
    worker = _worker()
    assert not worker._looks_like_connect_action("Follow Basil Y.", "Follow", "")


def test_looks_like_connect_action_rejects_pending():
    worker = _worker()
    assert not worker._looks_like_connect_action("Pending", "Pending", "")


def test_looks_like_connect_action_rejects_message():
    worker = _worker()
    assert not worker._looks_like_connect_action("Message Basil Y.", "Message", "")


def test_looks_like_connect_action_rejects_connections_word():
    worker = _worker()
    assert not worker._looks_like_connect_action("500+ connections", "Connections", "")
