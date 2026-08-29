"""基于小红书当前浏览器会话的本地内容发现。"""

from __future__ import annotations

from .cdp import Page
from .search import search_feeds
from .types import Feed, FilterOption

_ALLOWED_SCOPES = {"同城", "附近"}


def _account_from_feed(feed: Feed) -> dict | None:
    """将一条公开笔记压缩为账号及其首条样本笔记。"""
    item = feed.to_dict()
    user = item.get("user") or {}
    user_id = str(user.get("userId") or "").strip()
    nickname = str(user.get("nickname") or "").strip()
    # 热搜推荐等非笔记卡片没有稳定账号，不应混进账号发现结果。
    if not user_id or not nickname:
        return None

    sample = {
        "feedId": item["id"],
        "xsecToken": item["xsecToken"],
        "title": item.get("displayTitle", ""),
        "type": item.get("type", ""),
        "interactInfo": item.get("interactInfo", {}),
    }
    if item.get("cover"):
        sample["cover"] = item["cover"]
    if item.get("video"):
        sample["video"] = item["video"]
    return {"userId": user_id, "nickname": nickname, "sampleNote": sample}


def unique_accounts_from_feeds(feeds: list[Feed], limit: int) -> list[dict]:
    """按账号去重，保留其在当前结果中的首条样本笔记。"""
    accounts: list[dict] = []
    seen_user_ids: set[str] = set()
    for feed in feeds:
        account = _account_from_feed(feed)
        if not account or account["userId"] in seen_user_ids:
            continue
        seen_user_ids.add(account["userId"])
        accounts.append(account)
        if len(accounts) >= limit:
            break
    return accounts


def browse_local_accounts(
    page: Page,
    keyword: str,
    *,
    scope: str = "同城",
    limit: int = 30,
    sort_by: str = "综合",
) -> dict:
    """以小红书当前会话的本地筛选浏览并返回去重的公开账号。"""
    if scope not in _ALLOWED_SCOPES:
        choices = "、".join(sorted(_ALLOWED_SCOPES))
        raise ValueError(f"本地范围必须是 {choices}，实际为: {scope}")
    if not 1 <= limit <= 100:
        raise ValueError("--limit 必须在 1 到 100 之间")

    feeds = search_feeds(page, keyword, FilterOption(sort_by=sort_by, location=scope))
    accounts = unique_accounts_from_feeds(feeds, limit)
    return {
        "keyword": keyword,
        "localContext": {
            "mode": scope,
            "source": "小红书当前浏览器会话自动定位",
            "city": None,
            "cityStatus": "已应用本地筛选；页面未暴露可可靠读取的城市名称。",
        },
        "accounts": accounts,
        "count": len(accounts),
        "requestedLimit": limit,
        "warning": (
            "结果仅为关键词命中的公开账号，未验证账号主体的身份、年龄、性别或外貌；"
            "本地范围由小红书当前会话决定，不能视为精确位置。"
        ),
    }
