import { useState, useEffect, useRef } from 'react'
import { useCollaborationRoom } from '../hooks/useCollaboration'
import { apiClient } from '../lib/api'
import { PCB3DViewer } from '../components/PCB3DViewer'

interface CollaborationPageProps {
  roomId?: string
}

export function CollaborationPage({ roomId: initialRoomId }: CollaborationPageProps) {
  const { rooms, loading, createRoom } = useCollaborationRoom()
  const [activeRoomId, setActiveRoomId] = useState<string | null>(initialRoomId || null)
  const [userName, setUserName] = useState('')
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [joining, setJoining] = useState(false)
  const [roomInfo, setRoomInfo] = useState<any>(null)
  
  const canvasRef = useRef<HTMLDivElement>(null)

  // Auto-join if roomId provided
  useEffect(() => {
    if (initialRoomId && !activeRoomId) {
      setActiveRoomId(initialRoomId)
    }
  }, [initialRoomId])

  // Load room info when activeRoomId changes
  useEffect(() => {
    if (activeRoomId) {
      loadRoomInfo(activeRoomId)
    } else {
      setRoomInfo(null)
    }
  }, [activeRoomId])

  const loadRoomInfo = async (roomId: string) => {
    try {
      const res = await apiClient.getRoom(roomId)
      setRoomInfo(res.data)
    } catch (err) {
      console.error('Failed to load room:', err)
    }
  }

  const handleCreateRoom = async () => {
    if (!newProjectName.trim() || !userName.trim()) return
    setJoining(true)
    try {
      const res = await createRoom(newProjectName.trim())
      setActiveRoomId(res.data.room_id)
      setShowCreateDialog(false)
      setNewProjectName('')
    } catch (err) {
      console.error('Failed to create room:', err)
    } finally {
      setJoining(false)
    }
  }

  const handleJoinRoom = async (roomId: string) => {
    if (!userName.trim()) return
    setJoining(true)
    try {
      await apiClient.getRoom(roomId) // Verify room exists
      setActiveRoomId(roomId)
    } catch (err) {
      console.error('Failed to join room:', err)
    } finally {
      setJoining(false)
    }
  }

  const handleLeaveRoom = () => {
    setActiveRoomId(null)
    setRoomInfo(null)
  }

  if (!activeRoomId) {
    return (
      <div className="collab-lobby">
        <div className="lobby-header">
          <h1>🤝 Collaborative Design</h1>
          <p>Create or join a design session to work together in real-time</p>
        </div>

        <div className="lobby-form">
          <div className="form-group">
            <label>Your Name</label>
            <input
              type="text"
              value={userName}
              onChange={e => setUserName(e.target.value)}
              placeholder="Enter your name"
              required
            />
          </div>

          <div className="lobby-tabs">
            <button className="tab-btn active">Create New Session</button>
            <button className="tab-btn">Join Existing Session</button>
          </div>

          {showCreateDialog && (
            <div className="create-room-form">
              <div className="form-group">
                <label>Project Name</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={e => setNewProjectName(e.target.value)}
                  placeholder="e.g., Power Supply Design"
                  required
                />
              </div>
              <button className="btn-primary" onClick={handleCreateRoom} disabled={joining || !newProjectName.trim()}>
                {joining ? 'Creating...' : 'Create & Join'}
              </button>
            </div>
          )}
          {!showCreateDialog && (
              <div className="join-room-form">
                <div className="form-group">
                  <label>Room ID</label>
                  <input
                    type="text"
                    placeholder="Enter 8-character room ID"
                    maxLength={8}
                    onKeyDown={e => e.key === 'Enter' && handleJoinRoom(e.currentTarget.value)}
                  />
                </div>
                <button className="btn-primary" onClick={() => handleJoinRoom('')} disabled={joining}>
                  {joining ? 'Joining...' : 'Join Session'}
                </button>
              </div>
            )}

          <div className="existing-rooms">
            <h3>Recent Sessions</h3>
            {loading ? (
              <div className="loading">Loading...</div>
            ) : rooms.length === 0 ? (
              <p className="empty">No active sessions yet</p>
            ) : (
              <ul className="room-list">
                {rooms.map(room => (
                  <li key={room.room_id} className="room-item">
                    <div className="room-info">
                      <span className="room-name">{room.project_name}</span>
                      <span className="room-meta">
                        {room.user_count} user{room.user_count !== 1 ? 's' : ''} • 
                        {new Date(room.updated_at).toLocaleString()}
                      </span>
                    </div>
                    <button 
                      className="btn-secondary" 
                      onClick={() => handleJoinRoom(room.room_id)}
                      disabled={joining}
                    >
                      Join
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Active room view - would integrate with Yjs editor here
  return (
    <div className="collab-room">
      <header className="room-header">
        <button className="btn-secondary" onClick={handleLeaveRoom}>
          ← Leave Session
        </button>
        <div className="room-title">
          <h2>{roomInfo?.project_name || 'Loading...'}</h2>
          <span className="room-id">Room: {activeRoomId}</span>
        </div>
        <div className="user-presence">
          {(roomInfo?.users || []).map((user: any) => (
            <div key={user.id} className="user-badge" style={{ 
              backgroundColor: user.color,
              borderColor: user.id === '' ? '#fff' : 'transparent'
            }}>
              <span>{user.name}</span>
              {user.id === '' && <span className="you-badge">(you)</span>}
            </div>
          ))}
        </div>
      </header>

      <main className="room-main">
        <div className="room-sidebar">
          <div className="panel">
            <h3>Components</h3>
            <div className="component-tree">
              {roomInfo?.design_data?.components ? 
                Object.entries(roomInfo.design_data.components).map(([ref, comp]: [string, any]) => (
                  <div key={ref} className="component-item">
                    <code>{ref}</code> {comp.value} ({comp.component_type})
                  </div>
                )) : (
                  <p className="empty">No components yet</p>
                )}
            </div>
          </div>

          <div className="panel">
            <h3>Activity</h3>
            <div className="activity-log">
              <p className="empty">Real-time updates will appear here</p>
            </div>
          </div>
        </div>

        <div className="room-canvas" ref={canvasRef}>
          {/* 3D PCB Viewer */}
          <div style={{ height: '50%', minHeight: '300px' }}>
            <PCB3DViewer 
              gltfUrl={roomInfo?.generated_files?.gltf ? `/api/files${roomInfo.generated_files.gltf}` : undefined}
              boardWidth={100}
              boardHeight={80}
            />
          </div>

          {/* 2D Collaborative Canvas */}
          <div style={{ height: '50%', minHeight: '300px', borderTop: '1px solid var(--border)' }}>
            {/* This is where the collaborative schematic/PCB editor would go */}
            <div className="canvas-placeholder">
              <div className="placeholder-content">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M9 9h6v6H9z" />
                </svg>
                <h3>Collaborative Canvas</h3>
                <p>Real-time schematic and PCB editing with Yjs</p>
                <p className="hint">Other users' cursors will appear here</p>
              </div>
              
              {/* Remote cursors overlay */}
              <div className="remote-cursors">
                {(roomInfo?.users || [])
                  .filter((u: any) => u.id !== '' && u.cursor)
                  .map((user: any) => (
                    <div
                      key={user.id}
                      className="remote-cursor"
                      style={{
                        left: user.cursor!.x,
                        top: user.cursor!.y,
                        borderColor: user.color
                      }}
                    >
                      <div className="cursor-label" style={{ backgroundColor: user.color }}>
                        {user.name}
                      </div>
                      <div className="cursor-pointer" style={{ borderTopColor: user.color }} />
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default CollaborationPage