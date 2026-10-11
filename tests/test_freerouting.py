"""
Unit tests for FreeRouting integration.
"""

from unittest.mock import patch, MagicMock
from pathlib import Path
from src.routing.freerouting import FreeRoutingRunner, RoutingResult


def test_freerouting_runner_init():
    """Test FreeRouting runner initialization."""
    runner = FreeRoutingRunner(freerouting_jar="/custom/path/freerouting.jar")
    assert runner.freerouting_jar == "/custom/path/freerouting.jar"


@patch('subprocess.run')
def test_export_dsn(mock_run, tmp_path):
    """Test DSN export via kicad-cli."""
    # First call: version check (returns KiCad 6.0 for compatibility)
    # Second call: actual DSN export
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="6.0.10", stderr=""),  # version check
        MagicMock(returncode=0, stdout="", stderr="")        # DSN export
    ]
    
    runner = FreeRoutingRunner()
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb (version 20240108))")
    dsn_path = tmp_path / "test.dsn"
    
    result = runner._export_dsn(pcb_path, dsn_path)
    
    assert result.success is True
    assert mock_run.call_count == 2
    # First call: version check
    args_v = mock_run.call_args_list[0][0][0]
    assert args_v == ["kicad-cli", "--version"]
    # Second call: DSN export
    args_e = mock_run.call_args_list[1][0][0]
    assert args_e[:4] == ["kicad-cli", "pcb", "export", "dsn"]


@patch('subprocess.run')
def test_run_freerouting(mock_run, tmp_path):
    """Test FreeRouting execution."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    
    runner = FreeRoutingRunner(freerouting_jar="freerouting.jar")
    dsn_path = tmp_path / "test.dsn"
    dsn_path.write_text("(dsn ...)")
    ses_path = tmp_path / "test.ses"
    
    result = runner._run_freerouting(dsn_path, ses_path)
    
    assert result.success is True
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "java" in args
    assert "-jar" in args
    assert "freerouting.jar" in args


@patch('subprocess.run')
def test_import_ses(mock_run, tmp_path):
    """Test SES import back to KiCad."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    
    runner = FreeRoutingRunner()
    ses_path = tmp_path / "test.ses"
    ses_path.write_text("(ses ...)")
    pcb_output = tmp_path / "test_routed.kicad_pcb"
    
    result = runner._import_ses(ses_path, pcb_output)
    
    assert result.success is True
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "kicad-cli" in args
    assert "pcb" in args
    assert "import" in args
    assert "ses" in args