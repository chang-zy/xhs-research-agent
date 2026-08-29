"""视频地址发现和详情序列化测试。"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from video_processor import find_video_urls
from xhs.types import FeedDetail


def test_find_video_urls_prefers_stream_over_cover() -> None:
    data = {
        "media": {
            "stream": {
                "h264": [
                    {
                        "masterUrl": "https://video.example.com/main.mp4",
                        "backupUrls": ["https://video.example.com/backup.mp4"],
                    }
                ]
            }
        },
        "cover": {"url": "https://image.example.com/cover.jpg"},
    }

    assert find_video_urls(data) == [
        "https://video.example.com/main.mp4",
        "https://video.example.com/backup.mp4",
    ]


def test_feed_detail_preserves_video_metadata() -> None:
    video = {"media": {"stream": {"h264": [{"masterUrl": "https://x/video.mp4"}]}}}
    detail = FeedDetail.from_dict({"noteId": "note-1", "type": "video", "video": video})

    assert detail.to_dict()["video"] == video
