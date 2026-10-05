"""
Sandboxing and Isolation for AI Agent Execution.

Provides process isolation, resource limits, and safe execution environment
for AI agent operations and MCP tool calls.
"""

import asyncio
import os
import resource
import tempfile
import shutil
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from contextlib import asynccontextmanager
import logging
import json

from src.security.permissions import Permission

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed execution."""
    max_cpu_time: int = 30  # seconds
    max_memory: int = 512 * 1024 * 1024  # 512 MB
    max_file_size: int = 10 * 1024 * 1024  # 10 MB
    max_open_files: int = 100
    max_processes: int = 10
    max_total_size: int = 100 * 1024 * 1024  # 100 MB total workspace


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    work_dir: Optional[Path] = None
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    allowed_paths: Set[Path] = field(default_factory=set)
    blocked_paths: Set[Path] = field(default_factory=set)
    allowed_commands: Set[str] = field(default_factory=set)
    blocked_commands: Set[str] = field(default_factory=set)
    network_allowed: bool = False
    env_vars: Dict[str, str] = field(default_factory=dict)
    cleanup_on_exit: bool = True


@dataclass
class ExecutionResult:
    """Result of sandboxed execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    execution_time: float = 0.0
    peak_memory: int = 0
    error: Optional[str] = None
    files_created: List[Path] = field(default_factory=list)
    files_modified: List[Path] = field(default_factory=list)


class Sandbox:
    """Process sandbox with resource limits and path isolation."""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._temp_dir: Optional[Path] = None
        self._original_cwd: Optional[Path] = None
        self._original_env: Dict[str, str] = {}
        self._child_pids: List[int] = []
    
    async def __aenter__(self) -> 'Sandbox':
        await self._setup()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._cleanup()
    
    async def _setup(self) -> None:
        """Set up sandbox environment."""
        # Create working directory
        if self.config.work_dir:
            self._temp_dir = self.config.work_dir
            self._temp_dir.mkdir(parents=True, exist_ok=True)
        elif self.config.allowed_paths:
            # Create temp directory within the first allowed path
            first_allowed = next(iter(self.config.allowed_paths))
            self._temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_", dir=first_allowed))
        else:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_"))
        
        # Save original state
        self._original_cwd = Path.cwd()
        self._original_env = dict(os.environ)
        
        # Change to sandbox directory
        os.chdir(self._temp_dir)
        
        # Set up environment
        os.environ.update(self.config.env_vars)
        
        # Apply resource limits
        self._apply_resource_limits()
        
        # Set up path restrictions
        self._setup_path_restrictions()
        
        logger.info(f"Sandbox initialized at {self._temp_dir}")
    
    def _apply_resource_limits(self) -> None:
        """Resource limits are applied to child processes via preexec_fn, not to parent."""
        # Resource limits are applied to child processes via preexec_fn
        # to avoid affecting the parent process
        pass
    
    def _setup_path_restrictions(self) -> None:
        """Set up path access restrictions using a wrapper."""
        # We'll enforce path restrictions at the Python level
        # For full isolation, would need seccomp or container
        pass
    
    def _check_path_allowed(self, path: Path) -> bool:
        """Check if a path is allowed for access."""
        try:
            path = path.resolve()
            
            # Check blocked paths first
            for blocked in self.config.blocked_paths:
                try:
                    if path.is_relative_to(blocked.resolve()):
                        return False
                except ValueError:
                    pass  # Paths on different drives (Windows)
            
            # If allowed paths specified, must be in one of them
            if self.config.allowed_paths:
                allowed = False
                for allowed_path in self.config.allowed_paths:
                    try:
                        if path.is_relative_to(allowed_path.resolve()):
                            allowed = True
                            break
                    except ValueError:
                        pass
                if not allowed:
                    return False
            
            return True
        except Exception:
            return False
    
    def _check_command_allowed(self, command: str) -> bool:
        """Check if a command is allowed to execute."""
        cmd_name = command.split()[0] if command else ""
        
        if self.config.blocked_commands and cmd_name in self.config.blocked_commands:
            return False
        
        if self.config.allowed_commands and cmd_name not in self.config.allowed_commands:
            return False
        
        return True
    
    async def execute(self, command: str, args: List[str] = None, 
                      env: Dict[str, str] = None, timeout: float = None,
                      cwd: Optional[Path] = None) -> ExecutionResult:
        """Execute a command in the sandbox."""
        if not self._check_command_allowed(command):
            return ExecutionResult(
                success=False,
                error=f"Command not allowed: {command}"
            )
        
        # Prepare environment
        exec_env = dict(os.environ)
        if env:
            exec_env.update(env)
        
        # Working directory
        work_dir = cwd or self._temp_dir
        if not self._check_path_allowed(Path(work_dir)):
            return ExecutionResult(
                success=False,
                error=f"Working directory not allowed: {work_dir}"
            )
        
        # Execute with timeout
        timeout_val = timeout or 30.0
        start_time = asyncio.get_event_loop().time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                command, *(args or []),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env=exec_env,
                preexec_fn=self._set_child_limits if hasattr(os, 'fork') else None
            )
            
            self._child_pids.append(process.pid)
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    execution_time=asyncio.get_event_loop().time() - start_time
                )
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Collect created/modified files
            files_created, files_modified = self._scan_files()
            
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                return_code=process.returncode,
                execution_time=execution_time,
                files_created=files_created,
                files_modified=files_modified
            )
            
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start_time
            )
        finally:
            # Safely remove process from child_pids if it was created
            if 'process' in locals() and hasattr(process, 'pid') and process.pid in self._child_pids:
                self._child_pids.remove(process.pid)
    
    def _set_child_limits(self) -> None:
        """Set resource limits for child process (Unix only)."""
        # This runs in the child process after fork
        try:
            limits = self.config.resource_limits
            resource.setrlimit(resource.RLIMIT_CPU, 
                             (limits.max_cpu_time, limits.max_cpu_time + 5))
            resource.setrlimit(resource.RLIMIT_AS, 
                             (limits.max_memory, limits.max_memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, 
                             (limits.max_file_size, limits.max_file_size))
        except Exception:
            pass  # Ignore if not supported
    
    def _scan_files(self) -> tuple:
        """Scan for created/modified files in sandbox."""
        created = []
        modified = []
        
        # This would need a baseline snapshot to be accurate
        # For now, return empty lists
        return created, modified
    
    def read_file(self, path: Path) -> Optional[str]:
        """Safely read a file within sandbox."""
        full_path = (self._temp_dir / path).resolve()
        if not self._check_path_allowed(full_path):
            raise PermissionError(f"Access denied: {path}")
        if full_path.exists() and full_path.is_file():
            return full_path.read_text()
        return None
    
    def write_file(self, path: Path, content: str) -> bool:
        """Safely write a file within sandbox."""
        full_path = (self._temp_dir / path).resolve()
        if not self._check_path_allowed(full_path):
            raise PermissionError(f"Access denied: {path}")
        
        # Check file size limit
        if len(content.encode()) > self.config.resource_limits.max_file_size:
            raise ValueError("File size exceeds limit")
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return True
    
    def list_files(self, path: Path = None) -> List[Path]:
        """List files in sandbox directory."""
        target = (self._temp_dir / path).resolve() if path else self._temp_dir
        if not self._check_path_allowed(target):
            raise PermissionError(f"Access denied: {path}")
        if target.exists() and target.is_dir():
            return [p.relative_to(self._temp_dir) for p in target.rglob("*")]
        return []
    
    async def _cleanup(self) -> None:
        """Clean up sandbox resources."""
        # Kill any remaining child processes
        for pid in self._child_pids:
            try:
                os.kill(pid, 9)  # SIGKILL
            except ProcessLookupError:
                pass
        
        # Restore original state
        if self._original_cwd:
            os.chdir(self._original_cwd)
        os.environ.clear()
        os.environ.update(self._original_env)
        
        # Clean up temp directory
        if self.config.cleanup_on_exit and self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup sandbox: {e}")
        
        logger.info("Sandbox cleaned up")


class RestrictedFileSystem:
    """Wrapper providing restricted file system access."""
    
    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox
    
    def read(self, path: Path) -> Optional[str]:
        return self.sandbox.read_file(path)
    
    def write(self, path: Path, content: str) -> bool:
        return self.sandbox.write_file(path, content)
    
    def list(self, path: Path = None) -> List[Path]:
        return self.sandbox.list_files(path)
    
    def exists(self, path: Path) -> bool:
        full_path = (self.sandbox._temp_dir / path).resolve()
        if not self.sandbox._check_path_allowed(full_path):
            return False
        return full_path.exists()
    
    def is_file(self, path: Path) -> bool:
        full_path = (self.sandbox._temp_dir / path).resolve()
        if not self.sandbox._check_path_allowed(full_path):
            return False
        return full_path.is_file()
    
    def is_dir(self, path: Path) -> bool:
        full_path = (self.sandbox._temp_dir / path).resolve()
        if not self.sandbox._check_path_allowed(full_path):
            return False
        return full_path.is_dir()


# MCP Tool Sandbox Wrapper
class MCPSandboxWrapper:
    """Wraps MCP client calls with sandbox isolation."""
    
    def __init__(self, mcp_client, sandbox: Sandbox):
        self.mcp_client = mcp_client
        self.sandbox = sandbox
        self.fs = RestrictedFileSystem(sandbox)
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute MCP tool call with sandbox isolation."""
        # Check if tool is allowed
        if not self._is_tool_allowed(tool_name):
            raise PermissionError(f"Tool not allowed: {tool_name}")
        
        # Sanitize arguments
        safe_args = self._sanitize_arguments(tool_name, arguments)
        
        # Execute tool call
        return await self.mcp_client.call_tool(tool_name, safe_args)
    
    def _is_tool_allowed(self, tool_name: str) -> bool:
        """Check if MCP tool is allowed."""
        # Default: allow all KiCad tools
        allowed_prefixes = [
            "list_", "get_", "search_", "trace_", "generate_",
            "run_", "analyze_", "create_", "add_", "setup_",
            "export_", "detect_", "generate_", "search_", "download_"
        ]
        return any(tool_name.startswith(prefix) for prefix in allowed_prefixes)
    
    def _sanitize_arguments(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize tool arguments for safety."""
        safe_args = {}
        for key, value in args.items():
            if isinstance(value, str):
                # Sanitize paths
                if "path" in key.lower() or "dir" in key.lower():
                    # Ensure path is within sandbox
                    safe_args = self._sanitize_path(value)
                    safe_args[key] = safe_args
                else:
                    safe_args[key] = value
            elif isinstance(value, (int, float, bool)):
                safe_args[key] = value
            elif isinstance(value, dict):
                safe_args[key] = self._sanitize_arguments(tool_name, value)
            elif isinstance(value, list):
                safe_args[key] = [self._sanitize_arguments(tool_name, v) if isinstance(v, dict) else v 
                                  for v in value]
            else:
                safe_args[key] = value
        return safe_args
    
    def _sanitize_path(self, path: str) -> str:
        """Ensure path is within sandbox."""
        try:
            p = Path(path).resolve()
            if self.sandbox._check_path_allowed(p):
                return str(p.relative_to(self.sandbox._temp_dir))
        except Exception:
            pass
        # Return a safe default
        return Path(path).name


# Factory for creating secure execution environments
class SecureExecutor:
    """High-level secure executor combining permissions and sandboxing."""
    
    def __init__(self, permission_manager, sandbox_config: Optional[SandboxConfig] = None):
        self.permissions = permission_manager
        self.sandbox = Sandbox(sandbox_config)
        self.mcp_wrapper: Optional[MCPSandboxWrapper] = None
    
    async def __aenter__(self):
        await self.sandbox.__aenter__()
        self.mcp_wrapper = MCPSandboxWrapper(None, self.sandbox)  # Set MCP client later
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.sandbox.__aexit__(None, None, None)
    
    def set_mcp_client(self, client):
        """Set MCP client for tool execution."""
        self.mcp_wrapper = MCPSandboxWrapper(client, self.sandbox)
    
    async def execute_tool(self, principal_id: str, tool: str, 
                          arguments: Dict[str, Any]) -> Any:
        """Execute a tool with permission check and sandbox isolation."""
        # Check permissions
        tool_permission = Permission.EXECUTE_MCP_TOOL  # Generic tool execution permission
        self.permissions.require_permission(principal_id, tool_permission)
        
        # Execute via sandboxed MCP wrapper
        if not self.mcp_wrapper:
            raise RuntimeError("MCP client not set")
        
        return await self.mcp_wrapper.call_tool(tool, arguments)
    
    def get_filesystem(self) -> RestrictedFileSystem:
        return self.sandbox.fs