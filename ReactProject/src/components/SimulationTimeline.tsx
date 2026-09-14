import { useEffect, useMemo, useState } from 'react';
import type { ResultTimeline, SimulationTimelineStep } from '@/api/models';
import '@/assets/css/SimulationTimeline.css';

export default function SimulationTimeline({
  steps,
  activeTimeIndex,
  ranges,
  metadata,
  playing,
  loading,
  onTimeChange,
  onToggle,
}: {
  steps: SimulationTimelineStep[];
  activeTimeIndex: number;
  ranges: ResultTimeline['result_ranges'];
  metadata: ResultTimeline['result_metadata'];
  playing: boolean;
  loading: boolean;
  onTimeChange: (time: number) => void;
  onToggle: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);
  const current = Math.max(
    steps.findIndex((step) => step.time_index === activeTimeIndex),
    0,
  );
  useEffect(() => setPreview(null), [activeTimeIndex]);
  const position = preview ?? current;
  const format = (value?: string | null, compact = false) => {
    if (!value) return '—';
    const [date, time = ''] = value.split('T');
    return compact ? `${date.slice(5)} ${time.slice(0, 5)}` : `${date} ${time.slice(0, 8)}`;
  };
  const legends = useMemo(
    () =>
      [
        ['nodes-depth', '节点水深', 'depth', 'result-nodes', 'depth'],
        ['conduits-depth', '管线水深', 'depth', 'result-conduits', 'depth'],
        ['nodes-flooding', '节点溢流量', 'flooding', 'result-nodes', 'flooding'],
      ] as const,
    [],
  );
  return (
    <section className="result-presentation" aria-label="结果演示">
      <button
        className="result-top"
        type="button"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span>结果演示</span>
        <i>{collapsed ? '+' : '−'}</i>
      </button>
      {!collapsed && (
        <div className="result-content">
          <aside className="result-legends" aria-label="模拟结果图例">
            {legends.map(([id, label, palette, layer, field]) => {
              const range = ranges[layer]?.[field] ?? { minimum: 0, maximum: 0 };
              const unit = metadata[layer]?.[field]?.unit ?? '';
              return (
                <div key={id} className="result-legend">
                  <strong>{label}</strong>
                  <i className={palette} aria-hidden="true" />
                  <div className="legend-values">
                    <span>
                      {Number(range.minimum).toLocaleString('zh-CN', { maximumFractionDigits: 3 })}
                    </span>
                    <span>
                      {Number(range.maximum).toLocaleString('zh-CN', { maximumFractionDigits: 3 })}{' '}
                      {unit}
                    </span>
                  </div>
                </div>
              );
            })}
          </aside>
          <div className="simulation-timeline" aria-label="模拟结果时间轴">
            <div className="timeline-header">
              <button
                className="play-button"
                type="button"
                aria-label={playing ? '暂停动画' : '播放动画'}
                onClick={onToggle}
              >
                {playing ? 'Ⅱ' : '▶'}
              </button>
              <div className="current-time">
                <strong>{format(steps[position]?.timestamp)}</strong>
              </div>
              <span
                className={`loading-spinner${loading ? ' active' : ''}`}
                role="status"
                aria-label={loading ? '正在读取时间步' : undefined}
                aria-hidden={loading ? undefined : 'true'}
              />
              <span className="step-count">
                {current + 1}/{steps.length}
              </span>
            </div>
            <input
              className="timeline-range"
              type="range"
              min="0"
              max={Math.max(steps.length - 1, 0)}
              step="1"
              value={position}
              disabled={steps.length < 2}
              aria-label="选择模拟时间步"
              onChange={(event) => {
                const next = Number(event.target.value);
                setPreview(next);
                onTimeChange(steps[next].time_index);
              }}
              onKeyDown={(event) => {
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                  event.preventDefault();
                  const next = Math.max(
                    0,
                    Math.min(steps.length - 1, position + (event.key === 'ArrowLeft' ? -1 : 1)),
                  );
                  setPreview(next);
                  onTimeChange(steps[next].time_index);
                }
              }}
            />
            <div className="timeline-endpoints">
              <span>{format(steps[0]?.timestamp, true)}</span>
              <span>{format(steps.at(-1)?.timestamp, true)}</span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
