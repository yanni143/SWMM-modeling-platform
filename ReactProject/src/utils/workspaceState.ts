export interface WorkspaceState {
  schemaVersion?: 2;
  selectedModelId?: string;
  selectedVersionsByModel?: Record<string, string>;
  activeResultsByModel?: Record<string, string | null>;
  selectedVersionId?: string;
  activeResultVersionId?: string | null;
  layerOrder?: string[];
  layerVisibility?: Record<string, boolean>;
}

const WORKSPACE_STATE_KEY = 'swmm-workspace:v1';

// Retain the selected legacy real/design version, but stop splitting model history by source.
export function migrateWorkspaceState(raw: Record<string, any>): WorkspaceState {
  if (raw.schemaVersion === 2) return raw;
  const selectedVersionsByModel = { ...raw.selectedVersionsByModel };
  const activeResultsByModel = { ...raw.activeResultsByModel };
  const ids = new Set<string>([
    ...Object.keys(raw.rainfallModes ?? {}),
    ...Object.keys(raw.selectedVersionsByInput ?? {}).map((key) =>
      key.slice(0, key.lastIndexOf(':')),
    ),
  ]);
  for (const id of ids) {
    const scope = `${id}:${raw.rainfallModes?.[id] ?? 'design'}`;
    const version = raw.selectedVersionsByInput?.[scope];
    if (version) selectedVersionsByModel[id] = version;
    activeResultsByModel[id] = raw.activeResultsByInput?.[scope] ?? null;
  }
  if (raw.selectedModelId && raw.selectedVersionId && !selectedVersionsByModel[raw.selectedModelId])
    selectedVersionsByModel[raw.selectedModelId] = raw.selectedVersionId;
  if (
    raw.selectedModelId &&
    raw.activeResultVersionId &&
    !(raw.selectedModelId in activeResultsByModel)
  )
    activeResultsByModel[raw.selectedModelId] = raw.activeResultVersionId;
  return {
    schemaVersion: 2,
    selectedModelId: raw.selectedModelId,
    selectedVersionsByModel,
    activeResultsByModel,
    selectedVersionId: raw.selectedVersionId,
    activeResultVersionId: raw.activeResultVersionId,
    layerOrder: raw.layerOrder,
    layerVisibility: raw.layerVisibility,
  };
}

export function loadWorkspaceState(): WorkspaceState {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STATE_KEY);
    return raw ? migrateWorkspaceState(JSON.parse(raw)) : { schemaVersion: 2 };
  } catch {
    return { schemaVersion: 2 };
  }
}

export function saveWorkspaceState(patch: Partial<WorkspaceState>): void {
  const next = { ...loadWorkspaceState(), ...patch, schemaVersion: 2 };
  window.localStorage.setItem(WORKSPACE_STATE_KEY, JSON.stringify(next));
}

export function clearWorkspaceState(): void {
  window.localStorage.removeItem(WORKSPACE_STATE_KEY);
}
