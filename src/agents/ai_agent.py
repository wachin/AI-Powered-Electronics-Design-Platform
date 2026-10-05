"""
AI Design Agent with MCP Tool Integration.

Implements an intelligent agent that can use MCP tools for autonomous
electronics design automation with planning and verification loops.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
from pathlib import Path
import os

from src.agents.mcp_client import MCPClient, KiCadMCPTools, create_mcp_client, MCPResult
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType, PowerDomain
from src.core.erc import ERCValidator, ERCReport
from src.generators.kicad_generator import KiCadGenerator
from src.simulation.ngspice import simulate_circuit, SimulationResult
from src.routing.freerouting import route_kicad_pcb, RoutingResult
from src.components.database import ComponentDatabase
from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest, DesignSummary

logger = logging.getLogger(__name__)


class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentGoal:
    description: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1


@dataclass
class PlanStep:
    step_id: int
    tool: str
    description: str
    arguments: Dict[str, Any]
    expected_outcome: str
    verification: Optional[str] = None


@dataclass
class ExecutionResult:
    step_id: int
    success: bool
    output: Any = None
    error: Optional[str] = None
    verification_passed: bool = False
    verification_details: str = ""


@dataclass
class AgentExecution:
    goal: AgentGoal
    plan: List[PlanStep] = field(default_factory=list)
    execution_results: List[ExecutionResult] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class AIDesignAgent:
    def __init__(
        self,
        mcp_client: MCPClient,
        project_path: str,
        component_db: Optional[ComponentDatabase] = None
    ):
        self.mcp_client = mcp_client
        self.project_path = project_path
        self.component_db = component_db or ComponentDatabase()

        self.kicad_tools = KiCadMCPTools(mcp_client)
        self.orchestrator = AIDesignOrchestrator(db=self.component_db)
        self.current_execution: Optional[AgentExecution] = None

    async def execute_goal(self, goal: AgentGoal) -> AgentExecution:
        execution = AgentExecution(goal=goal, state=AgentState.PLANNING)
        self.current_execution = execution

        try:
            logger.info(f"Planning for goal: {goal.description}")
            plan = await self._generate_plan(goal)
            execution.plan = plan

            execution.state = AgentState.EXECUTING
            for step in plan:
                result = await self._execute_step(step)
                execution.execution_results.append(result)

                if not result.success:
                    recovery = await self._attempt_recovery(step, result)
                    if not recovery.success:
                        execution.state = AgentState.FAILED
                        execution.error = f"Step {step.step_id} failed: {result.error}"
                        return execution

            execution.state = AgentState.VERIFYING
            await self._verify_execution(execution)

            await self._run_integration_pipeline(execution)

            execution.state = AgentState.COMPLETED
            execution.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            execution.state = AgentState.FAILED
            execution.error = str(e)

        return execution

    async def _generate_plan(self, goal: AgentGoal) -> List[PlanStep]:
        goal_lower = goal.description.lower()
        plan = []
        step_id = 1

        if any(kw in goal.description.lower() for kw in ["ldo", "linear regulator", "voltage regulator"]):
            plan.extend(self._plan_ldo_design(goal, step_id))
            step_id = len(plan) + 1
        elif any(kw in goal.description.lower() for kw in ["buck", "step-down", "switching regulator"]):
            plan.extend(self._plan_buck_design(goal, step_id))
            step_id = len(plan) + 1
        elif any(kw in goal.description.lower() for kw in ["boost", "step-up"]):
            plan.extend(self._plan_boost_design(goal, step_id))
            step_id = len(plan) + 1
        elif "led" in goal.description.lower():
            plan.extend(self._plan_led_circuit(goal, step_id))
            step_id = len(plan) + 1
        else:
            plan.extend(self._plan_generic_circuit(goal, step_id))
            step_id = len(plan) + 1

        plan.extend([
            PlanStep(
                step_id=step_id,
                tool="run_erc",
                description="Run Electrical Rule Check on schematic",
                arguments={},
                expected_outcome="ERC passes with zero errors",
                verification="ERC report shows zero errors"
            ),
            PlanStep(
                step_id=step_id + 1,
                tool="run_spice",
                description="Run SPICE simulation",
                arguments={},
                expected_outcome="Simulation converges and voltages match targets",
                verification="SPICE output shows correct voltages"
            ),
            PlanStep(
                step_id=step_id + 2,
                tool="route_pcb",
                description="Auto-route PCB",
                arguments={},
                expected_outcome="PCB fully routed with zero DRC errors",
                verification="DRC passes"
            )
        ])

        return plan

    def _plan_ldo_design(self, goal: AgentGoal, start_id: int) -> List[PlanStep]:
        step_id = start_id
        steps = []

        v_in = goal.constraints.get("input_voltage", 5.0)
        v_out = goal.constraints.get("output_voltage", 3.3)
        i_out = goal.constraints.get("current", 0.5)

        steps.append(PlanStep(
            step_id=step_id,
            tool="search_parts",
            description=f"Search for {v_out}V LDO regulator {i_out}A",
            arguments={"query": f"{v_out}V LDO {i_out}A", "limit": 5},
            expected_outcome="Find suitable LDO regulator"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="create_kicad_project",
            description="Create KiCad project for LDO design",
            arguments={"project_path": self.project_path},
            expected_outcome="Empty KiCad project created"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_component_from_library",
            description="Add LDO regulator",
            arguments={
                "project_path": self.project_path,
                "lib_id": "Regulator_Linear:AMS1117-3.3",
                "reference": "U1",
                "value": f"{v_out}V",
                "position": {"x": 100, "y": 100}
            },
            expected_outcome="LDO regulator U1 added to schematic"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_component_from_library",
            description="Add input capacitor",
            arguments={
                "project_path": self.project_path,
                "lib_id": "Device:C",
                "reference": "C1",
                "value": "10uF",
                "position": {"x": 50, "y": 100}
            },
            expected_outcome="Input capacitor C1 added"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_component_from_library",
            description="Add output capacitor",
            arguments={
                "project_path": self.project_path,
                "lib_id": "Device:C",
                "reference": "C2",
                "value": "22uF",
                "position": {"x": 150, "y": 100}
            },
            expected_outcome="Output capacitor C2 added"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_wire",
            description="Wire input to LDO",
            arguments={
                "project_path": self.project_path,
                "start": {"x": 50, "y": 100},
                "end": {"x": 100, "y": 100}
            },
            expected_outcome="Input connected to LDO VIN"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_wire",
            description="Wire LDO output to output cap",
            arguments={
                "project_path": self.project_path,
                "start": {"x": 100, "y": 100},
                "end": {"x": 150, "y": 100}
            },
            expected_outcome="LDO VOUT connected to output capacitor"
        ))
        step_id += 1

        steps.append(PlanStep(
            step_id=step_id,
            tool="add_label",
            description="Add GND labels",
            arguments={
                "project_path": self.project_path,
                "label": "GND",
                "position": {"x": 50, "y": 150}
            },
            expected_outcome="Ground net labeled"
        ))
        step_id += 1

        return steps

    def _plan_buck_design(self, goal: AgentGoal, start_id: int) -> List[PlanStep]:
        return [
            PlanStep(
                step_id=start_id,
                tool="search_parts",
                description="Search for buck converter IC",
                arguments={"query": "buck converter 12V 5V 3A", "limit": 5},
                expected_outcome="Find buck controller"
            ),
            PlanStep(
                step_id=start_id + 1,
                tool="create_kicad_project",
                description="Create project for buck converter",
                arguments={"project_path": self.project_path},
                expected_outcome="Project created"
            )
        ]

    def _plan_boost_design(self, goal: AgentGoal, start_id: int) -> List[PlanStep]:
        return [
            PlanStep(
                step_id=start_id,
                tool="search_parts",
                description="Search for boost converter IC",
                arguments={"query": "boost converter 3.3V 5V", "limit": 5},
                expected_outcome="Find boost controller"
            ),
            PlanStep(
                step_id=start_id + 1,
                tool="create_kicad_project",
                description="Create project for boost converter",
                arguments={"project_path": self.project_path},
                expected_outcome="Project created"
            )
        ]

    def _plan_led_circuit(self, goal: AgentGoal, start_id: int) -> List[PlanStep]:
        return [
            PlanStep(
                step_id=start_id,
                tool="create_kicad_project",
                description="Create LED circuit project",
                arguments={"project_path": self.project_path},
                expected_outcome="Project created"
            ),
            PlanStep(
                step_id=start_id + 1,
                tool="add_component_from_library",
                description="Add LED",
                arguments={
                    "project_path": self.project_path,
                    "lib_id": "Device:LED",
                    "reference": "D1",
                    "value": "Green",
                    "position": {"x": 100, "y": 100}
                },
                expected_outcome="LED added"
            ),
            PlanStep(
                step_id=start_id + 2,
                tool="add_component_from_library",
                description="Add current limiting resistor",
                arguments={
                    "project_path": self.project_path,
                    "lib_id": "Device:R",
                    "reference": "R1",
                    "value": "330",
                    "position": {"x": 50, "y": 100}
                },
                expected_outcome="Resistor added"
            )
        ]

    def _plan_generic_circuit(self, goal: AgentGoal, start_id: int) -> List[PlanStep]:
        return [
            PlanStep(
                step_id=start_id,
                tool="create_kicad_project",
                description="Create generic project",
                arguments={"project_path": self.project_path},
                expected_outcome="Project created"
            )
        ]

    async def _execute_step(self, step: PlanStep) -> ExecutionResult:
        logger.info(f"Executing step {step.step_id}: {step.description}")

        try:
            result = await self._call_tool(step.tool, step.arguments)

            verification_passed = True
            verification_details = ""

            if step.verification and result.success:
                verification_passed, verification_details = await self._verify_step(step, result)

            return ExecutionResult(
                step_id=step.step_id,
                success=result.success,
                output=result.content,
                error=result.error,
                verification_passed=verification_passed,
                verification_details=verification_details
            )

        except Exception as e:
            logger.error(f"Step {step.step_id} failed with exception: {e}")
            return ExecutionResult(
                step_id=step.step_id,
                success=False,
                error=str(e)
            )

    async def _call_tool(self, tool: str, arguments: Dict[str, Any]) -> MCPResult:
        if "project_path" not in arguments:
            arguments["project_path"] = self.project_path

        return await self.mcp_client.call_tool(tool, arguments)

    async def _verify_step(self, step: PlanStep, result: MCPResult) -> tuple[bool, str]:
        if step.verification is None:
            return True, "No verification required"

        if step.tool == "run_erc":
            if result.success and result.content:
                erc_data = result.content
                passed = erc_data.get("passed", False)
                return passed, f"ERC {'passed' if passed else 'failed'}"

        elif step.tool == "run_drc":
            if result.success and result.content:
                drc_data = result.content
                passed = drc_data.get("passed", False)
                return passed, f"DRC {'passed' if passed else 'failed'}"

        elif step.tool == "run_spice":
            if result.success and result.content:
                spice_data = result.content
                success = spice_data.get("success", False)
                return success, f"SPICE {'converged' if success else 'failed'}"

        elif step.tool == "route_pcb":
            if result.success and result.content:
                route_data = result.content
                success = route_data.get("success", False)
                return success, f"Routing {'succeeded' if success else 'failed'}"

        return True, "Verification passed (generic)"

    async def _attempt_recovery(self, step: PlanStep, result: ExecutionResult) -> ExecutionResult:
        logger.info(f"Attempting recovery for step {step.step_id}")

        if "position" in step.arguments:
            modified_args = step.arguments.copy()
            pos = modified_args.get("position", {"x": 100, "y": 100})
            pos["x"] += 20
            pos["y"] += 20
            modified_args["position"] = pos

            return await self._call_tool(step.tool, modified_args)

        return ExecutionResult(step_id=step.step_id, success=False, error="Recovery not implemented")

    async def _verify_execution(self, execution: AgentExecution) -> None:
        logger.info("Verifying execution...")

        all_passed = all(r.success for r in execution.execution_results)

        if not all_passed:
            failed = [r for r in execution.execution_results if not r.success]
            logger.warning(f"Verification: {len(failed)} steps failed")
        else:
            logger.info("Verification: All steps passed")

    async def _run_integration_pipeline(self, execution: AgentExecution) -> None:
        logger.info("Running integration pipeline...")

        request = DesignRequest(
            prompt=execution.goal.description,
            project_name="ai_agent_design",
            run_spice=True,
            run_routing=True
        )

        summary = await asyncio.get_event_loop().run_in_executor(
            None,
            self.orchestrator.process_request,
            request,
            Path(self.project_path)
        )

        execution.execution_results.append(ExecutionResult(
            step_id=999,
            success=summary.erc_report.passed,
            output=summary.to_dict()
        ))


async def create_ai_design_agent(
    project_path: str,
    mcp_command: str = "python",
    mcp_args: List[str] = None,
    mcp_cwd: str = None
) -> AIDesignAgent:

    async with create_mcp_client(
        command=mcp_command,
        args=mcp_args or ["-m", "kicad_mcp_server"],
        cwd=mcp_cwd
    ) as mcp_client:
        agent = AIDesignAgent(mcp_client, project_path)
        yield agent
