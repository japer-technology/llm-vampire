"""CLI coverage for Phase 2/3 control-plane commands."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from pytest import CaptureFixture, MonkeyPatch

import vampire.cli as cli


def _mock_cli_client(
    monkeypatch: MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[dict[str, object]]:
    """Patch the CLI HTTP seam and record outgoing requests."""
    seen: list[dict[str, object]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "url": str(request.url),
                "json": json.loads(request.content) if request.content else None,
            }
        )
        return handler(request)

    def _build() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(_handler))

    monkeypatch.setattr(cli, "build_sync_client", _build)
    return seen


def test_cli_status_calls_gateway_control_api(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(
        monkeypatch,
        lambda request: httpx.Response(200, json={"object": "vampire.status", "nodes_total": 0}),
    )

    assert cli.main(["status", "--gateway", "http://gateway:7777"]) == 0

    assert seen == [
        {
            "method": "GET",
            "url": "http://gateway:7777/vampire/v1/status",
            "json": None,
        }
    ]
    assert json.loads(capsys.readouterr().out)["object"] == "vampire.status"


def test_cli_discover_sends_static_discovery_request(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"object": "vampire.discovery_result", "nodes": []}
        ),
    )

    assert (
        cli.main(
            [
                "discover",
                "--base-url",
                "http://node-a:1234",
                "--subnet",
                "192.168.1.0/24",
                "--port",
                "7778",
                "--timeout-ms",
                "250",
                "--trusted-only",
            ]
        )
        == 0
    )

    body = seen[0]["json"]
    assert isinstance(body, dict)
    assert body["methods"] == ["static"]
    assert body["base_urls"] == ["http://node-a:1234"]
    assert body["subnets"] == ["192.168.1.0/24"]
    assert body["ports"] == [1234, 7778]
    assert body["timeout_ms"] == 250
    assert body["trusted_only"] is True
    assert json.loads(capsys.readouterr().out)["object"] == "vampire.discovery_result"


def test_cli_nodes_add_and_route_add_shape_phase_api_requests(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))

    assert (
        cli.main(
            [
                "nodes",
                "add",
                "node-a",
                "http://node-a:1234",
                "--trusted",
                "--tag",
                "gpu",
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                "route",
                "add",
                "route-auto",
                "vampire:auto",
                "--target",
                "node-a:qwen",
                "--strategy",
                "least_latency",
                "--fallback",
                "vampire:fast",
            ]
        )
        == 0
    )

    node_body = seen[0]["json"]
    assert isinstance(node_body, dict)
    assert seen[0]["method"] == "POST"
    assert seen[0]["url"] == "http://127.0.0.1:7777/vampire/v1/nodes"
    assert node_body["id"] == "node-a"
    assert node_body["lmstudio_base_url"] == "http://node-a:1234"
    assert node_body["trusted"] is True
    assert node_body["tags"] == ["gpu"]

    route_body = seen[1]["json"]
    assert isinstance(route_body, dict)
    assert seen[1]["method"] == "POST"
    assert seen[1]["url"] == "http://127.0.0.1:7777/vampire/v1/routes"
    assert route_body["id"] == "route-auto"
    assert route_body["virtual_model"] == "vampire:auto"
    assert route_body["targets"] == [{"node": "node-a", "model": "qwen"}]
    assert route_body["strategy"] == "least_latency"
    assert route_body["fallback"] == "vampire:fast"
    assert capsys.readouterr().out.count('"ok": true') == 2


def test_required_implementation_plan_commands_are_bound_to_handlers() -> None:
    parser = cli.build_parser()
    commands = [
        ["serve"],
        ["status"],
        ["discover"],
        ["nodes"],
        ["models"],
        ["metrics"],
        ["route"],
        ["share", "off"],
        ["dashboard"],
        ["ui"],
    ]

    for command in commands:
        args = parser.parse_args(command)
        assert args.func is not cli._todo


def test_cli_nodes_update_get_delete_route_get_delete_and_share_call_control_api(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))

    assert cli.main(["nodes", "update", "node-a", "--trusted", "--queue-depth", "3"]) == 0
    assert cli.main(["nodes", "get", "node-a"]) == 0
    assert cli.main(["nodes", "delete", "node-a"]) == 0
    assert cli.main(["route", "get", "route-auto"]) == 0
    assert cli.main(["route", "delete", "route-auto"]) == 0
    assert (
        cli.main(
            [
                "share",
                "event",
                "on",
                "--duration",
                "2h",
                "--model",
                "lmstudio-vampire/event-safe",
            ]
        )
        == 0
    )
    assert cli.main(["share", "stop"]) == 0

    assert [request["method"] for request in seen] == [
        "PATCH",
        "GET",
        "DELETE",
        "GET",
        "DELETE",
        "POST",
        "POST",
    ]
    assert seen[0]["url"] == "http://127.0.0.1:7777/vampire/v1/nodes/node-a"
    assert seen[0]["json"] == {"trusted": True, "queue_depth": 3}
    assert seen[5]["url"] == "http://127.0.0.1:7777/vampire/v1/share"
    assert seen[5]["json"] == {
        "mode": "event",
        "enabled": True,
        "duration": "2h",
        "model": "lmstudio-vampire/event-safe",
    }
    assert seen[6]["json"] == {"mode": "off", "enabled": False}
    assert capsys.readouterr().out.count('"ok": true') == 7


def test_cli_nodes_drain_marks_node_unavailable_or_restored(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))

    assert cli.main(["nodes", "drain", "node-a"]) == 0
    assert cli.main(["nodes", "drain", "node-a", "off"]) == 0

    assert seen == [
        {
            "method": "PATCH",
            "url": "http://127.0.0.1:7777/vampire/v1/nodes/node-a",
            "json": {"status": "draining"},
        },
        {
            "method": "PATCH",
            "url": "http://127.0.0.1:7777/vampire/v1/nodes/node-a",
            "json": {"status": "online"},
        },
    ]
    assert capsys.readouterr().out.count('"ok": true') == 2


def test_cli_models_metrics_and_dashboard_commands(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    seen = _mock_cli_client(monkeypatch, lambda request: httpx.Response(200, json={"ok": True}))
    opened: list[str] = []
    monkeypatch.setattr("vampire.cli.webbrowser.open", opened.append)

    assert cli.main(["models"]) == 0
    assert cli.main(["metrics", "--gateway", "http://gateway:7777/"]) == 0
    assert cli.main(["dashboard", "--gateway", "http://gateway:7777"]) == 0
    assert cli.main(["ui", "--gateway", "http://gateway:7777", "--open"]) == 0

    assert seen == [
        {
            "method": "GET",
            "url": "http://127.0.0.1:7777/vampire/v1/models",
            "json": None,
        },
        {
            "method": "GET",
            "url": "http://gateway:7777/vampire/v1/metrics",
            "json": None,
        },
    ]
    assert opened == ["http://gateway:7777"]
    assert "http://gateway:7777" in capsys.readouterr().out


def test_cli_share_off_rejects_extra_state(capsys: CaptureFixture[str]) -> None:
    assert cli.main(["share", "off", "on"]) == 2
    assert "share off/stop do not accept" in capsys.readouterr().err


def test_cli_route_add_rejects_invalid_target(capsys: CaptureFixture[str]) -> None:
    assert cli.main(["route", "add", "route-bad", "vampire:auto", "--target", "missing-model"]) == 2
    assert "targets must use node:model" in capsys.readouterr().err
