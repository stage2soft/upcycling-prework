import axios from 'axios'

export type CandidateFile = {
  id: number; file_group: 'raw' | 'labeled'; reference_order: number
  original_relative_path: string; selected_relative_path: string; extension: string
  size: number; mtime: number; is_previewable_image: boolean; file_url: string
}
export type Candidate = {
  id: string; fingerprint: string; match_key: string; mapping_strategy: string
  match_status: string; selection_status: string; error_message: string
  created_at: string; updated_at: string; decided_at: string | null
  files: CandidateFile[]; label_json?: unknown
}
export type CandidatePage = { results: Candidate[]; count: number; page: number; page_size: number; total_pages: number; summary: Record<string, number> }
export type AppSettings = {
  mapping_strategy: 'file_name' | 'json_ref_key'; json_ref_key: string
  raw_relative_path: string; labeled_relative_path: string
  annotation_method_code: 'bbox_2d' | 'bbox_3d' | 'polygon' | 'segmentation'
}
export type DirectoryListing = {
  root_container_path: string; root_host_path: string; current: string; parent: string
  directories: { name: string; path: string }[]
}
export type VolumeStatus = {
  key: string; label: string; host_path: string; container_path: string; exists: boolean; is_mount: boolean
  readable: boolean; writable: boolean; total_bytes: number; used_bytes: number; free_bytes: number
}
export type VolumeOverview = {
  volumes: VolumeStatus[]
  selected_directories: { key: string; label: string; relative_path: string; exists: boolean; readable: boolean; writable: boolean }[]
}
export type TextPreview = {
  previewable: boolean; content?: string; encoding?: string; truncated?: boolean
  preview_bytes?: number; size?: number; reason?: string
}

const http = axios.create({ baseURL: '/api', timeout: 30000 })
export const api = {
  settings: () => http.get<AppSettings>('/settings').then(r => r.data),
  saveSettings: (value: AppSettings) => http.put<AppSettings>('/settings', value).then(r => r.data),
  directories: (path = '') => http.get<DirectoryListing>('/directories', { params: { path } }).then(r => r.data),
  volumes: () => http.get<VolumeOverview>('/volumes').then(r => r.data),
  scan: (value: AppSettings) => http.post<Record<string, number>>('/scan', value, { timeout: 120000 }).then(r => r.data),
  candidates: (params: Record<string, unknown>) => http.get<CandidatePage>('/candidates', { params }).then(r => r.data),
  candidate: (id: string) => http.get<Candidate>(`/candidates/${id}`).then(r => r.data),
  fileText: (candidateId: string, fileId: number) => http.get<TextPreview>(`/candidates/${candidateId}/files/${fileId}/text`).then(r => r.data),
  decision: (id: string, decision: 'selected' | 'rejected', overwrite = false) => http.post<Candidate>(`/candidates/${id}/decision`, { decision, overwrite }).then(r => r.data),
  reset: (id: string) => http.post<Candidate>(`/candidates/${id}/reset`).then(r => r.data),
}

export function apiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
    return String(detail || error.message)
  }
  return error instanceof Error ? error.message : String(error)
}

export function copyConflictPaths(error: unknown): string[] | null {
  if (!axios.isAxiosError(error)) return null
  const detail = error.response?.data?.detail
  return detail?.code === 'copy_conflict' && Array.isArray(detail.conflicts) ? detail.conflicts.map(String) : null
}
