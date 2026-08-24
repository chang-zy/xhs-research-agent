"""用户主页帖子完整加载测试。"""

from __future__ import annotations

import json

from scripts.xhs import user_profile


def _feed(feed_id: str) -> dict:
    return {
        "id": feed_id,
        "xsecToken": f"token-{feed_id}",
        "noteCard": {"displayTitle": f"帖子 {feed_id}"},
    }


class FakePage:
    def __init__(self, snapshots: list[list[dict]], states: list[dict]) -> None:
        self.snapshots = snapshots
        self.states = states
        self.index = 0

    def navigate(self, _url: str) -> None:
        pass

    def wait_for_load(self) -> None:
        pass

    def wait_dom_stable(self) -> None:
        pass

    def scroll_to_bottom(self) -> None:
        self.index = min(self.index + 1, len(self.snapshots) - 1)

    def evaluate(self, expression: str):
        if "userPageData" in expression:
            return json.dumps(
                {
                    "basicInfo": {"nickname": "测试用户"},
                    "interactions": [],
                }
            )
        if "window.__INITIAL_STATE__.user.notes" in expression:
            return json.dumps([self.snapshots[self.index]])
        if "endPatterns" in expression:
            return self.states[min(self.index, len(self.states) - 1)]
        if "window.__INITIAL_STATE__ !== undefined" in expression:
            return True
        raise AssertionError(f"未处理的脚本: {expression[:80]}")


def test_load_all_notes_scrolls_deduplicates_and_confirms_end(monkeypatch) -> None:
    page = FakePage(
        snapshots=[
            [_feed("1"), _feed("2")],
            [_feed("1"), _feed("2"), _feed("3")],
            [_feed("2"), _feed("3"), _feed("4")],
        ],
        states=[
            {"scrollHeight": 1000, "atBottom": False},
            {"scrollHeight": 1500, "atBottom": False},
            {"scrollHeight": 1500, "atBottom": True, "endVisible": True},
        ],
    )
    monkeypatch.setattr(user_profile, "get_scroll_interval", lambda _speed: 0)

    profile = user_profile.get_user_profile(
        page,
        "user-1",
        "token-1",
        load_all_notes=True,
    )

    assert [feed.id for feed in profile.feeds] == ["1", "2", "3", "4"]
    assert profile.note_load_status == {
        "requestedAll": True,
        "loaded": 4,
        "complete": True,
        "reason": "end_marker_detected",
        "completionConfidence": "confirmed",
        "scrollRounds": 2,
    }


def test_load_all_notes_respects_item_limit(monkeypatch) -> None:
    page = FakePage(
        snapshots=[
            [_feed("1"), _feed("2")],
            [_feed("1"), _feed("2"), _feed("3"), _feed("4")],
        ],
        states=[
            {"scrollHeight": 1000, "atBottom": False},
            {"scrollHeight": 1500, "atBottom": False},
        ],
    )
    monkeypatch.setattr(user_profile, "get_scroll_interval", lambda _speed: 0)

    profile = user_profile.get_user_profile(
        page,
        "user-1",
        "token-1",
        load_all_notes=True,
        max_note_items=3,
    )

    assert [feed.id for feed in profile.feeds] == ["1", "2", "3"]
    assert profile.note_load_status["complete"] is False
    assert profile.note_load_status["reason"] == "max_items_reached"
    assert profile.note_load_status["loaded"] == 3


def test_initial_page_is_explicitly_marked_incomplete() -> None:
    page = FakePage(
        snapshots=[[_feed("1"), _feed("2")]],
        states=[{"scrollHeight": 1000, "atBottom": False}],
    )

    profile = user_profile.get_user_profile(page, "user-1", "token-1")

    assert profile.note_load_status["complete"] is False
    assert profile.note_load_status["reason"] == "initial_page_only"


def test_stable_bottom_marks_inferred_completion(monkeypatch) -> None:
    page = FakePage(
        snapshots=[[_feed("1")], [_feed("1")]],
        states=[
            {"scrollHeight": 1000, "atBottom": True, "loadingVisible": True},
            {"scrollHeight": 1000, "atBottom": True, "loadingVisible": True},
        ],
    )
    monkeypatch.setattr(user_profile, "get_scroll_interval", lambda _speed: 0)

    profile = user_profile.get_user_profile(
        page,
        "user-1",
        "token-1",
        load_all_notes=True,
        stable_rounds=2,
    )

    assert profile.note_load_status["complete"] is True
    assert profile.note_load_status["reason"] == "stable_bottom"
    assert profile.note_load_status["completionConfidence"] == "inferred"


def test_empty_profile_can_complete(monkeypatch) -> None:
    page = FakePage(
        snapshots=[[]],
        states=[{"scrollHeight": 1000, "atBottom": True, "endVisible": True}],
    )
    monkeypatch.setattr(user_profile, "get_scroll_interval", lambda _speed: 0)

    profile = user_profile.get_user_profile(
        page,
        "user-1",
        "token-1",
        load_all_notes=True,
    )

    assert profile.feeds == []
    assert profile.note_load_status["complete"] is True
    assert profile.note_load_status["loaded"] == 0
