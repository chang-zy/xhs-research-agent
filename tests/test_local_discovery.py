from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from xhs.local_discovery import browse_local_accounts, unique_accounts_from_feeds
from xhs.types import Feed


def _feed(feed_id: str, user_id: str, nickname: str, title: str = "样本笔记") -> Feed:
    return Feed.from_dict(
        {
            "id": feed_id,
            "xsecToken": f"token-{feed_id}",
            "modelType": "note",
            "noteCard": {
                "type": "normal",
                "displayTitle": title,
                "user": {"userId": user_id, "nickname": nickname},
                "interactInfo": {},
            },
        }
    )


def test_unique_accounts_deduplicates_and_ignores_cards_without_users() -> None:
    accounts = unique_accounts_from_feeds(
        [
            _feed("a", "u1", "小红"),
            _feed("b", "u1", "小红"),
            _feed("c", "u2", "小绿"),
            _feed("d", "", ""),
        ],
        30,
    )
    assert [item["userId"] for item in accounts] == ["u1", "u2"]
    assert accounts[0]["sampleNote"]["feedId"] == "a"


@pytest.mark.parametrize("scope", ["不限", "北京"])
def test_browse_local_rejects_non_local_scope(scope: str) -> None:
    with pytest.raises(ValueError, match="本地范围"):
        browse_local_accounts(None, "测试", scope=scope)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, 101])
def test_browse_local_rejects_out_of_range_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="--limit"):
        browse_local_accounts(None, "测试", limit=limit)  # type: ignore[arg-type]
