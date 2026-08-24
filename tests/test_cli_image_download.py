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
