"""
MCP Client for KiCad MCP Server Integration.

Provides async client for communicating with KiCad MCP server via stdio transport.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from contextlib import asynccontextmanager
import shlex

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents an MCP tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPResource:
    """Represents an MCP resource."""
    uri: str
    name: str
    description: str
    mime_type: str


@dataclass
class MCPResult:
    """Result of an MCP tool call."""
    success: bool
    content: Any = None
    error: Optional[str] = None
    is_error: bool = False


class MCPClient:
    """
    Async MCP client using stdio transport.
    
    Communicates with MCP server (e.g., kicad-mcp-server) via JSON-RPC 2.0
    over stdin/stdout.
    """
    
    def __init__(
        self,
        command: str,
        args: List[str] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ):
        self.command = command
        self.args = args or []
        self.cwd = cwd
        self.env = env or {}
        self.timeout = timeout
        
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tools: List[MCPTool] = []
        self._resources: List[MCPResource] = []
        self._initialized = False
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._notification_handlers: Dict[str, List[Callable]] = {}
    
    @property
    def tools(self) -> List[MCPTool]:
        return self._tools
    
    @property
    def resources(self) -> List[MCPResource]:
        return self._resources
    
    @property
    def initialized(self) -> bool:
        return self._initialized
    
    async def start(self) -> None:
        """Start the MCP server process and initialize connection."""
        if self._process is not None:
            return
        
        cmd = [self.command] + self.args
        logger.info(f"Starting MCP server: {' '.join(shlex.quote(c) for c in cmd)}")
        
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env={**os.environ, **self.env}
        )
        
        # Start stderr reader
        asyncio.create_task(self._read_stderr())
        
        # Start stdout reader
        asyncio.create_task(self._read_stdout())
        
        # Initialize
        await self.initialize()
    
    async def initialize(self) -> None:
        """Initialize MCP connection with handshake."""
        # Send initialize request
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "clientInfo": {
                "name": "ai-electronics-design-platform",
                "version": "0.1.0"
            }
        })
        
        if result.success:
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            self._initialized = True
            
            # List available tools
            await self.list_tools()
            await self.list_resources()
            
            logger.info(f"MCP client initialized with {len(self._tools)} tools")
        else:
            raise RuntimeError(f"MCP initialization failed: {result.error}")
    
    async def list_tools(self) -> List[MCPTool]:
        """List available tools from MCP server."""
        result = await self._send_request("tools/list", {})
        
        if result.success:
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {})
                )
                for t in result.content.get("tools", [])
            ]
        else:
            logger.warning(f"Failed to list tools: {result.error}")
        
        return self._tools
    
    async def list_resources(self) -> List[MCPResource]:
        """List available resources from MCP server."""
        result = await self._send_request("resources/list", {})
        
        if result.success:
            self._resources = [
                MCPResource(
                    uri=r["uri"],
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    mime_type=r.get("mimeType", "")
                )
                for r in result.content.get("resources", [])
            ]
        
        return self._resources
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPResult:
        """Call an MCP tool."""
        if not self._initialized:
            return MCPResult(success=False, error="MCP client not initialized")
        
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        if result.success:
            return MCPResult(success=True, content=result.content)
        else:
            return MCPResult(success=False, error=result.error, is_error=result.is_error)
    
    async def read_resource(self, uri: str) -> MCPResult:
        """Read an MCP resource."""
        if not self._initialized:
            return MCPResult(success=False, error="MCP client not initialized")
        
        result = await self._send_request("resources/read", {"uri": uri})
        
        if result.success:
            return MCPResult(success=True, content=result.content)
        else:
            return MCPResult(success=False, error=result.error, is_error=result.is_error)
    
    async def subscribe_resource(self, uri: str) -> MCPResult:
        """Subscribe to resource updates."""
        return await self._send_request("resources/subscribe", {"uri": uri})
    
    async def unsubscribe_resource(self, uri: str) -> MCPResult:
        """Unsubscribe from resource updates."""
        return await self._send_request("resources/unsubscribe", {"uri": uri})
    
    def on_notification(self, method: str, handler: Callable[[Dict], None]) -> None:
        """Register notification handler."""
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)
    
    async def close(self) -> None:
        """Close the MCP connection."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None
            self._initialized = False
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> MCPResult:
        """Send JSON-RPC request and wait for response."""
        self._request_id += 1
        request_id = self._request_id
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.Future()
        self._pending_requests[request_id] = future
        
        try:
            await self._send_json(request)
            response = await asyncio.wait_for(future, timeout=self.timeout)
            return response
        except asyncio.TimeoutError:
            return MCPResult(success=False, error=f"Request timeout after {self.timeout}s")
        finally:
            self._pending_requests.pop(request_id, None)
    
    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        await self._send_json(notification)
    
    async def _send_json(self, data: Dict[str, Any]) -> None:
        """Send JSON data to stdin."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Process not running")
        
        line = json.dumps(data) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()
    
    async def _read_stdout(self) -> None:
        """Read responses from stdout."""
        if not self._process or not self._process.stdout:
            return
        
        async for line in self._process.stdout:
            line = line.decode().strip()
            if not line:
                continue
            
            try:
                message = json.loads(line)
                
                if "id" in message and message["id"] in self._pending_requests:
                    # Response to a request
                    future = self._pending_requests.pop(message["id"])
                    if not future.done():
                        if "error" in message:
                            future.set_result(MCPResult(
                                success=False,
                                error=message["error"].get("message", "Unknown error"),
                                is_error=True
                            ))
                        else:
                            future.set_result(MCPResult(
                                success=True,
                                content=message.get("result")
                            ))
                elif "method" in message:
                    # Notification
                    await self._handle_notification(message)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse MCP response: {e}")
    
    async def _read_stderr(self) -> None:
        """Read and log stderr from MCP server."""
        if not self._process or not self._process.stderr:
            return
        
        async for line in self._process.stderr:
            line = line.decode().strip()
            if line:
                logger.debug(f"MCP stderr: {line}")
    
    async def _handle_notification(self, message: Dict[str, Any]) -> None:
        """Handle incoming notification."""
        method = message.get("method")
        params = message.get("params", {})
        
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                handler(params)
            except Exception as e:
                logger.error(f"Notification handler error: {e}")


import os


@asynccontextmanager
async def create_mcp_client(
    command: str = "python",
    args: List[str] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> MCPClient:
    """Context manager for MCP client lifecycle."""
    client = MCPClient(command=command, args=args or [], cwd=cwd, env=env)
    try:
        await client.start()
        yield client
    finally:
        await client.close()


# Convenience functions for common KiCad MCP operations
class KiCadMCPTools:
    """High-level KiCad MCP tool wrappers."""
    
    def __init__(self, client: MCPClient):
        self.client = client
    
    # Schematic tools
    async def list_schematic_components(self, project_path: str, **filters) -> MCPResult:
        return await self.client.call_tool("list_schematic_components", {
            "project_path": project_path,
            **filters
        })
    
    async def list_schematic_nets(self, project_path: str, power_only: bool = False) -> MCPResult:
        return await self.client.call_tool("list_schematic_nets", {
            "project_path": project_path,
            "power_only": power_only
        })
    
    async def get_schematic_info(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("get_schematic_info", {
            "project_path": project_path
        })
    
    async def search_symbols(self, project_path: str, pattern: str) -> MCPResult:
        return await self.client.call_tool("search_symbols", {
            "project_path": project_path,
            "pattern": pattern
        })
    
    async def get_symbol_details(self, project_path: str, component_ref: str) -> MCPResult:
        return await self.client.call_tool("get_symbol_details", {
            "project_path": project_path,
            "component_ref": component_ref
        })
    
    # PCB tools
    async def list_pcb_footprints(self, project_path: str, layer: str = None) -> MCPResult:
        args = {"project_path": project_path}
        if layer:
            args["layer"] = layer
        return await self.client.call_tool("list_pcb_footprints", args)
    
    async def get_pcb_statistics(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("get_pcb_statistics", {
            "project_path": project_path
        })
    
    async def find_tracks_by_net(self, project_path: str, net_name: str) -> MCPResult:
        return await self.client.call_tool("find_tracks_by_net", {
            "project_path": project_path,
            "net_name": net_name
        })
    
    async def analyze_pcb_nets(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("analyze_pcb_nets", {
            "project_path": project_path
        })
    
    async def analyze_pcb_signal_integrity(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("analyze_pcb_signal_integrity", {
            "project_path": project_path
        })
    
    async def analyze_pcb_power_integrity(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("analyze_pcb_power_integrity", {
            "project_path": project_path
        })
    
    # Netlist tools
    async def generate_netlist(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("generate_netlist", {
            "project_path": project_path
        })
    
    async def trace_netlist_connection(self, project_path: str, component_ref: str) -> MCPResult:
        return await self.client.call_tool("trace_netlist_connection", {
            "project_path": project_path,
            "component_ref": component_ref
        })
    
    async def get_netlist_nets(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("get_netlist_nets", {
            "project_path": project_path
        })
    
    # Validation
    async def run_erc(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("run_erc", {
            "project_path": project_path
        })
    
    async def run_drc(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("run_drc", {
            "project_path": project_path
        })
    
    async def detect_pin_conflicts(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("detect_pin_conflicts", {
            "project_path": project_path
        })
    
    # Project editing
    async def create_kicad_project(self, project_path: str, template: str = None) -> MCPResult:
        args = {"project_path": project_path}
        if template:
            args["template"] = template
        return await self.client.call_tool("create_kicad_project", args)
    
    async def add_component_from_library(self, project_path: str, lib_id: str, reference: str, value: str, position: Dict[str, float] = None) -> MCPResult:
        args = {
            "project_path": project_path,
            "lib_id": lib_id,
            "reference": reference,
            "value": value
        }
        if position:
            args["position"] = position
        return await self.client.call_tool("add_component_from_library", args)
    
    async def add_wire(self, project_path: str, start: Dict[str, float], end: Dict[str, float]) -> MCPResult:
        return await self.client.call_tool("add_wire", {
            "project_path": project_path,
            "start": start,
            "end": end
        })
    
    async def add_label(self, project_path: str, label: str, position: Dict[str, float]) -> MCPResult:
        return await self.client.call_tool("add_label", {
            "project_path": project_path,
            "label": label,
            "position": position
        })
    
    async def setup_pcb_layout(self, project_path: str, width: float, height: float) -> MCPResult:
        return await self.client.call_tool("setup_pcb_layout", {
            "project_path": project_path,
            "width": width,
            "height": height
        })
    
    async def export_gerber(self, project_path: str, output_dir: str) -> MCPResult:
        return await self.client.call_tool("export_gerber", {
            "project_path": project_path,
            "output_dir": output_dir
        })
    
    # Pin analysis and code generation
    async def analyze_pin_functions(self, project_path: str, component_ref: str) -> MCPResult:
        return await self.client.call_tool("analyze_pin_functions", {
            "project_path": project_path,
            "component_ref": component_ref
        })
    
    async def detect_pin_conflicts(self, project_path: str) -> MCPResult:
        return await self.client.call_tool("detect_pin_conflicts", {
            "project_path": project_path
        })
    
    async def generate_device_tree(self, project_path: str, component_ref: str) -> MCPResult:
        return await self.client.call_tool("generate_device_tree", {
            "project_path": project_path,
            "component_ref": component_ref
        })
    
    async def generate_pytest_tests(self, project_path: str, component_ref: str = None) -> MCPResult:
        args = {"project_path": project_path}
        if component_ref:
            args["component_ref"] = component_ref
        return await self.client.call_tool("generate_pytest_tests", args)
    
    # Parts registry
    async def search_parts(self, query: str, limit: int = 10) -> MCPResult:
        return await self.client.call_tool("search_parts", {
            "query": query,
            "limit": limit
        })
    
    async def get_part_details(self, part_id: str) -> MCPResult:
        return await self.client.call_tool("get_part_details", {
            "part_id": part_id
        })
    
    async def download_part_assets(self, part_id: str, project_path: str) -> MCPResult:
        return await self.client.call_tool("download_part_assets", {
            "part_id": part_id,
            "project_path": project_path
        })