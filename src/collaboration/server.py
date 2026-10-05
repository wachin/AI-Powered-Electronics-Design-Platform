"""
Yjs Collaboration Server for AI-Powered Electronics Design Platform.

WebSocket server for real-time collaborative editing using Yjs CRDT.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any
from datetime import datetime
import logging

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)


@dataclass
class Collaborator:
    """Represents a connected collaborator."""
    user_id: str
    name: str
    color: str
    cursor_position: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, Any]] = None
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollaborationRoom:
    """A collaborative editing room for a design project."""
    room_id: str
    project_name: str
    design_data: Dict[str, Any] = field(default_factory=dict)
    collaborators: Dict[str, Collaborator] = field(default_factory=dict)
    document_state: bytes = field(default_factory=bytes)  # Yjs document binary state
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Awareness state (cursor, selection, user info)
    awareness_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class CollaborationManager:
    """Manages collaborative editing rooms and WebSocket connections."""
    
    def __init__(self):
        self.rooms: Dict[str, CollaborationRoom] = {}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}  # room_id -> user_id -> ws
        self.user_colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
            "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9"
        ]
        self._color_index = 0
    
    def _get_next_color(self) -> str:
        color = self.user_colors[self._color_index % len(self.user_colors)]
        self._color_index += 1
        return color
    
    async def create_room(self, room_id: str, project_name: str, initial_data: Optional[Dict] = None) -> CollaborationRoom:
        """Create a new collaboration room."""
        room = CollaborationRoom(
            room_id=room_id,
            project_name=project_name,
            design_data=initial_data or {}
        )
        self.rooms[room_id] = room
        self.active_connections[room_id] = {}
        logger.info(f"Created collaboration room: {room_id} ({project_name})")
        return room
    
    def get_room(self, room_id: str) -> Optional[CollaborationRoom]:
        """Get room by ID."""
        return self.rooms.get(room_id)
    
    async def join_room(self, room_id: str, user_id: str, name: str, websocket: WebSocket) -> Optional[Collaborator]:
        """Add a user to a collaboration room."""
        room = self.rooms.get(room_id)
        if not room:
            return None
        
        collaborator = Collaborator(
            user_id=user_id,
            name=name,
            color=self._get_next_color()
        )
        room.collaborators[user_id] = collaborator
        room.awareness_states[user_id] = {
            "user": {"id": user_id, "name": name, "color": collaborator.color},
            "cursor": None,
            "selection": None
        }
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
        self.active_connections[room_id][user_id] = websocket
        
        # Notify others about new user
        await self._broadcast_room(room_id, {
            "type": "user_joined",
            "user": {"id": user_id, "name": name, "color": collaborator.color}
        }, exclude_user=user_id)
        
        # Send current room state to new user
        await websocket.send_text(json.dumps({
            "type": "room_state",
            "room_id": room_id,
            "project_name": room.project_name,
            "design_data": room.design_data,
            "document_state": room.document_state.hex() if room.document_state else "",
            "users": [
                {"id": uid, "name": c.name, "color": c.color}
                for uid, c in room.collaborators.items()
            ],
            "your_id": user_id
        }))
        
        logger.info(f"User {name} ({user_id}) joined room {room_id}")
        return collaborator
    
    async def leave_room(self, room_id: str, user_id: str):
        """Remove a user from a collaboration room."""
        room = self.rooms.get(room_id)
        if not room:
            return
        
        collaborator = room.collaborators.pop(user_id, None)
        room.awareness_states.pop(user_id, None)
        
        if room_id in self.active_connections:
            self.active_connections[room_id].pop(user_id, None)
        
        # Notify others
        if collaborator:
            await self._broadcast_room(room_id, {
                "type": "user_left",
                "user_id": user_id
            })
            logger.info(f"User {collaborator.name} ({user_id}) left room {room_id}")
        
        # Clean up empty rooms
        if not room.collaborators:
            await self._cleanup_room(room_id)
    
    async def _cleanup_room(self, room_id: str):
        """Clean up empty room."""
        self.rooms.pop(room_id, None)
        self.active_connections.pop(room_id, None)
        logger.info(f"Cleaned up empty room: {room_id}")
    
    async def broadcast_awareness(self, room_id: str, user_id: str, awareness: Dict[str, Any]):
        """Broadcast awareness update (cursor, selection) to other users."""
        room = self.rooms.get(room_id)
        if not room:
            return
        
        room.awareness_states[user_id] = awareness
        
        await self._broadcast_room(room_id, {
            "type": "awareness_update",
            "user_id": user_id,
            "awareness": awareness
        }, exclude_user=user_id)
    
    async def broadcast_document_update(self, room_id: str, user_id: str, update: bytes):
        """Broadcast Yjs document update to other users."""
        room = self.rooms.get(room_id)
        if not room:
            return
        
        # Append to document state (simplified - in production use Yjs doc.merge)
        room.document_state = update
        room.updated_at = datetime.utcnow()
        
        await self._broadcast_room(room_id, {
            "type": "document_update",
            "user_id": user_id,
            "update": update.hex()
        }, exclude_user=user_id)
    
    async def broadcast_design_change(self, room_id: str, user_id: str, change: Dict[str, Any]):
        """Broadcast design data change (components, nets, etc.)."""
        room = self.rooms.get(room_id)
        if not room:
            return
        
        room.design_data = change.get("design_data", room.design_data)
        room.updated_at = datetime.utcnow()
        
        await self._broadcast_room(room_id, {
            "type": "design_change",
            "user_id": user_id,
            "change": change
        }, exclude_user=user_id)
    
    async def _broadcast_room(self, room_id: str, message: Dict[str, Any], exclude_user: Optional[str] = None):
        """Send message to all users in a room except excluded user."""
        if room_id not in self.active_connections:
            return
        
        message_str = json.dumps(message)
        for user_id, ws in self.active_connections[room_id].items():
            if user_id != exclude_user:
                try:
                    await ws.send_text(message_str)
                except Exception as e:
                    logger.warning(f"Failed to send to {user_id}: {e}")
    
    def get_room_users(self, room_id: str) -> List[Dict[str, Any]]:
        """Get list of users in a room."""
        room = self.rooms.get(room_id)
        if not room:
            return []
        return [
            {"id": uid, "name": c.name, "color": c.color}
            for uid, c in room.collaborators.items()
        ]


# Global collaboration manager
collaboration_manager = CollaborationManager()


async def handle_collaboration_websocket(websocket: WebSocket, room_id: str, user_id: str, name: str):
    """Handle WebSocket connection for collaborative editing."""
    await websocket.accept()
    
    room = collaboration_manager.get_room(room_id)
    if not room:
        # Auto-create room if it doesn't exist
        room = await collaboration_manager.create_room(room_id, f"Project {room_id}")
    
    collaborator = await collaboration_manager.join_room(room_id, user_id, name, websocket)
    if not collaborator:
        await websocket.close(code=4004, reason="Failed to join room")
        return
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            msg_type = message.get("type")
            
            if msg_type == "awareness":
                awareness = message.get("awareness", {})
                await collaboration_manager.broadcast_awareness(room_id, user_id, awareness)
            
            elif msg_type == "document_update":
                update_hex = message.get("update", "")
                if update_hex:
                    update_bytes = bytes.fromhex(update_hex)
                    await collaboration_manager.broadcast_document_update(room_id, user_id, update_bytes)
            
            elif msg_type == "design_change":
                change = message.get("change", {})
                await collaboration_manager.broadcast_design_change(room_id, user_id, change)
            
            elif msg_type == "sync_request":
                # Send current document state
                room = collaboration_manager.get_room(room_id)
                if room:
                    await websocket.send_text(json.dumps({
                        "type": "document_state",
                        "state": room.document_state.hex() if room.document_state else ""
                    }))
            
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for {user_id} in {room_id}: {e}")
    finally:
        await collaboration_manager.leave_room(room_id, user_id)


# REST API endpoints for room management
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


@router.post("/rooms")
async def create_room(project_name: str, initial_data: Optional[Dict] = None):
    """Create a new collaboration room."""
    room_id = str(uuid.uuid4())[:8]
    room = await collaboration_manager.create_room(room_id, project_name, initial_data)
    return {
        "room_id": room.room_id,
        "project_name": room.project_name,
        "created_at": room.created_at.isoformat()
    }


@router.get("/rooms/{room_id}")
async def get_room(room_id: str):
    """Get room information."""
    room = collaboration_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {
        "room_id": room.room_id,
        "project_name": room.project_name,
        "design_data": room.design_data,
        "users": [
            {"id": uid, "name": c.name, "color": c.color, "connected_at": c.connected_at.isoformat()}
            for uid, c in room.collaborators.items()
        ],
        "created_at": room.created_at.isoformat(),
        "updated_at": room.updated_at.isoformat()
    }


@router.get("/rooms")
async def list_rooms():
    """List all active collaboration rooms."""
    return [
        {
            "room_id": room.room_id,
            "project_name": room.project_name,
            "user_count": len(room.collaborators),
            "created_at": room.created_at.isoformat(),
            "updated_at": room.updated_at.isoformat()
        }
        for room in collaboration_manager.rooms.values()
    ]


@router.post("/rooms/{room_id}/design")
async def update_design(room_id: str, design_data: Dict[str, Any]):
    """Update the design data for a room."""
    room = collaboration_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room.design_data = design_data
    room.updated_at = datetime.utcnow()
    
    # Broadcast to all users
    await collaboration_manager._broadcast_room(room_id, {
        "type": "design_sync",
        "design_data": design_data
    })
    
    return {"status": "ok"}


@router.get("/rooms/{room_id}/design")
async def get_design(room_id: str):
    """Get the current design data for a room."""
    room = collaboration_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.design_data