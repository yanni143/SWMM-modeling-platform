import { useEffect, useMemo, useState } from 'react';
import {
  previewRainfall,
  type RainfallMode,
  type RainfallOptions,
  type RainfallOptionsInput,
} from '@/api/models';
import { parseRainfallText, rainfallStats } from '@/utils/rainfall';

export interface RainfallDraft {
  input?: RainfallOptionsInput;
  changed: boolean;
  error: string;
  description: string;
}

const labels = { design: '芝加哥雨型', real: '真实降雨', custom: '自定义序列' };

export default function RainfallEditor({
  current,
  duration,
  studyArea,
  resetToken,
  onChange,
}: {
  current: RainfallOptions;
  duration: number;
  studyArea: string;
  resetToken: number;
  onChange: (draft: RainfallDraft) => void;
}) {
  const [source, setSource] = useState<RainfallMode>(current.mode);
  const [start, setStart] = useState(current.start_seconds);
  const [step, setStep] = useState(current.time_step_seconds);
  const [wetDuration, setWetDuration] = useState(current.duration_seconds);
  const [total, setTotal] = useState(current.total_rainfall_mm);
  const [text, setText] = useState(current.values_mm.join('\n'));
  const [preview, setPreview] = useState<number[]>(current.values_mm);
  const [previewError, setPreviewError] = useState('');
  const [previewing, setPreviewing] = useState(false);
  const event = current.real_event;
  useEffect(() => {
    setSource(current.mode);
    setStart(current.start_seconds);
    setStep(current.time_step_seconds);
    setWetDuration(current.duration_seconds);
    setTotal(current.total_rainfall_mm);
    setText(current.values_mm.join('\n'));
    setPreview(current.values_mm);
    setPreviewError('');
    setPreviewing(false);
  }, [current, resetToken]);

  const draft = useMemo(() => {
    let error = '';
    let values: number[] = [];
    let input: RainfallOptionsInput | undefined;
    if (!Number.isInteger(start) || start < 0) error = '降雨开始必须是不小于 0 的整数秒';
    if (source === 'design') {
      input = {
        mode: 'design',
        start_seconds: start,
        duration_seconds: wetDuration,
        total_rainfall_mm: total,
      };
      if (!Number.isInteger(wetDuration) || wetDuration <= 0 || start % 300 || wetDuration % 300)
        error ||= '芝加哥雨型开始时间和时长须为 300 秒的整数倍，时长须大于 0';
      if (!Number.isFinite(total) || total <= 0) error ||= '总降雨量必须大于 0';
    } else if (source === 'real') {
      if (!event) error ||= '当前研究区暂无内置真实降雨事件';
      else values = event.values_mm;
      input = { mode: 'real', event_id: event?.event_id ?? '', start_seconds: start };
    } else {
      if (!Number.isInteger(step) || step <= 0) error ||= '记录间隔必须是大于 0 的整数秒';
      try {
        values = parseRainfallText(text, step);
      } catch (reason) {
        error ||= (reason as Error).message;
      }
      input = { mode: 'custom', start_seconds: start, time_step_seconds: step, values_mm: values };
    }
    const interval =
      source === 'design' ? 300 : source === 'real' ? (event?.time_step_seconds ?? 300) : step;
    const length = source === 'design' ? wetDuration : values.length * interval;
    if (start + length > duration)
      error ||= `降雨覆盖到 ${start + length} 秒，超过模拟时长 ${duration} 秒，请调整模拟时长或序列`;
    const changed =
      source !== current.mode ||
      start !== current.start_seconds ||
      (source === 'design'
        ? wetDuration !== current.duration_seconds || total !== current.total_rainfall_mm
        : source === 'custom'
          ? step !== current.time_step_seconds ||
            JSON.stringify(values) !== JSON.stringify(current.values_mm)
          : event?.event_id !== current.event_id);
    return { input, changed, error, values, interval, length };
  }, [source, start, wetDuration, total, step, text, duration, current, event]);

  // Chicago previews use the server's existing generator, never a second formula in JS.
  useEffect(() => {
    let active = true;
    setPreviewError('');
    if (draft.error || source !== 'design' || !draft.changed) {
      setPreviewing(false);
      setPreview(source === 'design' ? current.values_mm : draft.values);
      return;
    }
    setPreviewing(true);
    const timer = window.setTimeout(() => {
      previewRainfall(studyArea, duration, draft.input!)
        .then((result) => {
          if (active) {
            setPreview(result.values_mm);
            setPreviewing(false);
          }
        })
        .catch((reason: Error) => {
          if (active) {
            setPreviewError(reason.message);
            setPreviewing(false);
          }
        });
    }, 300);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [draft, source, studyArea, duration, current]);

  const stats = rainfallStats(preview, draft.interval);
  useEffect(() => {
    onChange({
      input: draft.changed ? draft.input : undefined,
      changed: draft.changed,
      error: draft.error || previewError || (previewing ? '正在预览降雨序列…' : ''),
      description: `${labels[source]} · ${draft.length} 秒 · ${source === 'design' ? total : rainfallStats(draft.values, draft.interval).total.toFixed(2)} mm`,
    });
  }, [draft, previewError, previewing, source, total, onChange]);

  const changeSource = (next: RainfallMode) => {
    // Keep the current rainfall when converting to editable custom data.
    if (next === 'custom') {
      setText(preview.join('\n'));
      setStep(draft.interval);
    }
    if (next === 'real') setStart(0);
    setSource(next);
  };
  const importFile = async (file?: File) => {
    if (!file) return;
    if (file.size > 1024 * 1024) {
      setPreviewError('CSV 文件不能超过 1 MB');
      return;
    }
    try {
      setText(await file.text());
      setPreviewError('');
    } catch {
      setPreviewError('文件读取失败，请重新选择 CSV 文件');
    }
  };

  // Bin only for rendering; the editor and submitted data retain every original value.
  const bins = 120;
  const stride = Math.max(1, Math.ceil(preview.length / bins));
  const bars = Array.from({ length: Math.ceil(preview.length / stride) }, (_, index) =>
    Math.max(0, ...preview.slice(index * stride, (index + 1) * stride)),
  );
  const max = Math.max(1e-9, ...bars);
  return (
    <div className="rainfall-settings">
      <div className="rainfall-editor-title">
        <h3>降雨设置</h3>
        <span>保存后应用于当前工程版本</span>
      </div>
      <div className="rainfall-setting-fields">
        <label>
          <span>降雨来源</span>
          <select value={source} onChange={(e) => changeSource(e.target.value as RainfallMode)}>
            <option value="design">芝加哥雨型</option>
            <option value="real" disabled={!event}>
              真实降雨{!event ? '（暂无内置事件）' : ''}
            </option>
            <option value="custom">自定义序列</option>
          </select>
        </label>
        <label>
          <span>
            降雨开始 <small>秒</small>
          </span>
          <input
            type="number"
            min="0"
            step="1"
            value={start}
            onChange={(e) => setStart(Number(e.target.value))}
          />
          <small>相对模拟开始的偏移</small>
        </label>
        {source === 'design' && (
          <>
            <label>
              <span>
                降雨时长 <small>秒</small>
              </span>
              <input
                type="number"
                min="300"
                step="300"
                value={wetDuration}
                onChange={(e) => setWetDuration(Number(e.target.value))}
              />
            </label>
            <label>
              <span>
                总降雨量 <small>mm</small>
              </span>
              <input
                type="number"
                min="0.01"
                step="any"
                value={total}
                onChange={(e) => setTotal(Number(e.target.value))}
              />
            </label>
          </>
        )}
        {source === 'real' && event && (
          <label className="rainfall-full">
            <span>真实降雨事件</span>
            <select value={event.event_id} onChange={() => {}}>
              <option value={event.event_id}>{event.label}</option>
            </select>
            <small>
              {event.start_datetime.replace('T', ' ')} 至 {event.end_datetime.replace('T', ' ')}
              ；按相对时间应用到当前模拟，原始日期仅作资料说明。
            </small>
          </label>
        )}
        {source === 'custom' && (
          <label className="rainfall-full">
            <span>
              记录间隔 <small>秒</small>
            </span>
            <input
              type="number"
              min="1"
              step="1"
              value={step}
              onChange={(e) => setStep(Number(e.target.value))}
            />
            <small>每个值为该间隔内的雨量（mm），时长和总雨量由序列计算。</small>
          </label>
        )}
      </div>
      {source === 'custom' && (
        <div className="rainfall-sequence">
          <label htmlFor="rainfall-values">
            分段雨量序列 <small>每行一个 mm 值，支持从表格粘贴</small>
          </label>
          <textarea
            id="rainfall-values"
            value={text}
            spellCheck={false}
            onChange={(e) => setText(e.target.value)}
            aria-describedby="rainfall-csv-help"
          />
          <div className="rainfall-import">
            <label>
              导入 CSV
              <input
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                onChange={(e) => {
                  void importFile(e.target.files?.[0]);
                  e.target.value = '';
                }}
              />
            </label>
            <a
              download="rainfall-template.csv"
              href="data:text/csv;charset=utf-8,offset_seconds%2Crainfall_mm%0A0%2C0%0A300%2C1.5%0A600%2C0%0A"
            >
              下载 300 秒模板
            </a>
          </div>
          <small id="rainfall-csv-help">
            也可使用两列：offset_seconds,rainfall_mm。偏移从 0 按记录间隔连续排列；例如 0,1.5
            表示第一个间隔降雨 1.5 mm。空白行忽略，最多 10000 条。
          </small>
        </div>
      )}
      <div className="rainfall-preview" aria-busy={previewing}>
        <div>
          <span>降雨过程</span>
          <small>
            {draft.interval} 秒间隔 · {draft.length} 秒覆盖 · {preview.length} 条记录
          </small>
        </div>
        <svg
          viewBox="0 0 600 100"
          role="img"
          aria-label="降雨过程图，横轴为降雨覆盖时间，柱高表示分段雨量"
        >
          {bars.map((value, index) => (
            <rect
              key={index}
              x={(index * 600) / bars.length}
              y={95 - (value / max) * 85}
              width={Math.max(1, 600 / bars.length - 1)}
              height={(value / max) * 85}
            >
              <title>
                {index * stride * draft.interval} 秒起：最高 {value.toFixed(3)} mm / 间隔
              </title>
            </rect>
          ))}
          <line x1="0" y1="95" x2="600" y2="95" />
        </svg>
        <div className="rainfall-time-axis">
          <small>0 秒</small>
          <small>{draft.length} 秒</small>
        </div>
        <div>
          <strong>{stats.total.toFixed(2)} mm</strong>
          <span>总雨量</span>
          <strong>{stats.peak.toFixed(2)} mm/h</strong>
          <span>峰值雨强</span>
        </div>
        {stride > 1 && <small>图中按区间最大值汇总显示，保存使用完整序列。</small>}
      </div>
    </div>
  );
}
