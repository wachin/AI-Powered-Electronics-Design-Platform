"""
Unit and Integration tests for AIDesignOrchestrator.
"""

import tempfile
from pathlib import Path
from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest


def test_orchestrator_ldo_flow():
    orchestrator = AIDesignOrchestrator()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        request = DesignRequest(
            prompt="Design a 5V to 3.3V LDO regulator circuit",
            project_name="test_ldo",
        )

        summary = orchestrator.process_request(request, out_dir)

        assert summary.project_name == "test_ldo"
        assert summary.erc_report.passed is True
        assert len(summary.circuit_ir.components) >= 4  # U1, C1, C2, D1, R1
        assert "U1" in summary.circuit_ir.components
        assert len(summary.bom) >= 4
        assert summary.generated_files["sch"].exists()
        assert summary.generated_files["pcb"].exists()
        assert summary.generated_files["pro"].exists()
