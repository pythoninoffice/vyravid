import apiClient from './apiClient'
import { AxiosError } from 'axios'

// TypeScript interfaces
export interface ImageFolder {
  id: string
  user_id: string
  name: string
  color?: string
  sort_order: number
  image_count: number
  created_at: string
  updated_at: string
}

export interface CreateFolderRequest {
  name: string
  color?: string
}

export interface UpdateFolderRequest {
  name?: string
  color?: string
  sort_order?: number
}

export interface MoveImageToFolderRequest {
  folder_id: string | null
}

export interface BulkMoveImagesRequest {
  image_ids: string[]
  folder_id: string | null
}

export interface FolderResponse {
  folder: ImageFolder
}

export interface FoldersListResponse {
  folders: ImageFolder[]
  total: number
}

// Error handling
export class FolderError extends Error {
  constructor(
    message: string,
    public code?: string,
    public statusCode?: number
  ) {
    super(message)
    this.name = 'FolderError'
  }
}

const handleApiError = (error: AxiosError): never => {
  if (!error.response) {
    throw new FolderError(
      'Network error occurred. Please check your connection and try again.',
      'NETWORK_ERROR',
      0
    )
  }

  const { status, data } = error.response
  const message = (data as any)?.detail?.message ||
                  (data as any)?.message ||
                  (data as any)?.error ||
                  (typeof data === 'string' ? data : null) ||
                  error.message

  switch (status) {
    case 400:
      throw new FolderError(message, 'BAD_REQUEST', status)
    case 401:
      throw new FolderError(
        'Authentication required. Please sign in.',
        'UNAUTHORIZED',
        status
      )
    case 404:
      throw new FolderError(
        'Folder not found or access denied.',
        'NOT_FOUND',
        status
      )
    case 500:
      throw new FolderError(
        message || 'Server error occurred. Please try again.',
        'SERVER_ERROR',
        status
      )
    default:
      throw new FolderError(
        message || 'An unexpected error occurred.',
        'UNKNOWN_ERROR',
        status
      )
  }
}

// API Service
export const imageFoldersService = {
  /**
   * Get all folders for the current user
   */
  async listFolders(): Promise<FoldersListResponse> {
    try {
      const response = await apiClient.get<FoldersListResponse>('/api/folders')
      return response.data
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Create a new folder
   */
  async createFolder(data: CreateFolderRequest): Promise<ImageFolder> {
    try {
      const response = await apiClient.post<FolderResponse>('/api/folders', data)
      return response.data.folder
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Update a folder (rename, change color, reorder)
   */
  async updateFolder(folderId: string, data: UpdateFolderRequest): Promise<ImageFolder> {
    try {
      const response = await apiClient.put<FolderResponse>(`/api/folders/${folderId}`, data)
      return response.data.folder
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Delete a folder (images will be set to uncategorized)
   */
  async deleteFolder(folderId: string): Promise<void> {
    try {
      await apiClient.delete(`/api/folders/${folderId}`)
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Move a single image to a folder (or remove from folder)
   */
  async moveImageToFolder(imageId: string, folderId: string | null): Promise<void> {
    try {
      await apiClient.put(`/api/folders/images/${imageId}/folder`, {
        folder_id: folderId
      })
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Move multiple images to a folder (or remove from folders)
   */
  async bulkMoveImages(imageIds: string[], folderId: string | null): Promise<void> {
    try {
      await apiClient.post('/api/folders/images/bulk-move', {
        image_ids: imageIds,
        folder_id: folderId
      })
    } catch (error) {
      return handleApiError(error as AxiosError)
    }
  }
}

export default imageFoldersService
