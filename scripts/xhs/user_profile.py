"""用户主页，对应 Go xiaohongshu/user_profile.go。"""

from __future__ import annotations

import json
import logging
import time

from .cdp import Page
from .human import get_scroll_interval
from .types import Feed, UserBasicInfo, UserInteraction, UserProfileResponse
from .urls import make_user_profile_url

logger = logging.getLogger(__name__)

# 提取用户数据的 JS
_EXTRACT_USER_DATA_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.user &&
        window.__INITIAL_STATE__.user.userPageData) {
        const userPageData = window.__INITIAL_STATE__.user.userPageData;
        const data = userPageData.value !== undefined ? userPageData.value : userPageData._value;
        if (data) {
            return JSON.stringify(data);
        }
    }
    return "";
})()
"""

_EXTRACT_USER_NOTES_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.user &&
        window.__INITIAL_STATE__.user.notes) {
        const notes = window.__INITIAL_STATE__.user.notes;
        const data = notes.value !== undefined ? notes.value : notes._value;
        if (data) {
            return JSON.stringify(data);
        }
    }
    return "";
})()
"""

_PROFILE_SCROLL_STATE_JS = r"""
(() => {
    const root = document.documentElement;
    const body = document.body;
    const scrollTop = window.pageYOffset || root.scrollTop || body.scrollTop || 0;
    const viewportHeight = window.innerHeight || root.clientHeight || 0;
    const scrollHeight = Math.max(
        body ? body.scrollHeight : 0,
        root ? root.scrollHeight : 0
    );
    const endPatterns = [/没有更多/, /已经到底/, /到底啦/, /暂无更多/];
    const endVisible = Array.from(document.querySelectorAll('div,span,p'))
        .some((el) => {
            const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
            if (!text || text.length > 30 || !endPatterns.some((p) => p.test(text))) {
                return false;
            }
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                style.display !== 'none' && style.visibility !== 'hidden';
        });
    const loadingVisible = Array.from(
        document.querySelectorAll('.loading,.loading-container,[class*="loading"]')
    ).some((el) => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 &&
            style.display !== 'none' && style.visibility !== 'hidden';
    });
    return {
        scrollTop,
        viewportHeight,
        scrollHeight,
        atBottom: scrollTop + viewportHeight >= scrollHeight - 100,
        endVisible,
        loadingVisible,
    };
})()
"""


def get_user_profile(
    page: Page,
    user_id: str,
    xsec_token: str,
    *,
    load_all_notes: bool = False,
    max_note_items: int = 0,
    scroll_speed: str = "normal",
    max_scroll_rounds: int = 120,
    stable_rounds: int = 4,
) -> UserProfileResponse:
    """获取用户主页信息及帖子。

    Args:
        page: CDP 页面对象。
        user_id: 用户 ID。
        xsec_token: xsec_token。

    Raises:
        RuntimeError: 数据提取失败。
    """
    url = make_user_profile_url(user_id, xsec_token)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()

    if max_note_items < 0:
        raise ValueError("max_note_items 不能小于 0")
    if max_scroll_rounds <= 0:
        raise ValueError("max_scroll_rounds 必须大于 0")
    if stable_rounds <= 0:
        raise ValueError("stable_rounds 必须大于 0")
    if scroll_speed not in {"slow", "normal", "fast"}:
        raise ValueError("scroll_speed 必须是 slow、normal 或 fast")

    profile = _extract_user_profile_data(page)
    if not load_all_notes:
        profile.note_load_status = {
            "requestedAll": False,
            "loaded": len(profile.feeds),
            "complete": False,
            "reason": "initial_page_only",
            "scrollRounds": 0,
        }
        return profile

    profile.feeds, profile.note_load_status = _load_all_user_notes(
        page,
        profile.feeds,
        max_note_items=max_note_items,
        scroll_speed=scroll_speed,
        max_scroll_rounds=max_scroll_rounds,
        stable_rounds=stable_rounds,
    )
    return profile


def _feed_key(feed: Feed) -> str:
    """生成稳定去重键；正常情况下帖子 ID 总是存在。"""
    if feed.id:
        return f"id:{feed.id}"
    return "fallback:{}:{}:{}".format(
        feed.xsec_token,
        feed.note_card.display_title,
        feed.note_card.user.user_id,
    )


def _merge_unique_feeds(target: list[Feed], incoming: list[Feed]) -> int:
    """按帖子 ID 合并并保持首次出现顺序，返回新增数量。"""
    known = {_feed_key(feed) for feed in target}
    added = 0
    for feed in incoming:
        key = _feed_key(feed)
        if key in known:
            continue
        known.add(key)
        target.append(feed)
        added += 1
    return added


def _extract_user_notes(page: Page) -> list[Feed] | None:
    """提取当前已加载的主页帖子快照。"""
    notes_result = page.evaluate(_EXTRACT_USER_NOTES_JS)
    if not notes_result:
        return None
    notes_feeds_raw = json.loads(notes_result)
    feeds: list[Feed] = []
    for feed_group in notes_feeds_raw:
        if isinstance(feed_group, list):
            feeds.extend(Feed.from_dict(feed) for feed in feed_group)
        elif isinstance(feed_group, dict):
            feeds.append(Feed.from_dict(feed_group))
    return feeds


def _load_all_user_notes(
    page: Page,
    initial_feeds: list[Feed],
    *,
    max_note_items: int,
    scroll_speed: str,
    max_scroll_rounds: int,
    stable_rounds: int,
) -> tuple[list[Feed], dict]:
    """滚动用户主页，合并懒加载帖子并返回完整性状态。"""
    feeds: list[Feed] = []
    _merge_unique_feeds(feeds, initial_feeds)
    if max_note_items and len(feeds) >= max_note_items:
        return feeds[:max_note_items], {
            "requestedAll": True,
            "loaded": max_note_items,
            "complete": False,
            "reason": "max_items_reached",
            "scrollRounds": 0,
        }

    stable_count = 0
    previous_state = page.evaluate(_PROFILE_SCROLL_STATE_JS) or {}
    last_state = previous_state

    for round_number in range(1, max_scroll_rounds + 1):
        page.scroll_to_bottom()
        time.sleep(get_scroll_interval(scroll_speed))

        snapshot = _extract_user_notes(page) or []
        added = _merge_unique_feeds(feeds, snapshot)
        state = page.evaluate(_PROFILE_SCROLL_STATE_JS) or {}

        # 页面显示加载动画时再给一次网络/渲染机会。
        if state.get("loadingVisible"):
            time.sleep(max(get_scroll_interval(scroll_speed), 0.5))
            added += _merge_unique_feeds(feeds, _extract_user_notes(page) or [])
            state = page.evaluate(_PROFILE_SCROLL_STATE_JS) or state

        if max_note_items and len(feeds) >= max_note_items:
            return feeds[:max_note_items], {
                "requestedAll": True,
                "loaded": max_note_items,
                "complete": False,
                "reason": "max_items_reached",
                "scrollRounds": round_number,
            }

        if state.get("endVisible"):
            return feeds, {
                "requestedAll": True,
                "loaded": len(feeds),
                "complete": True,
                "reason": "end_marker_detected",
                "completionConfidence": "confirmed",
                "scrollRounds": round_number,
            }

        height_unchanged = int(state.get("scrollHeight", 0)) <= int(
            previous_state.get("scrollHeight", 0)
        ) + 2
        stable_bottom = (
            added == 0
            and height_unchanged
            and bool(state.get("atBottom"))
        )
        stable_count = stable_count + 1 if stable_bottom else 0
        last_state = state
        previous_state = state

        if stable_count >= stable_rounds:
            return feeds, {
                "requestedAll": True,
                "loaded": len(feeds),
                "complete": True,
                "reason": "stable_bottom",
                "completionConfidence": "inferred",
                "stableRounds": stable_count,
                "scrollRounds": round_number,
            }

    return feeds, {
        "requestedAll": True,
        "loaded": len(feeds),
        "complete": False,
        "reason": "max_scroll_rounds_reached",
        "scrollRounds": max_scroll_rounds,
        "atBottom": bool(last_state.get("atBottom")),
    }


def _extract_user_profile_data(page: Page) -> UserProfileResponse:
    """从页面提取用户资料数据。"""
    # 等待 __INITIAL_STATE__
    _wait_for_initial_state(page)

    # 提取用户信息
    user_data_result = page.evaluate(_EXTRACT_USER_DATA_JS)
    if not user_data_result:
        raise RuntimeError("user.userPageData.value not found in __INITIAL_STATE__")

    # 提取用户帖子
    feeds = _extract_user_notes(page)
    if feeds is None:
        raise RuntimeError("user.notes.value not found in __INITIAL_STATE__")

    # 解析用户信息
    user_page_data = json.loads(user_data_result)
    basic_info = UserBasicInfo.from_dict(user_page_data.get("basicInfo", {}))
    interactions = [UserInteraction.from_dict(i) for i in user_page_data.get("interactions", [])]

    return UserProfileResponse(
        user_basic_info=basic_info,
        interactions=interactions,
        feeds=feeds,
    )


def _wait_for_initial_state(page: Page, timeout: float = 10.0) -> None:
    """等待 __INITIAL_STATE__ 就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = page.evaluate("window.__INITIAL_STATE__ !== undefined")
        if ready:
            return
        time.sleep(0.5)
    logger.warning("等待 __INITIAL_STATE__ 超时")
