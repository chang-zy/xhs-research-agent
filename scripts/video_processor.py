"""下载小红书视频并生成供多模态模型读取的本地素材。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests


_MEDIA_KEY_HINTS = ("master", "play", "stream", "video", "media", "backup")
_IMAGE_KEY_HINTS = ("image", "cover", "poster", "avatar", "thumbnail")


def find_video_urls(video_data: dict) -> list[str]:
    """从版本不固定的视频对象中找出最可能的播放地址。"""
    candidates: list[tuple[int, str]] = []

    def visit(value, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, (*path, str(key)))
            return
        if isinstance(value, list):
            for child in value:
                visit(child, path)
            return
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return

        lowered_path = "/".join(path).lower()
        lowered_url = value.lower()
        score = 0
        if ".mp4" in lowered_url:
            score += 80
        elif ".m3u8" in lowered_url:
            score += 70
        if any(hint in lowered_path for hint in _MEDIA_KEY_HINTS):
            score += 30
        if any(hint in lowered_path for hint in _IMAGE_KEY_HINTS):
            score -= 100
        if score > 0:
            candidates.append((score, value))

    visit(video_data, ())
    ordered: list[str] = []
    seen: set[str] = set()
    for _, url in sorted(candidates, key=lambda item: item[0], reverse=True):
        if url not in seen:
            ordered.append(url)
            seen.add(url)
    return ordered


class VideoProcessor:
    """把视频转换为视频文件、关键帧、音轨和元数据清单。"""

    def __init__(self, output_dir: str, referer: str = "https://www.xiaohongshu.com/") -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.referer = referer
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare(self, video_data: dict, max_frames: int = 18) -> dict:
        urls = find_video_urls(video_data)
        if not urls:
            return {
                "success": False,
                "error": "详情数据中未找到可下载的视频地址",
                "directory": str(self.output_dir),
            }

        video_path = self.output_dir / "video.mp4"
        download_errors: list[str] = []
        selected_url = ""
        for url in urls:
            try:
                self._download(url, video_path)
                selected_url = url
                break
            except Exception as exc:
                download_errors.append(str(exc))

        if not selected_url:
            return {
                "success": False,
                "error": "视频下载失败",
                "directory": str(self.output_dir),
                "failures": download_errors,
            }

        probe = self._probe(video_path)
        duration = float(probe.get("format", {}).get("duration") or 0)
        frame_paths = self._extract_frames(video_path, duration, max_frames)
        audio_path = self._extract_audio(video_path)
        manifest = {
            "success": True,
            "localPath": str(video_path),
            "sourceUrl": selected_url,
            "durationSeconds": duration,
            "metadata": probe,
            "frames": frame_paths,
            "frameCount": len(frame_paths),
            "audioPath": str(audio_path) if audio_path else None,
            "directory": str(self.output_dir),
            "warning": "完整视频理解耗时较长，并会消耗较多模型额度。",
        }
        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifestPath"] = str(manifest_path)
        return manifest

    def _download(self, url: str, destination: Path) -> None:
        if ".m3u8" in urlparse(url).path.lower():
            ffmpeg = self._require_binary("ffmpeg")
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-headers",
                    f"Referer: {self.referer}\r\nUser-Agent: Mozilla/5.0\r\n",
                    "-i",
                    url,
                    "-c",
                    "copy",
                    "-y",
                    str(destination),
                ],
                check=True,
            )
            return

        headers = {"Referer": self.referer, "User-Agent": "Mozilla/5.0"}
        with requests.get(url, headers=headers, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        if destination.stat().st_size == 0:
            raise RuntimeError("下载结果为空")

    def _probe(self, video_path: Path) -> dict:
        ffprobe = self._require_binary("ffprobe")
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _extract_frames(self, video_path: Path, duration: float, max_frames: int) -> list[str]:
        ffmpeg = self._require_binary("ffmpeg")
        frames_dir = self.output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        max_frames = max(1, max_frames)
        interval = max(1.0, duration / max_frames) if duration else 5.0
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval:.3f}",
                "-frames:v",
                str(max_frames),
                "-q:v",
                "2",
                "-y",
                str(frames_dir / "frame_%03d.jpg"),
            ],
            check=True,
        )
        return [str(path.resolve()) for path in sorted(frames_dir.glob("frame_*.jpg"))]

    def _extract_audio(self, video_path: Path) -> Path | None:
        ffmpeg = self._require_binary("ffmpeg")
        audio_path = self.output_dir / "audio.m4a"
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "aac",
                "-y",
                str(audio_path),
            ],
            check=False,
        )
        return audio_path if completed.returncode == 0 and audio_path.exists() else None

    @staticmethod
    def _require_binary(name: str) -> str:
        path = shutil.which(name)
        if not path:
            raise RuntimeError(f"缺少视频处理依赖: {name}")
        return path
