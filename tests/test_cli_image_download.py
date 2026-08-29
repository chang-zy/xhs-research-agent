"""get-feed-detail 图片下载参数的轻量测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cli_module():
    cli_path = Path(__file__).parents[1] / "scripts" / "cli.py"
    spec = importlib.util.spec_from_file_location("xhs_cli", cli_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_get_feed_detail_accepts_image_download_options() -> None:
    cli = _load_cli_module()
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "get-feed-detail",
            "--feed-id",
            "feed-1",
            "--xsec-token",
            "token-1",
            "--download-images",
            "--image-dir",
            "/tmp/xhs-images/feed-1",
            "--max-images",
            "3",
        ]
    )

    assert args.download_images is True
    assert args.image_dir == "/tmp/xhs-images/feed-1"
    assert args.max_images == 3


def test_get_feed_detail_accepts_confirmed_video_preparation_options() -> None:
    cli = _load_cli_module()
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "get-feed-detail",
            "--feed-id",
            "feed-video-1",
            "--xsec-token",
            "token-1",
            "--prepare-video",
            "--confirm-video-understanding",
            "--video-dir",
            "/tmp/xhs-videos/feed-video-1",
            "--max-video-frames",
            "24",
        ]
    )

    assert args.prepare_video is True
    assert args.confirm_video_understanding is True
    assert args.video_dir == "/tmp/xhs-videos/feed-video-1"
    assert args.max_video_frames == 24


def test_user_profile_accepts_complete_note_loading_options() -> None:
    cli = _load_cli_module()
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "user-profile",
            "--user-id",
            "user-1",
            "--xsec-token",
            "token-1",
            "--load-all-notes",
            "--max-note-items",
            "50",
            "--scroll-speed",
            "slow",
            "--max-scroll-rounds",
            "80",
            "--stable-rounds",
            "5",
        ]
    )

    assert args.load_all_notes is True
    assert args.max_note_items == 50
    assert args.scroll_speed == "slow"
    assert args.max_scroll_rounds == 80
    assert args.stable_rounds == 5


def test_browse_local_defaults_to_session_based_same_city_scope() -> None:
    cli = _load_cli_module()
    parser = cli.build_parser()
    args = parser.parse_args(["browse-local", "--keyword", "咖啡"])

    assert args.keyword == "咖啡"
    assert args.scope == "同城"
    assert args.limit == 30
    assert args.sort_by == "综合"
