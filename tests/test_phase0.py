"""Phase 0 scaffolding & foundations tests (IMPLEMENTATION-PLAN.md §"Phase 0").

Phase 0 promises an installable package with the ``vampire`` console-script, an
app factory and configuration, the core Pydantic models from DESIGN-API.md §4,
and the testing/linting/type-checking/CI scaffolding. These tests pin those
foundations so later phases cannot quietly regress the project's bedrock.
"""

from __future__ import annotations

import logging
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vampire import __version__
from vampire.app import create_app
from vampire.cli import build_parser, main
from vampire.config import Settings, configure_logging, get_settings
from vampire.models import (
    ChatCompletionRequest,
    CompletionRequest,
    EmbeddingsRequest,
    ModelCard,
    ModelListResponse,
    Node,
    NodeCapabilities,
    OpenAIError,
    OpenAIErrorResponse,
    OpenAIMessage,
    ResponsesRequest,
    RoutePolicy,
    RouteTarget,
    ShareStatus,
    VirtualModel,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- Package + console-script entry point -----------------------------------


def test_package_exposes_semver_version() -> None:
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_package_version_matches_pyproject() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject


def test_pyproject_declares_vampire_console_script() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.scripts]" in pyproject
    assert 'vampire = "vampire.cli:main"' in pyproject
    assert 'vampire-desktop = "vampire.desktop.launcher:main"' in pyproject


def test_pyproject_packages_dashboard_asset() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'vampire = ["assets/vampire-dashboard.html"]' in pyproject


def test_python_dash_m_vampire_runs_the_cli() -> None:
    """``python -m vampire`` must reach the same entry point as the script."""
    result = subprocess.run(
        [sys.executable, "-m", "vampire", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"vampire {__version__}" in result.stdout


def test_main_module_guard_executes_without_arguments() -> None:
    """The ``__main__`` module exits cleanly when no subcommand is supplied."""
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("vampire", run_name="__main__")
    # argparse exits 2 when the required subcommand is missing.
    assert excinfo.value.code == 2


# --- App factory: the three METHOD-A surfaces --------------------------------


def test_app_factory_builds_titled_application() -> None:
    app = create_app()
    assert app.title == "llm-vampire"
    assert app.version == __version__


def test_app_factory_returns_independent_instances() -> None:
    assert create_app() is not create_app()


def test_app_mounts_openai_control_and_static_surfaces() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    # Layer 1 OpenAI-compatible proxy + Layer 2 Vampire control API.
    assert any(path.startswith("/v1") for path in paths)
    assert "/vampire/v1/status" in paths

    # Layer 3 static UI: the Phase 4 dashboard is served from the application
    # root in editable installs.
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_status_route_reports_scaffold_envelope() -> None:
    client = TestClient(create_app())
    body = client.get("/vampire/v1/status").json()
    assert body["object"] == "vampire.status"
    assert body["version"] == __version__
    assert body["nodes_total"] == 0
    assert body["nodes_online"] == 0


# --- Configuration -----------------------------------------------------------


def test_settings_defaults_match_design_api_ports() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 7777
    assert settings.default_base_url == "http://localhost:1234"
    assert settings.lmstudio_base_url == settings.default_base_url
    assert settings.log_level == "INFO"
    assert settings.auth_token == ""


def test_settings_honour_vampire_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAMPIRE_PORT", "8123")
    monkeypatch.setenv("VAMPIRE_LMSTUDIO_BASE_URL", "http://node-x:4321")
    monkeypatch.setenv("VAMPIRE_LOG_LEVEL", "DEBUG")

    settings = get_settings()
    assert settings.port == 8123
    assert settings.default_base_url == "http://node-x:4321"
    assert settings.log_level == "DEBUG"


def test_settings_honour_provider_neutral_base_url_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAMPIRE_DEFAULT_BASE_URL", "http://node-y:8080")

    assert Settings().default_base_url == "http://node-y:8080"


def test_get_settings_returns_cached_snapshot() -> None:
    assert get_settings() is get_settings()


def test_configure_logging_applies_settings_level() -> None:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    try:
        configure_logging(Settings(log_level="WARNING"))
        assert root.level == logging.WARNING
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def test_configure_logging_falls_back_on_unknown_level() -> None:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    try:
        configure_logging(Settings(log_level="not-a-level"))
        assert root.level == logging.INFO
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


# --- Core Pydantic models (DESIGN-API.md §4) ---------------------------------


def test_model_card_defaults_to_llm_vampire_ownership() -> None:
    card = ModelCard(id="local-model")
    assert card.object == "model"
    assert isinstance(card.created, int)
    assert card.created > 0
    assert card.owned_by == "llm-vampire"


def test_model_list_rejects_duplicate_model_ids() -> None:
    with pytest.raises(ValidationError):
        ModelListResponse(data=[ModelCard(id="dup"), ModelCard(id="dup")])


def test_node_carries_capabilities_and_routing_defaults() -> None:
    node = Node(id="node-a", base_url="http://node-a:1234")
    assert node.status == "unknown"
    assert node.trusted is False
    assert node.tags == []
    assert node.request_count == 0
    assert isinstance(node.capabilities, NodeCapabilities)
    assert node.capabilities.chat is True


def test_node_accepts_and_serializes_legacy_lmstudio_base_url() -> None:
    node = Node.model_validate(
        {"id": "legacy-node", "lmstudio_base_url": "http://legacy-node:1234"}
    )

    assert node.base_url == "http://legacy-node:1234"
    assert node.model_dump()["lmstudio_base_url"] == node.base_url


def test_virtual_model_and_route_policy_shapes() -> None:
    virtual = VirtualModel(id="vampire:auto", targets=["node-a:llama"])
    assert virtual.type == "virtual"

    policy = RoutePolicy(
        id="route-auto",
        virtual_model="vampire:auto",
        targets=[RouteTarget(node="node-a", model="llama")],
    )
    assert policy.strategy == "round_robin"
    assert policy.fallback is None
    assert policy.targets[0].node == "node-a"


def test_share_status_defaults_to_off() -> None:
    share = ShareStatus()
    assert share.object == "vampire.share"
    assert share.mode == "off"
    assert share.enabled is False


def test_openai_request_models_preserve_extra_fields() -> None:
    chat = ChatCompletionRequest(
        model="local-model",
        messages=[OpenAIMessage(role="user", content="hello")],
        stream=True,
    )
    assert chat.messages[0].role == "user"
    assert chat.stream is True

    completion = CompletionRequest(model="local-model", prompt="hi")
    assert completion.prompt == "hi"

    embeddings = EmbeddingsRequest(model="local-model", input="hi")
    assert embeddings.input == "hi"

    responses = ResponsesRequest(model="local-model", input="hi")
    assert responses.input == "hi"


def test_openai_error_envelope_shape() -> None:
    envelope = OpenAIErrorResponse(
        error=OpenAIError(message="boom", type="server_error", code="upstream_unavailable")
    )
    assert envelope.error.code == "upstream_unavailable"
    assert envelope.error.type == "server_error"


# --- CLI scaffolding ---------------------------------------------------------


def test_cli_version_uses_console_entrypoint(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert f"vampire {__version__}" in capsys.readouterr().out


def test_parser_binds_every_implementation_plan_command() -> None:
    parser = build_parser()
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
        assert callable(args.func)


# --- Testing / tooling / CI scaffolding (best practice meta-tests) -----------


def test_pyproject_pins_dev_tooling_and_test_paths() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for tool in ("mypy", "pytest", "ruff"):
        assert tool in pyproject
    assert 'testpaths = ["tests"]' in pyproject
    assert "strict = true" in pyproject


def test_ci_workflow_runs_format_lint_type_and_tests() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file()
    content = workflow.read_text(encoding="utf-8")
    for command in ("ruff format", "ruff check", "mypy", "pytest"):
        assert command in content


def test_phase_test_suite_exists_for_phases_zero_through_four() -> None:
    tests_dir = REPO_ROOT / "tests"
    for phase in range(5):
        assert (tests_dir / f"test_phase{phase}.py").is_file()
