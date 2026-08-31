"""任务收尾与 Chrome 所有权判断测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_cli_module():
    cli_path = Path(__file__).parents[1] / "scripts" / "cli.py"
    spec = importlib.util.spec_from_file_location("xhs_cli_cleanup", cli_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cleanup_parser_is_safe_by_default() -> None:
    cli = _load_cli_module()
    args = cli.build_parser().parse_args(["cleanup"])

    assert args.force_close_chrome is False
    assert args.func is cli.cmd_cleanup


def test_quit_chrome_preserves_unmanaged_browser(monkeypatch) -> None:
    cli = _load_cli_module()
    monkeypatch.setattr(cli, "_read_browser_state", lambda: None)

    result = cli._quit_chrome()

    assert result["closed"] is False
    assert "保留用户浏览器" in result["reason"]


def test_cleanup_calls_extension_without_starting_browser(monkeypatch) -> None:
    cli = _load_cli_module()
    calls = []

    class FakePage:
        def __init__(self, bridge_url):
            calls.append(("init", bridge_url))

        def is_server_running(self):
            return True

        def is_extension_connected(self):
            return True

        def cleanup_managed_tabs(self):
            calls.append(("cleanup",))
            return {"closed_tabs": 2}

    monkeypatch.setattr("xhs.bridge.BridgePage", FakePage)
    monkeypatch.setattr(
        cli,
        "_quit_chrome",
        lambda force=False: {"closed": True, "force": force},
    )

    captured = {}

    def fake_output(data, exit_code=0):
        captured.update(data)

    monkeypatch.setattr(cli, "_output", fake_output)
    cli.cmd_cleanup(SimpleNamespace(bridge_url="ws://localhost:9333", force_close_chrome=False))

    assert ("cleanup",) in calls
    assert captured["cleanup"]["tabs"]["closed_tabs"] == 2
    assert captured["cleanup"]["chrome"]["closed"] is True


def test_cleanup_still_quits_browser_when_extension_cleanup_fails(monkeypatch) -> None:
    cli = _load_cli_module()

    class OldExtensionPage:
        def __init__(self, _bridge_url):
            pass

        def is_server_running(self):
            return True

        def is_extension_connected(self):
            return True

        def cleanup_managed_tabs(self):
            raise RuntimeError("unknown method")

    monkeypatch.setattr("xhs.bridge.BridgePage", OldExtensionPage)
    monkeypatch.setattr(cli, "_quit_chrome", lambda force=False: {"closed": True})

    captured = {}
    monkeypatch.setattr(cli, "_output", lambda data, exit_code=0: captured.update(data))
    cli.cmd_cleanup(SimpleNamespace(bridge_url="ws://localhost:9333", force_close_chrome=False))

    assert captured["cleanup"]["chrome"]["closed"] is True
    assert "标签页清理失败" in captured["cleanup"]["tabs"]["reason"]
