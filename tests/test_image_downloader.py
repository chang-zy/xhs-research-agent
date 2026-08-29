from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from image_downloader import ImageDownloader


def test_xhs_cdn_http_url_is_upgraded_to_https() -> None:
    url = "http://sns-webpic-qc.xhscdn.com/path/image.webp?token=abc"

    assert ImageDownloader._secure_xhs_cdn_url(url) == (
        "https://sns-webpic-qc.xhscdn.com/path/image.webp?token=abc"
    )


def test_non_xhs_url_is_unchanged() -> None:
    url = "http://example.com/path/image.webp"

    assert ImageDownloader._secure_xhs_cdn_url(url) == url
