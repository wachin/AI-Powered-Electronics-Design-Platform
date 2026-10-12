"""
Unit tests for the FreeRouting integration.

The routing path changed fundamentally and these tests document the new
contract:

* DSN/SES go through KiCad's **`pcbnew`** Python API, not `kicad-cli`. The
  `kicad-cli pcb export dsn` and `kicad-cli pcb import ses` subcommands do not
  exist in KiCad 7+, so the previous implementation could never have worked.
* FreeRouting is started with the **`-de`/`-do`** flags (the modern CLI) and a
  Java 25 runtime, because the jars are compiled to class-file version 69.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.routing.freerouting import FreeRoutingRunner


def test_runner_accepts_explicit_jar_and_java():
    runner = FreeRoutingRunner(
        freerouting_jar="/custom/freerouting.jar", java="/custom/java"
    )
    assert runner.freerouting_jar == "/custom/freerouting.jar"
    assert runner.java == "/custom/java"


def test_runner_discovers_a_java_runtime():
    """A Java runtime must always be resolved, even if it is just `java`."""
    runner = FreeRoutingRunner(freerouting_jar="/x.jar")
    assert runner.java


class TestExportDsn:
    @patch("subprocess.run")
    def test_export_uses_pcbnew_not_kicad_cli(self, mock_run, tmp_path):
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        dsn_path = tmp_path / "test.dsn"

        def fake_run(cmd, **kwargs):
            dsn_path.write_text("(pcb test.dsn)")  # emulate pcbnew writing it
            return MagicMock(returncode=0, stdout="OK\n", stderr="")

        mock_run.side_effect = fake_run

        result = FreeRoutingRunner(java="java")._export_dsn(pcb_path, dsn_path)

        assert result.success is True
        command = mock_run.call_args[0][0]
        # A python interpreter running an inline pcbnew snippet.
        assert "-c" in command
        assert "pcbnew" in command[2]
        assert "ExportSpecctraDSN" in command[2]
        assert "kicad-cli" not in command

    @patch("subprocess.run")
    def test_export_reports_failure_when_pcbnew_declines(self, mock_run, tmp_path):
        pcb_path = tmp_path / "t.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        mock_run.return_value = MagicMock(returncode=0, stdout="FAILED\n", stderr="")

        result = FreeRoutingRunner(java="java")._export_dsn(pcb_path, tmp_path / "t.dsn")

        assert result.success is False
        assert "DSN export failed" in (result.error or "")

    @patch("subprocess.run")
    def test_export_reports_missing_bindings_clearly(self, mock_run, tmp_path):
        """Without pcbnew the message must say what to install."""
        with patch(
            "src.agents.mcp_registry.find_pcbnew_python", return_value=None
        ):
            pcb = tmp_path / "t.kicad_pcb"
            pcb.write_text("(kicad_pcb)")
            result = FreeRoutingRunner(java="java")._export_dsn(pcb, tmp_path / "t.dsn")

        assert result.success is False
        assert "pcbnew" in (result.error or "")
        mock_run.assert_not_called()


class TestRunFreerouting:
    @patch("subprocess.run")
    def test_uses_modern_cli_flags_and_java(self, mock_run, tmp_path):
        dsn_path = tmp_path / "test.dsn"
        dsn_path.write_text("(pcb ...)")
        ses_path = tmp_path / "test.ses"

        def fake_run(cmd, **kwargs):
            ses_path.write_text("(session ...)")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        runner = FreeRoutingRunner(freerouting_jar="/jars/freerouting.jar", java="/java25")
        result = runner._run_freerouting(dsn_path, ses_path)

        assert result.success is True
        args = mock_run.call_args[0][0]
        assert args[0] == "/java25", "must use the discovered Java 25 runtime"
        assert "-jar" in args
        assert "/jars/freerouting.jar" in args
        # The modern flags, not the removed `-d`/`-o` spelling.
        assert "-de" in args
        assert "-do" in args
        assert "-d" not in args

    def test_missing_jar_is_reported_with_the_expected_location(self):
        runner = FreeRoutingRunner(freerouting_jar=None, java="java")
        runner.freerouting_jar = None
        result = runner._run_freerouting(Path("a.dsn"), Path("a.ses"))
        assert result.success is False
        assert "libs/freerouting" in (result.error or "")

    @patch("subprocess.run")
    def test_no_ses_file_is_treated_as_failure(self, mock_run, tmp_path):
        """A zero exit code alone is not proof that routing happened."""
        dsn = tmp_path / "t.dsn"
        dsn.write_text("(pcb)")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = FreeRoutingRunner(freerouting_jar="/x.jar", java="java")._run_freerouting(
            dsn, tmp_path / "t.ses"
        )

        assert result.success is False
        assert "no SES file" in (result.error or "")


class TestImportSes:
    @patch("subprocess.run")
    def test_import_loads_the_original_board_and_saves_to_output(
        self, mock_run, tmp_path
    ):
        ses_path = tmp_path / "test.ses"
        ses_path.write_text("(session)")
        source = tmp_path / "original.kicad_pcb"
        source.write_text("(kicad_pcb)")
        output = tmp_path / "routed.kicad_pcb"

        mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")

        result = FreeRoutingRunner(java="java")._import_ses(ses_path, source, output)

        assert result.success is True
        snippet = mock_run.call_args[0][0][2]
        assert "ImportSpecctraSES" in snippet
        # It must load the ORIGINAL board, not the (not yet existing) output.
        assert str(source) in snippet
        assert str(output) in snippet

    def test_missing_ses_is_reported(self, tmp_path):
        result = FreeRoutingRunner(java="java")._import_ses(
            tmp_path / "missing.ses", tmp_path / "a.kicad_pcb", tmp_path / "out.kicad_pcb"
        )
        assert result.success is False
        assert "missing" in (result.error or "")

    @patch("subprocess.run")
    def test_import_failure_is_reported(self, mock_run, tmp_path):
        ses = tmp_path / "t.ses"
        ses.write_text("(session)")
        source = tmp_path / "a.kicad_pcb"
        source.write_text("(kicad_pcb)")
        mock_run.return_value = MagicMock(returncode=0, stdout="FAILED\n", stderr="")

        result = FreeRoutingRunner(java="java")._import_ses(
            ses, source, tmp_path / "out.kicad_pcb"
        )
        assert result.success is False
        assert "SES import failed" in (result.error or "")


class TestRoutingResult:
    def test_routed_board_path_is_carried(self):
        from src.routing.freerouting import RoutingResult

        result = RoutingResult(success=True, routed_pcb_path=Path("x.kicad_pcb"))
        assert result.routed_pcb_path == Path("x.kicad_pcb")

    def test_default_result_has_no_routed_board(self):
        from src.routing.freerouting import RoutingResult

        assert RoutingResult(success=False).routed_pcb_path is None
