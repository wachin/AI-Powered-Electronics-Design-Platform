import axios from 'axios'
import type { 
  DesignRequest, 
  JobStatus, 
  DesignResponse,
  ComponentSearchRequest,
  ComponentResult 
} from '../types'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

export const designApi = {
  create: (request: DesignRequest): Promise<{ data: DesignResponse }> =>
    api.post('/design', request),
  
  getJob: (jobId: string): Promise<{ data: JobStatus }> =>
    api.get(`/jobs/${jobId}`),
  
  listJobs: (): Promise<{ data: { jobs: JobStatus[] } }> =>
    api.get('/jobs'),
}

export const componentApi = {
  search: (request: ComponentSearchRequest): Promise<{ data: ComponentResult[] }> =>
    api.post('/components/search', request),
  
  getCategories: (): Promise<{ data: { categories: string[] } }> =>
    api.get('/components/categories'),
  
  get: (mpn: string): Promise<{ data: ComponentResult }> =>
    api.get(`/components/${mpn}`),
}

// Collaboration API
export interface CollaborationRoom {
  room_id: string
  project_name: string
  design_data: any
  users: Array<{ id: string; name: string; color: string; connected_at: string }>
  created_at: string
  updated_at: string
}

export interface RoomListItem {
  room_id: string
  project_name: string
  user_count: number
  created_at: string
  updated_at: string
}

export const collaborationApi = {
  createRoom: (projectName: string, initialData?: any): Promise<{ data: { room_id: string; project_name: string } }> =>
    api.post('/collaboration/rooms', { project_name: projectName, initial_data: initialData }),
  
  getRoom: (roomId: string): Promise<{ data: CollaborationRoom }> =>
    api.get(`/collaboration/rooms/${roomId}`),
  
  listRooms: (): Promise<{ data: RoomListItem[] }> =>
    api.get('/collaboration/rooms'),
  
  updateDesign: (roomId: string, designData: any): Promise<{ data: { status: string } }> =>
    api.post(`/collaboration/rooms/${roomId}/design`, designData),
  
  getDesign: (roomId: string): Promise<{ data: any }> =>
    api.get(`/collaboration/rooms/${roomId}/design`),
  
  // WebSocket URL builder
  getWebSocketUrl: (roomId: string, userId: string, userName: string): string => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/collaboration/ws/${roomId}/${userId}/${encodeURIComponent(userName)}`
  }
}

export const apiClient = {
  createDesign: designApi.create,
  getJob: designApi.getJob,
  listJobs: designApi.listJobs,
  searchComponents: componentApi.search,
  getCategories: componentApi.getCategories,
  getComponent: componentApi.get,
  // Collaboration
  createRoom: collaborationApi.createRoom,
  getRoom: collaborationApi.getRoom,
  listRooms: collaborationApi.listRooms,
  updateDesign: collaborationApi.updateDesign,
  getDesign: collaborationApi.getDesign,
  getCollabWsUrl: collaborationApi.getWebSocketUrl,
}

export default apiClient