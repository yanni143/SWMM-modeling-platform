const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/').replace(/\/$/, '')

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

export interface ProjectGeoJsonLayer {
  id: string
  name: string
  geometry_type: 'fill' | 'line' | 'circle'
  source: 'inp' | 'simulation'
  source_crs?: string
  display_crs?: string
  geojson: {
    type: 'FeatureCollection'
    features: Array<Record<string, unknown>>
  }
}

export interface ProjectRunResponse {
  run_id: string
  model_version_id: string
  version: number
  status: string
  layers: ProjectGeoJsonLayer[]
  artifacts: Array<Record<string, unknown>>
}

export interface ModelResultSummary {
  version_id: string
  version: number
  effective_run_id: string
  created_at: string
  finished_at: string | null
}

export interface VersionResultLayers extends ModelResultSummary {
  layers: ProjectGeoJsonLayer[]
}

export interface SimulationTimelineStep {
  time_index: number
  timestamp: string | null
}

export interface ResultValueRange {
  minimum: number
  maximum: number
}

export interface ResultTimeline {
  version_id: string
  version: number
  effective_run_id: string
  steps: SimulationTimelineStep[]
  result_ranges: Record<string, Record<string, ResultValueRange>>
  result_metadata: Record<string, Record<string, { unit: string | null }>>
}

export interface ResultTimeSeries {
  type: 'FeatureCollection'
  features: Array<Record<string, any>>
  field_metadata: Record<string, { unit: string | null }>
}

export interface EditableField {
  key: string
  section: string
  field: string
  label: string
  unit: string
  value: string
  minimum: number
  maximum: number
  step: number
}

export interface EditableObject {
  target: string
  element_type: string
  fields: EditableField[]
}

export interface EditableGroup {
  id: string
  label: string
  map_layer: string
  objects: EditableObject[]
}

export interface SimulationOptions {
  start_datetime: string
  end_datetime: string
  duration_seconds: number
  report_step_seconds: number
  routing_step_seconds: number
  duration_min_seconds: number
  duration_max_seconds: number
  report_step_min_seconds: number
  max_output_steps: number
  require_report_step_divisible: boolean
}

export interface EditableParametersResponse {
  groups: EditableGroup[]
  simulation_options: SimulationOptions
}

export interface SimulationOptionsInput {
  duration_seconds: number
  report_step_seconds: number
}

export interface ParameterChangeInput {
  section: string
  target: string
  field: string
  new_value: string
}

export interface AdjustedVersionResponse {
  version: ModelVersion
  changes: Array<ParameterChangeInput & { old_value: string; label: string; unit: string }>
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

export async function fetchProjectLayers(versionId: string): Promise<ProjectGeoJsonLayer[]> {
  const response = await request<{ layers: ProjectGeoJsonLayer[] }>(
    `/api/model-versions/${versionId}/layers`,
  )
  return response.layers
}

export function runProjectVersion(versionId: string): Promise<ProjectRunResponse> {
  return request(`/api/model-versions/${versionId}/runs`, { method: 'POST' })
}

export function fetchModelResults(): Promise<ModelResultSummary[]> {
  return request('/api/model-results')
}

export function fetchLatestVersionResultLayers(versionId: string): Promise<VersionResultLayers> {
  return request(`/api/model-versions/${versionId}/latest-result/layers`)
}

export function fetchResultTimeline(versionId: string): Promise<ResultTimeline> {
  return request(`/api/model-versions/${versionId}/latest-result/timeline`)
}

export function fetchResultStep(
  versionId: string,
  timeIndex: number,
  signal?: AbortSignal,
): Promise<VersionResultLayers> {
  return request(`/api/model-versions/${versionId}/latest-result/steps/${timeIndex}`, { signal })
}

export function fetchLatestVersionTimeSeries(
  versionId: string,
  layerId: string,
  featureName: string,
): Promise<ResultTimeSeries> {
  const params = new URLSearchParams({ layer_id: layerId, feature_name: featureName })
  return request(`/api/model-versions/${versionId}/latest-result/timeseries?${params}`)
}

export function fetchEditableParameters(versionId: string): Promise<EditableParametersResponse> {
  return request<EditableParametersResponse>(`/api/model-versions/${versionId}/editable-parameters`)
}

export function createAdjustedVersion(
  versionId: string,
  changes: ParameterChangeInput[],
  summary?: string,
  simulationOptions?: SimulationOptionsInput,
): Promise<AdjustedVersionResponse> {
  return request(`/api/model-versions/${versionId}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ changes, summary, simulation_options: simulationOptions }),
  })
}
