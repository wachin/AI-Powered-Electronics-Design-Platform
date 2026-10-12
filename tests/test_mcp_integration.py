"""
Tests for the optional MCP server integration.

These cover the parts that must work without a server installed: the registry,
the launch recipe (including the system-interpreter case for `pcbnew`), response
parsing, and the guarantee that a missing server never breaks design generation.

The tests that actually talk to a server are skipped unless one is set up, so the
suite stays green on a machine that has never run `mcp-setup`.
"""

import json
import sys
from pathlib import Path

import pytest

# This project's own virtual environment, whose interpreter lacks `pcbnew`.
# sys.prefix is the venv root and does not follow symlinks the way
# sys.executable.resolve() does on this platform.
_PROJECT_VENV = Path(sys.prefix)

from src.agents.mcp_client import MCPResult
from src.agents.mcp_registry import (
    REGISTRY,
    find_pcbnew_python,
    get_spec,
    is_ready,
    launch_recipe,
    status,
)
from src.agents.mcp_servers import MCPServerManager, render_status
from src.agents.mcp_validation import (
    MCPValidation,
    _parse,
    mcp_validation_available,
    validate_with_mcp,
)


class TestRegistry:
    def test_known_servers_are_registered(self):
        assert {"kicad", "pcbparts"} <= set(REGISTRY)

    def test_every_spec_has_a_license(self):
        """A server without a recorded license must not be launched unnoticed."""
        for spec in REGISTRY.values():
            assert spec.license, f"{spec.key} has no license recorded"

    def test_unknown_server_raises_with_helpful_message(self):
        with pytest.raises(KeyError, match="Unknown MCP server"):
            get_spec("does-not-exist")

    def test_kicad_uses_system_python_for_native_bindings(self):
        """pcbnew ships with KiCad's Python, not with our virtual environment."""
        spec = get_spec("kicad")
        assert spec.needs_system_python is True
        # The isolated environment still holds the server's own packages.
        assert "PYTHONPATH" in spec.launch_env()

    def test_pcbparts_installs_from_its_git_url(self):
        """
        pcbparts-mcp has no PyPI release, so it is declared as a git dependency.

        This is the point of the whole design: installable code is declared as a
        dependency, not cloned into the repository.
        """
        spec = get_spec("pcbparts")
        assert len(spec.install) == 1
        assert "git+https://github.com/" in spec.install[0]
        assert spec.module
        # It must not point into the reference checkout.
        assert spec.source_dir is None

    def test_no_server_installs_from_a_local_checkout(self):
        """
        Installable code must be declared as a package or a git URL.

        The project must not require anyone to clone a research repository in
        order to install its dependencies.
        """
        project_root = Path(__file__).resolve().parents[1]
        for spec in REGISTRY.values():
            assert spec.source_dir is None, (
                f"{spec.key} installs from a local checkout; declare it as a "
                "package or git URL instead"
            )
            for requirement in spec.install:
                assert str(project_root) not in requirement
                assert not requirement.startswith((".", "/")), (
                    f"{spec.key} uses a local path: {requirement}"
                )

    def test_pcbnew_interpreter_is_discovered_or_absent(self):
        """The lookup must return a real path, or None -- never raise."""
        python = find_pcbnew_python()
        assert python is None or Path(python).exists()

    def test_status_reports_every_server(self):
        report = status()
        assert {entry["key"] for entry in report} == set(REGISTRY)
        assert all("ready" in entry for entry in report)

    def test_render_status_mentions_setup_command(self):
        text = render_status(status())
        assert "mcp-setup" in text
        assert "optional" in text.lower()


class TestLaunchRecipe:
    def test_unconfigured_server_yields_no_recipe(self):
        """A server whose environment does not exist must not produce a command."""
        spec = get_spec("pcbparts")
        if not is_ready(spec):
            assert spec.launch_command() is None
            assert launch_recipe("pcbparts") is None

    def test_extra_env_is_merged(self):
        recipe = launch_recipe("kicad", {"KICAD_MCP_PROJECTS_BASE": "/tmp/x"})
        if recipe is None:
            pytest.skip("kicad MCP server not set up")
        command, env = recipe
        assert command
        assert env["KICAD_MCP_PROJECTS_BASE"] == "/tmp/x"

    def test_kicad_launch_does_not_use_our_venv_interpreter(self):
        """
        Regression guard: the launcher must not use this project's venv python.

        That interpreter does not have `pcbnew`, so using it silently disables
        board analysis and auto-routing. The isolated packages are exposed
        through PYTHONPATH instead.
        """
        spec = get_spec("kicad")
        command = spec.launch_command()
        if command is None:
            pytest.skip("kicad MCP server not set up")

        venv_dir = str(Path(sys.prefix)) if False else str(_PROJECT_VENV)
        assert not command[0].startswith(venv_dir), (
            "launcher used the project venv python, which lacks pcbnew"
        )
        # And the packages must still be reachable.
        assert "PYTHONPATH" in spec.launch_env()


class TestParse:
    """MCP wraps tool output two levels deep; parsing must unwrap both."""

    def test_unwraps_jsonrpc_content_blocks(self):
        payload = {"success": True, "violations": 0}
        result = MCPResult(
            success=True,
            content={"content": [{"type": "text", "text": json.dumps(payload)}]},
        )
        assert _parse(result) == payload

    def test_handles_a_bare_list_of_blocks(self):
        result = MCPResult(
            success=True, content=[{"type": "text", "text": '{"success": true}'}]
        )
        assert _parse(result)["success"] is True

    def test_handles_a_direct_dict(self):
        result = MCPResult(success=True, content={"success": True, "violations": 3})
        assert _parse(result)["violations"] == 3

    def test_non_json_text_is_returned_raw(self):
        result = MCPResult(success=True, content=[{"type": "text", "text": "hello"}])
        assert _parse(result)["raw"] == "hello"

    def test_failed_call_is_reported_as_failure(self):
        result = MCPResult(success=False, error="boom")
        parsed = _parse(result)
        assert parsed["success"] is False
        assert parsed["error"] == "boom"


class TestMCPValidationResult:
    def test_passed_requires_both_checks_to_run(self):
        assert MCPValidation(available=True, erc={"success": True}, drc={"success": True}).passed
        assert not MCPValidation(available=True, erc={"success": True}).passed
        assert not MCPValidation(available=False).passed

    def test_violations_are_summed(self):
        result = MCPValidation(
            available=True, erc={"success": True, "violations": 1},
            drc={"success": True, "violations": 4},
        )
        assert result.violations == 5

    def test_library_only_findings_are_recognised(self):
        result = MCPValidation(
            available=True,
            drc={
                "success": True,
                "violations": 2,
                "summary": [{"type": "lib_footprint_issues"}],
            },
        )
        assert result.only_library_warnings is True

    def test_real_violations_are_not_dismissed_as_library_notices(self):
        result = MCPValidation(
            available=True,
            drc={
                "success": True,
                "violations": 1,
                "summary": [{"type": "clearance"}],
            },
        )
        assert result.only_library_warnings is False

    def test_to_dict_is_json_serialisable(self):
        json.dumps(MCPValidation(available=False, error="x").to_dict())


class TestGracefulDegradation:
    """A missing MCP server must never break design generation."""

    @pytest.mark.asyncio
    async def test_missing_server_returns_unavailable(self, tmp_path):
        files = {"sch": tmp_path / "a.kicad_sch"}
        files["sch"].write_text("(kicad_sch)")
        outcome = await validate_with_mcp(
            files=files, workspace=tmp_path / "ws", project_name="p",
            server="pcbparts",  # deliberately the one that is not set up
        )
        if mcp_validation_available("pcbparts"):  # pragma: no cover
            pytest.skip("pcbparts is set up; this test covers the missing case")
        assert outcome.available is False
        assert outcome.error
        assert outcome.passed is False

    @pytest.mark.asyncio
    async def test_no_kicad_files_yields_unavailable(self, tmp_path):
        outcome = await validate_with_mcp(
            files={"other": tmp_path / "notes.txt"},
            workspace=tmp_path / "ws",
            project_name="p",
        )
        assert outcome.available is False
        assert "no .kicad_sch" in outcome.error


class TestServerManager:
    def test_manager_uses_the_project_env_root_by_default(self):
        manager = MCPServerManager()
        assert manager.base_dir.name == ".mcp_envs"

    def test_ensure_env_creates_a_usable_interpreter(self, tmp_path):
        """Setting up a server must produce a working interpreter."""
        manager = MCPServerManager(base_dir=tmp_path, verbose=False)
        spec = get_spec("pcbparts")
        ok, created, error = manager.ensure_env(spec)
        assert ok is True, error
        assert (tmp_path / "pcbparts" / "bin" / "python").exists()

    def test_free_route_jar_and_java_are_discoverable(self):
        """
        Routing needs both a jar and a Java 25 runtime; the server env wires
        whatever is found, and must not crash when neither is present.
        """
        from src.agents.mcp_registry import (
            FREEROUTING_JAR_ENV,
            find_freerouting_jar,
            find_java25,
        )

        jar, java = find_freerouting_jar(), find_java25()
        assert jar is None or jar.is_file()
        assert java is None or java.exists()
        env = get_spec("kicad").launch_env()
        if jar is not None:
            assert env[FREEROUTING_JAR_ENV] == str(jar)
