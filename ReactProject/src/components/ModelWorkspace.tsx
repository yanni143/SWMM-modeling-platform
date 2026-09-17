import { useEffect } from 'react';
import '@/assets/css/ModelWorkspace.css';
import {
  latestLisfloodInputUrl,
  latestLisfloodVirtualRainfallUrl,
} from '@/api/models';
import { useModelStore } from '@/stores/modelStore';
import ParameterTuning from './ParameterTuning';

const formatBytes = (value: number | null) =>
  value === null ? '大小未知' : value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KB`;
const formatTime = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
const studyAreaName = (name: string) => ({ LC: '老城', JJ: '金江' }[name] ?? name);

export default function ModelWorkspace() {
  const store = useModelStore();
  useEffect(() => {
    void store.loadModels();
  }, []);
  const selected = store.models.find((item) => item.id === store.selectedModelId) ?? null;
  const run = async () => {
    const result = await store.runSelectedVersion();
    if (result) window.dispatchEvent(new CustomEvent('swmm:run-completed', { detail: result }));
  };
  const reset = async () => {
    await store.restoreInitialState();
    window.dispatchEvent(new Event('swmm:workspace-reset'));
  };
  return (
    <aside className="model-workspace" aria-label="工程工作台">
      <div className="workspace-heading">
        <div>
          <p className="workspace-kicker">
            SWMM STUDY AREA
          </p>
          <h2>{selected ? studyAreaName(selected.name) : '模型工作台'}</h2>
        </div>
        <div className="workspace-status">
          <span className="system-state">
            <i /> INP READY
          </span>
          <button type="button" onClick={() => void store.loadModels()}>
            刷新
          </button>
        </div>
      </div>
      {store.error && (
        <p className="error-message" role="alert">
          {store.error}
        </p>
      )}
      {selected && (
        <section className="study-area-summary">
          {store.models.length > 1 && (
            <label className="study-area-picker">
              <span>研究区</span>
              <select
                className="ledger-select"
                value={store.selectedModelId ?? ''}
                aria-label="选择研究区"
                disabled={store.running}
                onChange={(event) => event.target.value && void store.selectModel(event.target.value)}
              >
                {store.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {studyAreaName(model.name)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="model-facts">
            <div>
              <span>状态</span>
              <strong>已就绪</strong>
            </div>
            <div>
              <span>版本数</span>
              <strong>{selected.version_count}</strong>
            </div>
            <div>
              <span>最新版本</span>
              <strong>V{selected.latest_version ?? '—'}</strong>
            </div>
          </div>
        </section>
      )}
      {store.versions.length > 0 && (
        <section className="ledger-section">
          <div className="section-title">
            <span>工程版本</span>
            <em>每次调参生成新版本</em>
          </div>
          <select
            className="ledger-select"
            value={store.selectedVersionId ?? ''}
            aria-label="选择工程版本"
            onChange={(event) => event.target.value && void store.selectVersion(event.target.value)}
          >
            {store.versions.map((version) => (
              <option key={version.id} value={version.id}>
                V{version.version} · {formatBytes(version.size_bytes)}
              </option>
            ))}
          </select>
          <button
            className="run-action"
            type="button"
            disabled={store.running || !store.selectedVersionId}
            onClick={run}
          >
            {store.running ? '正在运行并解析结果…' : '运行当前版本'}
          </button>
        </section>
      )}
      {store.availableResults.length > 0 && (
        <section className="ledger-section">
          <div className="section-title">
            <span>历史模拟结果</span>
            <em>每个版本保留最新结果</em>
          </div>
          <select
            className="ledger-select"
            value={store.activeResultVersionId ?? ''}
            disabled={store.running}
            aria-label="选择要显示的模拟结果版本"
            onChange={(event) =>
              event.target.value && store.activateResultVersion(event.target.value)
            }
          >
            <option value="" disabled>
              选择一个结果版本
            </option>
            {store.availableResults.map((result) => (
              <option key={result.version_id} value={result.version_id}>
                V{result.version} · {formatTime(result.finished_at || result.created_at)}
              </option>
            ))}
          </select>
          {store.activeResultVersionId && (
            <>
              <a
                className="run-action lisflood-download"
                href={latestLisfloodInputUrl(store.activeResultVersionId)}
              >
                下载 LISFLOOD 点源输入
              </a>
              <a
                className="run-action lisflood-download"
                href={latestLisfloodVirtualRainfallUrl(store.activeResultVersionId)}
              >
                下载 LISFLOOD 虚拟降雨
              </a>
            </>
          )}
        </section>
      )}
      <button
        className="reset-action"
        type="button"
        disabled={store.running}
        onClick={reset}
      >
        恢复初始状态
      </button>
      {store.selectedVersionId && store.parameterGroups.length > 0 && <ParameterTuning />}
    </aside>
  );
}
