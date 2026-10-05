import { useEffect, useRef, useState, useCallback } from 'react'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'

// Types for collaboration
export interface Collaborator {
  id: string
  name: string
  color: string
  cursor?: { x: number; y: number }
  selection?: any
}

export interface RoomState {
  roomId: string
  projectName: string
  designData: any
  users: Collaborator[]
  yourId: string
}

export interface AwarenessState {
  user: { id: string; name: string; color: string }
  cursor?: { x: number; y: number }
  selection?: any
}

/**
 * Hook for Yjs collaboration with WebSocket provider
 */
export function useCollaboration(roomId: string, userName: string) {
  const [connected, setConnected] = useState(false)
  const [users, setUsers] = useState<Collaborator[]>([])
  const [designData, setDesignData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  
  const docRef = useRef<Y.Doc | null>(null)
  const providerRef = useRef<WebsocketProvider | null>(null)
  const awarenessRef = useRef<any>(null)
  const userIdRef = useRef<string>(`user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)

  const userId = userIdRef.current

  // Initialize Yjs document and WebSocket provider
  useEffect(() => {
    const userId = userIdRef.current
    
    // Create Yjs document
    const doc = new Y.Doc()
    docRef.current = doc

    // Create WebSocket provider
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/collaboration/ws/${roomId}/${userId}/${encodeURIComponent(userName)}`
    
    const provider = new WebsocketProvider(wsUrl, roomId, doc, {
      connect: true
    })
    providerRef.current = provider

    // Get awareness instance
    const awareness = provider.awareness
    awarenessRef.current = awareness

    // Set local user info
    awareness.setLocalStateField('user', {
      id: userId,
      name: userName,
      color: `hsl(${Math.random() * 360}, 70%, 50%)`
    })

    // Connection status
    provider.on('status', (event: { status: string }) => {
      setConnected(event.status === 'connected')
      if (event.status === 'connected') {
        setError(null)
      }
    })

    // Handle incoming awareness updates (other users' cursors/selections)
    awareness.on('change', () => {
      const states = awareness.getStates()
      const userList: Collaborator[] = []
      
      states.forEach((state: any, _clientId: number) => {
        if (state.user) {
          userList.push({
            id: state.user.id,
            name: state.user.name,
            color: state.user.color,
            cursor: state.cursor,
            selection: state.selection
          })
        }
      })
      setUsers(userList)
    })

    // Handle sync with other users
    provider.on('sync', (isSynced: boolean) => {
      console.log('Yjs sync:', isSynced)
    })

    // Handle connection errors
    provider.ws?.addEventListener('error', (err) => {
      console.error('WebSocket error:', err)
      setError('Connection error. Retrying...')
    })

    provider.ws?.addEventListener('close', () => {
      setConnected(false)
    })

    // Cleanup
    return () => {
      awareness.destroy()
      provider.destroy()
      doc.destroy()
    }
  }, [roomId, userName])

  // Update local cursor position
  const updateCursor = useCallback((x: number, y: number) => {
    const awareness = awarenessRef.current
    if (awareness) {
      awareness.setLocalStateField('cursor', { x, y })
    }
  }, [])

  // Update local selection
  const updateSelection = useCallback((selection: any) => {
    const awareness = awarenessRef.current
    if (awareness) {
      awareness.setLocalStateField('selection', selection)
    }
  }, [])

  // Broadcast design changes to other users
  const broadcastDesignChange = useCallback((change: any) => {
    const provider = providerRef.current
    if (provider && provider.ws && provider.ws.readyState === WebSocket.OPEN) {
      provider.ws.send(JSON.stringify({
        type: 'design_change',
        change
      }))
    }
  }, [])

  // Update design data locally and broadcast
  const updateDesign = useCallback((newData: any) => {
    setDesignData(newData)
    broadcastDesignChange({ design_data: newData })
  }, [broadcastDesignChange])

  // Request document sync
  const requestSync = useCallback(() => {
    const provider = providerRef.current
    if (provider) {
      provider.ws?.send(JSON.stringify({ type: 'sync_request' }))
    }
  }, [])

  return {
    // State
    connected,
    users,
    designData,
    yourId: userId,
    error,
    
    // Actions
    updateCursor,
    updateSelection,
    updateDesign,
    requestSync,
    broadcastDesignChange,
    
    // Raw access
    doc: docRef.current,
    provider: providerRef.current,
    awareness: awarenessRef.current
  }
}

/**
 * Hook for managing collaboration room via REST API
 */
export function useCollaborationRoom() {
  const [rooms, setRooms] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchRooms = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/collaboration/rooms')
      const data = await res.json()
      setRooms(data)
    } catch (err) {
      console.error('Failed to fetch rooms:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const createRoom = useCallback(async (projectName: string, initialData?: any) => {
    const res = await fetch('/api/collaboration/rooms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: projectName, initial_data: initialData })
    })
    return res.json()
  }, [])

  const getRoom = useCallback(async (roomId: string) => {
    const res = await fetch(`/api/collaboration/rooms/${roomId}`)
    return res.json()
  }, [])

  const updateDesign = useCallback(async (roomId: string, designData: any) => {
    const res = await fetch(`/api/collaboration/rooms/${roomId}/design`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(designData)
    })
    return res.json()
  }, [])

  useEffect(() => {
    fetchRooms()
  }, [fetchRooms])

  return {
    rooms,
    loading,
    createRoom,
    getRoom,
    updateDesign,
    refresh: fetchRooms
  }
}