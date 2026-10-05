"""
Security and Permission System for AI-Powered Electronics Design Platform.

Implements capability-based permission system for AI agents and users.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Fine-grained permissions for the platform."""
    # Read permissions
    READ_PROJECT = "read:project"
    READ_SCHEMATIC = "read:schematic"
    READ_PCB = "read:pcb"
    READ_BOM = "read:bom"
    READ_COMPONENT_DB = "read:component_db"
    READ_DATASHEET = "read:datasheet"
    READ_SIMULATION = "read:simulation"
    READ_3D_MODEL = "read:3d_model"
    
    # Write permissions
    WRITE_PROJECT = "write:project"
    WRITE_SCHEMATIC = "write:schematic"
    WRITE_PCB = "write:pcb"
    WRITE_BOM = "write:bom"
    WRITE_COMPONENT = "write:component"
    
    # Execution permissions
    EXECUTE_ERC = "execute:erc"
    EXECUTE_DRC = "execute:drc"
    EXECUTE_SPICE = "execute:spice"
    EXECUTE_ROUTING = "execute:routing"
    EXECUTE_3D_EXPORT = "execute:3d_export"
    EXECUTE_MCP_TOOL = "execute:mcp_tool"
    EXECUTE_AI_AGENT = "execute:ai_agent"
    
    # Administrative permissions
    ADMIN_USER = "admin:user"
    ADMIN_PROJECT = "admin:project"
    ADMIN_SYSTEM = "admin:system"
    
    # Collaboration permissions
    COLLAB_JOIN = "collab:join"
    COLLAB_INVITE = "collab:invite"
    COLLAB_EDIT = "collab:edit"
    COLLAB_ADMIN = "collab:admin"


class Role(Enum):
    """Predefined roles with permission sets."""
    VIEWER = "viewer"
    DESIGNER = "designer"
    ENGINEER = "engineer"
    ADMIN = "admin"
    AI_AGENT = "ai_agent"


@dataclass
class PermissionSet:
    """A set of permissions with metadata."""
    permissions: Set[Permission] = field(default_factory=set)
    granted_at: datetime = field(default_factory=datetime.utcnow)
    granted_by: Optional[str] = None
    expires_at: Optional[datetime] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    def has_permission(self, perm: Permission) -> bool:
        if perm in self.permissions:
            if self.expires_at and datetime.utcnow() > self.expires_at:
                return False
            return True
        return False
    
    def add(self, perm: Permission, granted_by: str = None) -> None:
        self.permissions.add(perm)
        self.granted_by = granted_by
    
    def remove(self, perm: Permission) -> None:
        self.permissions.discard(perm)


@dataclass
class Principal:
    """A user, AI agent, or service that can have permissions."""
    id: str
    type: str  # "user", "ai_agent", "service"
    name: str
    roles: Set[Role] = field(default_factory=set)
    permissions: PermissionSet = field(default_factory=PermissionSet)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: Optional[datetime] = None
    
    def has_permission(self, perm: Permission) -> bool:
        # Check explicit permissions
        if self.permissions.has_permission(perm):
            return True
        # Check role-based permissions
        for role in self.roles:
            if PERMISSIONS_BY_ROLE.get(role, set()).intersection({perm}):
                return True
        return False
    
    def grant_role(self, role: Role, granted_by: str = None) -> None:
        self.roles.add(role)
        for perm in PERMISSIONS_BY_ROLE.get(role, set()):
            self.permissions.add(perm, granted_by=granted_by)
    
    def revoke_role(self, role: Role) -> None:
        self.roles.discard(role)
        # Recalculate permissions from remaining roles
        self.permissions.permissions.clear()
        for r in self.roles:
            for perm in PERMISSIONS_BY_ROLE.get(r, set()):
                self.permissions.add(perm)


# Default role-permission mappings
PERMISSIONS_BY_ROLE: Dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        Permission.READ_PROJECT,
        Permission.READ_SCHEMATIC,
        Permission.READ_PCB,
        Permission.READ_BOM,
        Permission.READ_COMPONENT_DB,
        Permission.READ_DATASHEET,
        Permission.READ_SIMULATION,
        Permission.READ_3D_MODEL,
        Permission.COLLAB_JOIN,
    },
    Role.DESIGNER: {
        Permission.READ_PROJECT,
        Permission.READ_SCHEMATIC,
        Permission.READ_PCB,
        Permission.READ_BOM,
        Permission.READ_COMPONENT_DB,
        Permission.READ_DATASHEET,
        Permission.READ_SIMULATION,
        Permission.READ_3D_MODEL,
        Permission.WRITE_SCHEMATIC,
        Permission.WRITE_PCB,
        Permission.WRITE_BOM,
        Permission.WRITE_COMPONENT,
        Permission.EXECUTE_ERC,
        Permission.EXECUTE_DRC,
        Permission.EXECUTE_SPICE,
        Permission.EXECUTE_ROUTING,
        Permission.EXECUTE_3D_EXPORT,
        Permission.COLLAB_JOIN,
        Permission.COLLAB_EDIT,
    },
    Role.ENGINEER: {
        Permission.READ_PROJECT,
        Permission.READ_SCHEMATIC,
        Permission.READ_PCB,
        Permission.READ_BOM,
        Permission.READ_COMPONENT_DB,
        Permission.READ_DATASHEET,
        Permission.READ_SIMULATION,
        Permission.READ_3D_MODEL,
        Permission.WRITE_PROJECT,
        Permission.WRITE_SCHEMATIC,
        Permission.WRITE_PCB,
        Permission.WRITE_BOM,
        Permission.WRITE_COMPONENT,
        Permission.EXECUTE_ERC,
        Permission.EXECUTE_DRC,
        Permission.EXECUTE_SPICE,
        Permission.EXECUTE_ROUTING,
        Permission.EXECUTE_3D_EXPORT,
        Permission.EXECUTE_MCP_TOOL,
        Permission.COLLAB_JOIN,
        Permission.COLLAB_INVITE,
        Permission.COLLAB_EDIT,
    },
    Role.ADMIN: {
        Permission.READ_PROJECT,
        Permission.READ_SCHEMATIC,
        Permission.READ_PCB,
        Permission.READ_BOM,
        Permission.READ_COMPONENT_DB,
        Permission.READ_DATASHEET,
        Permission.READ_SIMULATION,
        Permission.READ_3D_MODEL,
        Permission.WRITE_PROJECT,
        Permission.WRITE_SCHEMATIC,
        Permission.WRITE_PCB,
        Permission.WRITE_BOM,
        Permission.WRITE_COMPONENT,
        Permission.EXECUTE_ERC,
        Permission.EXECUTE_DRC,
        Permission.EXECUTE_SPICE,
        Permission.EXECUTE_ROUTING,
        Permission.EXECUTE_3D_EXPORT,
        Permission.EXECUTE_MCP_TOOL,
        Permission.EXECUTE_AI_AGENT,
        Permission.ADMIN_USER,
        Permission.ADMIN_PROJECT,
        Permission.ADMIN_SYSTEM,
        Permission.COLLAB_JOIN,
        Permission.COLLAB_INVITE,
        Permission.COLLAB_EDIT,
        Permission.COLLAB_ADMIN,
    },
    Role.AI_AGENT: {
        Permission.READ_PROJECT,
        Permission.READ_SCHEMATIC,
        Permission.READ_PCB,
        Permission.READ_BOM,
        Permission.READ_COMPONENT_DB,
        Permission.READ_DATASHEET,
        Permission.READ_SIMULATION,
        Permission.READ_3D_MODEL,
        Permission.WRITE_SCHEMATIC,
        Permission.WRITE_PCB,
        Permission.WRITE_BOM,
        Permission.WRITE_COMPONENT,
        Permission.EXECUTE_ERC,
        Permission.EXECUTE_DRC,
        Permission.EXECUTE_SPICE,
        Permission.EXECUTE_ROUTING,
        Permission.EXECUTE_3D_EXPORT,
        Permission.EXECUTE_MCP_TOOL,
        Permission.EXECUTE_AI_AGENT,
        Permission.COLLAB_JOIN,
        Permission.COLLAB_EDIT,
    },
}


class PermissionManager:
    """Manages principals and permissions."""
    
    def __init__(self):
        self.principals: Dict[str, Principal] = {}
        self.audit_log: List[Dict[str, Any]] = []
    
    def create_principal(self, principal_id: str, principal_type: str, name: str, 
                         roles: Optional[List[Role]] = None) -> Principal:
        """Create a new principal."""
        principal = Principal(
            id=principal_id,
            type=principal_type,
            name=name,
            roles=set(roles) if roles else set()
        )
        self.principals[principal_id] = principal
        self._audit("create_principal", principal_id, {"type": principal_type, "name": name})
        return principal
    
    def get_principal(self, principal_id: str) -> Optional[Principal]:
        return self.principals.get(principal_id)
    
    def delete_principal(self, principal_id: str) -> bool:
        if principal_id in self.principals:
            del self.principals[principal_id]
            self._audit("delete_principal", principal_id)
            return True
        return False
    
    def check_permission(self, principal_id: str, permission: Permission) -> bool:
        principal = self.principals.get(principal_id)
        if not principal:
            return False
        return principal.has_permission(permission)
    
    def require_permission(self, principal_id: str, permission: Permission) -> None:
        if not self.check_permission(principal_id, permission):
            principal = self.principals.get(principal_id)
            raise PermissionError(
                f"Principal '{principal.name if principal else principal_id}' "
                f"lacks required permission: {permission.value}"
            )
    
    def grant_permission(self, principal_id: str, permission: Permission, 
                         granted_by: str = None) -> bool:
        principal = self.principals.get(principal_id)
        if not principal:
            return False
        principal.permissions.add(permission, granted_by=granted_by)
        self._audit("grant_permission", principal_id, {"permission": permission.value})
        return True
    
    def revoke_permission(self, principal_id: str, permission: Permission) -> bool:
        principal = self.principals.get(principal_id)
        if not principal:
            return False
        principal.permissions.remove(permission)
        self._audit("revoke_permission", principal_id, {"permission": permission.value})
        return True
    
    def grant_role(self, principal_id: str, role: Role, granted_by: str = None) -> bool:
        principal = self.principals.get(principal_id)
        if not principal:
            return False
        principal.grant_role(role, granted_by=granted_by)
        self._audit("grant_role", principal_id, {"role": role.value})
        return True
    
    def revoke_role(self, principal_id: str, role: Role) -> bool:
        principal = self.principals.get(principal_id)
        if not principal:
            return False
        principal.revoke_role(role)
        self._audit("revoke_role", principal_id, {"role": role.value})
        return True
    
    def _audit(self, action: str, principal_id: str, details: Dict[str, Any]) -> None:
        self.audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "principal_id": principal_id,
            "details": details
        })
    
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.audit_log[-limit:]


# Global permission manager
permission_manager = PermissionManager()


def require_permission(permission: Permission):
    """Decorator to require a permission for a function."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract principal_id from context (would come from auth middleware)
            principal_id = kwargs.get("_principal_id")
            if not principal_id:
                raise PermissionError("No principal ID provided")
            permission_manager.require_permission(principal_id, permission)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Context manager for temporary permission elevation
class TemporaryPermission:
    """Context manager for temporarily granting a permission."""
    
    def __init__(self, manager: PermissionManager, principal_id: str, 
                 permission: Permission, granted_by: str = "system"):
        self.manager = manager
        self.principal_id = principal_id
        self.permission = permission
        self.granted_by = granted_by
        self.was_granted = False
    
    def __enter__(self):
        self.was_granted = self.manager.check_permission(self.principal_id, self.permission)
        if not self.was_granted:
            self.manager.grant_permission(self.principal_id, self.permission, self.granted_by)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.was_granted:
            self.manager.revoke_permission(self.principal_id, self.permission)


# Example usage and default setup
def setup_default_permissions():
    """Set up default principals for the platform."""
    # Create default admin
    admin = permission_manager.create_principal(
        "admin", "user", "System Administrator", roles=[Role.ADMIN]
    )
    
    # Create default AI agent principal
    ai_agent = permission_manager.create_principal(
        "ai_agent_001", "ai_agent", "Design Assistant", roles=[Role.AI_AGENT]
    )
    
    # Create default designer
    designer = permission_manager.create_principal(
        "designer_001", "user", "PCB Designer", roles=[Role.DESIGNER]
    )
    
    return {
        "admin": admin,
        "ai_agent": ai_agent,
        "designer": designer
    }