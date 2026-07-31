import { apiHelpers } from './apiClient'

export interface UserStats {
  videosCreated: number
  totalProcessingTime: number // in seconds
  storageUsed: number // in bytes
  successRate: number // percentage
}

export interface Project {
  id: string
  title: string
  status: 'completed' | 'processing' | 'failed' | 'draft'
  createdAt: string
  duration: number // in seconds
  thumbnail?: string
  videoUrl?: string
  size?: number // in bytes
  creationStep?: string
  projectType?: string
}

// No more mock data - only real projects from database

export const dashboardService = {
  async getUserStats(): Promise<UserStats> {
    try {
      const response = await apiHelpers.get<UserStats>('/api/dashboard/stats')
      return response.data
    } catch (error) {
      console.error('Failed to fetch user stats:', error)
      // Return default stats for new users
      return {
        videosCreated: 0,
        totalProcessingTime: 0,
        storageUsed: 0,
        successRate: 100
      }
    }
  },

  async getRecentProjects(limit: number = 6): Promise<Project[]> {
    try {

      // Pass limit parameter to backend API to only fetch required number of projects
      const response = await apiHelpers.get<{projects: Project[], total: number, userId: string}>('/api/video/user/projects', {
        params: { limit }
      })

      return response.data.projects
    } catch (error) {
      // Return empty array if API fails
      return []
    }
  },

  async getAllProjects(): Promise<Project[]> {
    try {
      const response = await apiHelpers.get<{projects: Project[], total: number, userId: string}>('/api/video/user/projects')
      return response.data.projects
    } catch (error) {
      console.error('❌ Failed to fetch all projects:', error)
      // Return empty array if API fails - no more mock data
      return []
    }
  },

  async deleteProject(projectId: string): Promise<void> {
    try {
      await apiHelpers.delete(`/api/video/user/projects/${projectId}`)
    } catch (error) {
      console.error('Failed to delete project:', error)
      throw error
    }
  },

  async duplicateProject(projectId: string): Promise<Project> {
    try {
      const response = await apiHelpers.post<Project>(`/api/dashboard/projects/${projectId}/duplicate`)
      return response.data
    } catch (error) {
      console.error('Failed to duplicate project:', error)
      throw error
    }
  },

  async renameProject(projectId: string, newTitle: string): Promise<void> {
    try {
      await apiHelpers.patch(`/api/dashboard/projects/${projectId}`, { title: newTitle })
    } catch (error) {
      console.error('Failed to rename project:', error)
      throw error
    }
  }
}
