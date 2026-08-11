export interface WorkspaceState {
  selectedVersionId?: string
  activeResultVersionId?: string | null
  layerOrder?: string[]
  layerVisibility?: Record<string, boolean>
}

const WORKSPACE_STATE_KEY = 'swmm-demo-workspace:v1'

export function loadWorkspaceState(): WorkspaceState {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STATE_KEY)
    return raw ? (JSON.parse(raw) as WorkspaceState) : {}
  } catch {
    return {}
  }
}

export function saveWorkspaceState(patch: Partial<WorkspaceState>): void {
  const next = { ...loadWorkspaceState(), ...patch }
  window.localStorage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(next))
}

export function clearWorkspaceState(): void {
  window.localStorage.removeItem(WORKSPACE_STATE_KEY)
}
