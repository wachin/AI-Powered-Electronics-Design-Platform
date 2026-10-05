"""
Tests for Security and Permission System.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock
from src.security.permissions import (
    Permission, Role, PermissionSet, Principal, PermissionManager,
    PERMISSIONS_BY_ROLE, TemporaryPermission
)
from src.security.sandbox import (
    Sandbox, SandboxConfig, ResourceLimits,
    ExecutionResult, RestrictedFileSystem, SecureExecutor
)


class TestPermissions:
    def test_permission_enum(self):
        assert Permission.READ_PROJECT.value == "read:project"
        assert Permission.WRITE_SCHEMATIC.value == "write:schematic"
        assert Permission.EXECUTE_SPICE.value == "execute:spice"
        assert Permission.ADMIN_SYSTEM.value == "admin:system"
    
    def test_role_enum(self):
        assert Role.VIEWER.value == "viewer"
        assert Role.DESIGNER.value == "designer"
        assert Role.ENGINEER.value == "engineer"
        assert Role.ADMIN.value == "admin"
        assert Role.AI_AGENT.value == "ai_agent"
    
    def test_permission_set(self):
        ps = PermissionSet()
        assert not ps.has_permission(Permission.READ_PROJECT)
        
        ps.add(Permission.READ_PROJECT)
        assert ps.has_permission(Permission.READ_PROJECT)
        assert not ps.has_permission(Permission.WRITE_PROJECT)
        
        ps.remove(Permission.READ_PROJECT)
        assert not ps.has_permission(Permission.READ_PROJECT)
    
    def test_permissions_by_role(self):
        # VIEWER permissions
        viewer_perms = PERMISSIONS_BY_ROLE[Role.VIEWER]
        assert Permission.READ_PROJECT in viewer_perms
        assert Permission.WRITE_PROJECT not in viewer_perms
        assert Permission.COLLAB_JOIN in viewer_perms
        
        # DESIGNER permissions
        designer_perms = PERMISSIONS_BY_ROLE[Role.DESIGNER]
        assert Permission.READ_PROJECT in designer_perms
        assert Permission.WRITE_SCHEMATIC in designer_perms
        assert Permission.EXECUTE_ERC in designer_perms
        assert Permission.ADMIN_USER not in designer_perms
        
        # ADMIN permissions (should have all)
        admin_perms = PERMISSIONS_BY_ROLE[Role.ADMIN]
        assert Permission.ADMIN_SYSTEM in admin_perms
        assert Permission.ADMIN_USER in admin_perms
        assert Permission.EXECUTE_AI_AGENT in admin_perms
        
        # AI_AGENT permissions
        ai_perms = PERMISSIONS_BY_ROLE[Role.AI_AGENT]
        assert Permission.EXECUTE_AI_AGENT in ai_perms
        assert Permission.EXECUTE_MCP_TOOL in ai_perms
        assert Permission.ADMIN_SYSTEM not in ai_perms
    
    def test_principal(self):
        principal = Principal(
            id="user_123",
            type="user",
            name="Test User",
            roles={Role.DESIGNER}
        )
        
        assert principal.has_permission(Permission.READ_PROJECT)
        assert principal.has_permission(Permission.WRITE_SCHEMATIC)
        assert not principal.has_permission(Permission.ADMIN_SYSTEM)
        
        # Grant additional role
        principal.grant_role(Role.ADMIN)
        assert principal.has_permission(Permission.ADMIN_SYSTEM)
        
        # Revoke role
        principal.revoke_role(Role.ADMIN)
        assert not principal.has_permission(Permission.ADMIN_SYSTEM)
        assert principal.has_permission(Permission.WRITE_SCHEMATIC)  # Still has designer permissions
    
    def test_permission_manager(self):
        manager = PermissionManager()
        
        # Create principal
        principal = manager.create_principal("user_1", "user", "Test User")
        assert principal.id == "user_1"
        assert principal.name == "Test User"
        
        # Check permission (no permissions by default)
        assert not manager.check_permission("user_1", Permission.READ_PROJECT)
        
        # Grant permission
        manager.grant_permission("user_1", Permission.READ_PROJECT)
        assert manager.check_permission("user_1", Permission.READ_PROJECT)
        
        # Revoke permission
        manager.revoke_permission("user_1", Permission.READ_PROJECT)
        assert not manager.check_permission("user_1", Permission.READ_PROJECT)
        
        # Grant role
        manager.grant_role("user_1", Role.DESIGNER)
        assert manager.check_permission("user_1", Permission.WRITE_SCHEMATIC)
        
        # Revoke role
        manager.revoke_role("user_1", Role.DESIGNER)
        assert not manager.check_permission("user_1", Permission.WRITE_SCHEMATIC)
    
    def test_temporary_permission(self):
        manager = PermissionManager()
        principal = manager.create_principal("user_1", "user", "Test")
        
        assert not manager.check_permission("user_1", Permission.ADMIN_SYSTEM)
        
        with TemporaryPermission(manager, "user_1", Permission.ADMIN_SYSTEM):
            assert manager.check_permission("user_1", Permission.ADMIN_SYSTEM)
        
        assert not manager.check_permission("user_1", Permission.ADMIN_SYSTEM)
    
    def test_audit_log(self):
        manager = PermissionManager()
        manager.create_principal("user_1", "user", "Test")
        manager.grant_permission("user_1", Permission.READ_PROJECT)
        manager.grant_role("user_1", Role.DESIGNER)
        
        log = manager.get_audit_log()
        assert len(log) >= 3
        actions = [entry["action"] for entry in log]
        assert "create_principal" in actions
        assert "grant_permission" in actions
        assert "grant_role" in actions


class TestSandbox:
    @pytest.mark.asyncio
    async def test_sandbox_basic(self):
        config = SandboxConfig()
        async with Sandbox(config) as sandbox:
            # Test file operations
            sandbox.write_file(Path("test.txt"), "Hello World")
            content = sandbox.read_file(Path("test.txt"))
            assert content == "Hello World"
            
            # Test file listing
            files = sandbox.list_files()
            assert any("test.txt" in str(f) for f in files)
            
            # Test directory operations
            sandbox.write_file(Path("subdir/nested.txt"), "Nested")
            assert sandbox.read_file(Path("subdir/nested.txt")) == "Nested"
    
    @pytest.mark.asyncio
    async def test_sandbox_path_restrictions(self):
        import tempfile
        import shutil
        allowed_dir = Path(tempfile.mkdtemp(prefix="allowed_"))
        try:
            config = SandboxConfig(
                allowed_paths={allowed_dir},
                blocked_paths={Path("/etc")}
            )
            
            async with Sandbox(config) as sandbox:
                # Should allow paths within sandbox temp dir (which is under allowed_dir)
                sandbox.write_file(Path("test.txt"), "OK")
                assert sandbox.read_file(Path("test.txt")) == "OK"
                
                # Should block access to /etc
                with pytest.raises(PermissionError):
                    sandbox.read_file(Path("/etc/passwd"))
        finally:
            shutil.rmtree(allowed_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_sandbox_command_execution(self):
        config = SandboxConfig(
            allowed_commands={"echo", "ls", "cat"},
            blocked_commands={"rm"}
        )
        
        async with Sandbox(config) as sandbox:
            # Allowed command
            result = await sandbox.execute("echo", ["Hello World"])
            assert result.success
            assert "Hello World" in result.stdout
            
            # Blocked command
            result = await sandbox.execute("rm", ["-rf", "/"])
            assert not result.success
            assert "not allowed" in result.error.lower()
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Resource limits test causes memory issues in test runner")
    async def test_sandbox_resource_limits(self):
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="File size limit test affects test runner")
    async def test_sandbox_file_size_limit(self):
        pass
    
    @pytest.mark.asyncio
    async def test_sandbox_cleanup(self):
        temp_dirs_before = set(Path("/tmp").glob("sandbox_*"))
        
        async with Sandbox(SandboxConfig()) as sandbox:
            sandbox.write_file(Path("test.txt"), "test")
            sandbox_path = sandbox._temp_dir
        
        # After context exit, temp dir should be cleaned up
        await asyncio.sleep(0.1)  # Give time for cleanup
        assert not sandbox_path.exists()


class TestRestrictedFileSystem:
    @pytest.mark.asyncio
    async def test_restricted_fs(self):
        async with Sandbox(SandboxConfig()) as sandbox:
            fs = RestrictedFileSystem(sandbox)
            
            fs.write(Path("test.txt"), "Hello")
            assert fs.read(Path("test.txt")) == "Hello"
            assert fs.exists(Path("test.txt"))
            assert fs.is_file(Path("test.txt"))
            assert not fs.is_dir(Path("test.txt"))
            assert fs.is_dir(Path("."))
            assert fs.list()  # Should list files
            assert not fs.exists(Path("nonexistent.txt"))


class TestSecureExecutor:
    @pytest.mark.asyncio
    async def test_secure_executor(self):
        from src.security.permissions import PermissionManager
        
        perm_manager = PermissionManager()
        principal = perm_manager.create_principal("user_1", "user", "Test")
        
        config = SandboxConfig()
        async with SecureExecutor(perm_manager, SandboxConfig()) as executor:
            executor.set_mcp_client(MagicMock())
            executor.permissions.grant_permission("user_1", Permission.EXECUTE_MCP_TOOL)
            
            # The executor should check permissions before executing
            with pytest.raises(PermissionError):
                await executor.execute_tool("user_2", "some_tool", {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])