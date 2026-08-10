const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/$/,
  '',
)

export interface ModelInfo {
  id: string
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ModelSummary extends ModelInfo {
  version_count: number
  latest_version: number | null
}

export interface ModelVersion {
  id: string
  model_id: string
  parent_version_id: string | null
  version: number
  checksum: string | null
  size_bytes: number | null
  change_summary: Record<string, unknown> | null
  created_by: string | null
  created_at: string
}

export interface SectionSummary {
  name: string
  record_count: number
  editable: boolean
  fields: string[]
}

export interface SectionRecord {
  index: number
  target: string | null
  values: Record<string, string | null>
  extra_values: string[]
  raw: string
}

export interface SectionDetail {
  name: string
  editable: boolean
  fields: string[]
  record_count: number
  records: SectionRecord[]
}

export interface ImportModelResponse {
  model: ModelInfo
  version: ModelVersion
  sections: SectionSummary[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

export function fetchModels(): Promise<ModelSummary[]> {
  return request('/api/models')
}

export function fetchVersions(modelId: string): Promise<ModelVersion[]> {
  return request(`/api/models/${modelId}/versions`)
}

export async function fetchSections(versionId: string): Promise<SectionSummary[]> {
  const response = await request<{ sections: SectionSummary[] }>(
    `/api/model-versions/${versionId}/sections`,
  )
  return response.sections
}

export async function fetchSection(versionId: string, sectionName: string): Promise<SectionDetail> {
  const response = await request<{ section: SectionDetail }>(
    `/api/model-versions/${versionId}/sections/${encodeURIComponent(sectionName)}`,
  )
  return response.section
}

export function uploadModel(input: {
  name: string
  description?: string
  createdBy?: string
  file: File
}): Promise<ImportModelResponse> {
  const body = new FormData()
  body.append('name', input.name)
  body.append('file', input.file)
  if (input.description) body.append('description', input.description)
  if (input.createdBy) body.append('created_by', input.createdBy)
  return request('/api/models', { method: 'POST', body })
}
