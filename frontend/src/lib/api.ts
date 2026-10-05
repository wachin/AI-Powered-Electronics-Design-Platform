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

export const apiClient = {
  createDesign: designApi.create,
  getJob: designApi.getJob,
  listJobs: designApi.listJobs,
  searchComponents: componentApi.search,
  getCategories: componentApi.getCategories,
  getComponent: componentApi.get,
}

export default apiClient