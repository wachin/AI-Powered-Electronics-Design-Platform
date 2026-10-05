"""
Tests for AI Design Agent with MCP Integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.ai_agent import (
    AIDesignAgent, AgentGoal, AgentState, PlanStep, ExecutionResult, AgentExecution
)
from src.agents.mcp_client import MCPResult
from src.agents.orchestrator import DesignSummary, ERCReport


@pytest.fixture
def mock_mcp_client():
    client = AsyncMock()
    client.call_tool = AsyncMock(return_value=MCPResult(success=True, content={"passed": True}))
    return client


@pytest.fixture
def agent(mock_mcp_client):
    with patch('src.agents.ai_agent.ComponentDatabase'):
        agent = AIDesignAgent(mock_mcp_client, "/tmp/test_project")
        return agent


@pytest.mark.asyncio
async def test_agent_goal_creation():
    goal = AgentGoal(
        description="Design a 5V to 3.3V LDO regulator",
        constraints={"input_voltage": 5.0, "output_voltage": 3.3, "current": 0.5}
    )
    assert goal.description == "Design a 5V to 3.3V LDO regulator"
    assert goal.constraints["output_voltage"] == 3.3


@pytest.mark.asyncio
async def test_plan_step_creation():
    step = PlanStep(
        step_id=1,
        tool="create_kicad_project",
        description="Create KiCad project",
        arguments={"project_path": "/tmp/test"},
        expected_outcome="Project created",
        verification="Project exists"
    )
    assert step.step_id == 1
    assert step.tool == "create_kicad_project"


@pytest.mark.asyncio
async def test_plan_ldo_design(agent):
    goal = AgentGoal(
        description="Design a 5V to 3.3V LDO regulator",
        constraints={"input_voltage": 5.0, "output_voltage": 3.3, "current": 0.5}
    )

    plan = agent._plan_ldo_design(goal, 1)

    assert len(plan) > 0
    assert plan[0].tool == "search_parts"
    assert "LDO" in plan[0].description
    
    # Check for project creation step
    create_project_steps = [s for s in plan if s.tool == "create_kicad_project"]
    assert len(create_project_steps) == 1

    # Check for LDO component
    ldo_steps = [s for s in plan if "LDO" in s.description and "add_component" in s.tool]
    assert len(ldo_steps) == 1


@pytest.mark.asyncio
async def test_plan_buck_design(agent):
    goal = AgentGoal(
        description="Create a 12V to 5V buck converter",
        constraints={"input_voltage": 12.0, "output_voltage": 5.0, "current": 3.0}
    )

    plan = agent._plan_buck_design(goal, 1)

    assert len(plan) >= 2
    assert plan[0].tool == "search_parts"
    assert "buck" in plan[0].description.lower()


@pytest.mark.asyncio
async def test_plan_boost_design(agent):
    goal = AgentGoal(
        description="Create a 3.3V to 5V boost converter",
        constraints={"input_voltage": 3.3, "output_voltage": 5.0, "current": 1.0}
    )

    plan = agent._plan_boost_design(goal, 1)

    assert len(plan) >= 2
    assert plan[0].tool == "search_parts"
    assert "boost" in plan[0].description.lower()


@pytest.mark.asyncio
async def test_plan_led_circuit(agent):
    goal = AgentGoal(description="Simple LED circuit with resistor")

    plan = agent._plan_led_circuit(goal, 1)

    assert len(plan) >= 3
    tools = [s.tool for s in plan]
    assert "create_kicad_project" in tools
    assert "add_component_from_library" in tools


@pytest.mark.asyncio
async def test_execute_step_success(agent):
    step = PlanStep(
        step_id=1,
        tool="create_kicad_project",
        description="Create project",
        arguments={"project_path": "/tmp/test"},
        expected_outcome="Project created"
    )

    agent.mcp_client.call_tool = AsyncMock(return_value=MCPResult(
        success=True, content={"status": "created"}
    ))

    result = await agent._execute_step(step)

    assert result.success is True
    assert result.step_id == 1


@pytest.mark.asyncio
async def test_execute_step_failure(agent):
    step = PlanStep(
        step_id=1,
        tool="create_kicad_project",
        description="Create project",
        arguments={"project_path": "/tmp/test"},
        expected_outcome="Project created"
    )

    agent.mcp_client.call_tool = AsyncMock(return_value=MCPResult(
        success=False, error="Project already exists"
    ))

    result = await agent._execute_step(step)

    assert result.success is False
    assert result.error == "Project already exists"


@pytest.mark.asyncio
async def test_verify_step_erc(agent):
    step = PlanStep(
        step_id=1,
        tool="run_erc",
        description="Run ERC",
        arguments={},
        expected_outcome="ERC passes",
        verification="ERC passes with zero errors"
    )

    result = MCPResult(success=True, content={"passed": True, "errors": 0})

    passed, details = await agent._verify_step(step, result)

    assert passed is True
    assert "passed" in details


@pytest.mark.asyncio
async def test_verify_step_spice(agent):
    step = PlanStep(
        step_id=1,
        tool="run_spice",
        description="Run SPICE",
        arguments={},
        expected_outcome="Simulation converges",
        verification="SPICE converges"
    )

    result = MCPResult(success=True, content={"success": True, "stdout": "OK"})

    passed, details = await agent._verify_step(step, result)

    assert passed is True
    assert "converged" in details


@pytest.mark.asyncio
async def test_generate_plan_ldo(agent):
    goal = AgentGoal(
        description="Design a 5V to 3.3V LDO regulator",
        constraints={"input_voltage": 5.0, "output_voltage": 3.3, "current": 0.5}
    )

    plan = await agent._generate_plan(goal)

    assert len(plan) > 5  # Should have multiple steps
    
    # Check for LDO-specific steps
    tool_names = [s.tool for s in plan]
    assert "search_parts" in tool_names
    assert "create_kicad_project" in tool_names
    assert "add_component_from_library" in tool_names
    assert "add_wire" in tool_names
    assert "run_erc" in tool_names


@pytest.mark.asyncio
async def test_execute_goal_ldo(agent):
    goal = AgentGoal(
        description="Design a 5V to 3.3V LDO regulator with LED",
        constraints={"input_voltage": 5.0, "output_voltage": 3.3, "current": 0.5}
    )

    # Mock all tool calls to succeed
    agent.mcp_client.call_tool = AsyncMock(return_value=MCPResult(
        success=True, content={"passed": True, "success": True}
    ))
    
    # Mock the orchestrator's process_request (sync method run in executor)
    mock_summary = MagicMock(spec=DesignSummary)
    mock_summary.erc_report = MagicMock(spec=ERCReport)
    mock_summary.erc_report.passed = True
    mock_summary.to_dict = MagicMock(return_value={"status": "ok"})
    
    agent.orchestrator.process_request = MagicMock(return_value=mock_summary)

    execution = await agent.execute_goal(goal)

    assert execution.state == AgentState.COMPLETED
    assert len(execution.plan) > 0
    assert len(execution.execution_results) > 0


@pytest.mark.asyncio
async def test_agent_state_transitions(agent):
    goal = AgentGoal(description="Simple LED circuit")

    agent.mcp_client.call_tool = AsyncMock(return_value=MCPResult(
        success=True, content={"passed": True}
    ))
    
    mock_summary = MagicMock(spec=DesignSummary)
    mock_summary.erc_report = MagicMock(spec=ERCReport)
    mock_summary.erc_report.passed = True
    mock_summary.to_dict = MagicMock(return_value={"status": "ok"})
    
    agent.orchestrator.process_request = MagicMock(return_value=mock_summary)

    execution = await agent.execute_goal(goal)

    assert execution.state == AgentState.COMPLETED
    assert execution.completed_at is not None


@pytest.mark.asyncio
async def test_agent_failure_handling(agent):
    goal = AgentGoal(description="Design a circuit")

    agent.mcp_client.call_tool = AsyncMock(return_value=MCPResult(
        success=False, error="Tool not found"
    ))

    execution = await agent.execute_goal(goal)

    assert execution.state == AgentState.FAILED
    assert execution.error is not None
    assert "Tool not found" in execution.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])