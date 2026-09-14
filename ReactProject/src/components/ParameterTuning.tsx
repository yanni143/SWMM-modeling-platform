import { useEffect, useMemo, useState } from 'react';
import '@/assets/css/ParameterTuning.css';
import type { EditableField, ModelVersion } from '@/api/models';
import { useModelStore } from '@/stores/modelStore';

interface Draft {
  key: string;
  section: string;
  target: string;
  field: string;
  label: string;
  unit: string;
  oldValue: string;
  newValue: string;
}
const time = (value: number) => {
  const seconds = Math.max(0, Math.round(value));
  return `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
};
const parseDate = (value: string) =>
  new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);

export default function ParameterTuning() {
  const store = useModelStore();
  const groups = store.parameterGroups;
  const [groupId, setGroupId] = useState('');
  const [target, setTarget] = useState('');
  const [targets, setTargets] = useState<string[]>([]);
  const [mode, setMode] = useState<'single' | 'batch'>('single');
  const [search, setSearch] = useState('');
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [summary, setSummary] = useState('');
  const [localError, setLocalError] = useState('');
  const [created, setCreated] = useState<ModelVersion | null>(null);
  const [batchKey, setBatchKey] = useState('');
  const [batchOperation, setBatchOperation] = useState<'set' | 'add' | 'percent'>('set');
  const [batchAmount, setBatchAmount] = useState('');
  const [duration, setDuration] = useState(0);
  const [reportStep, setReportStep] = useState(0);
  const [rainStart, setRainStart] = useState(0);
  const [rainDuration, setRainDuration] = useState(0);
  const [rainfall, setRainfall] = useState(0);
  const group = groups.find((item) => item.id === groupId);
  const objects = group?.objects ?? [];
  const filtered = objects.filter((item) =>
    item.target.toLowerCase().includes(search.toLowerCase()),
  );
  const object = objects.find((item) => item.target === target);
  const selectedObjects = objects.filter((item) => targets.includes(item.target));
  const commonFields =
    selectedObjects[0]?.fields.filter((field) =>
      selectedObjects.every((item) => item.fields.some((candidate) => candidate.key === field.key)),
    ) ?? [];
  const batchField = commonFields.find((field) => field.key === batchKey);
  const draftsList = Object.values(drafts);
  const options = store.simulationOptions;
  const rainOptions = store.rainfallOptions;
  const durationChanged = duration !== options?.duration_seconds;
  const stepChanged = reportStep !== options?.report_step_seconds;
  const rainChanged =
    !!rainOptions &&
    (rainStart !== rainOptions.start_seconds ||
      rainDuration !== rainOptions.duration_seconds ||
      rainfall !== rainOptions.total_rainfall_mm);
  const minStep = Math.max(
    options?.report_step_min_seconds ?? 1,
    Math.ceil(options?.routing_step_seconds ?? 0),
  );
  const outputSteps =
    Number.isInteger(duration) && Number.isInteger(reportStep) && reportStep > 0
      ? Math.floor(duration / reportStep)
      : 0;
  const simulationError = !options
    ? ''
    : !Number.isInteger(duration)
      ? '模拟时长必须是整数秒'
      : duration < options.duration_min_seconds || duration > options.duration_max_seconds
        ? `模拟时长必须在 ${options.duration_min_seconds}～${options.duration_max_seconds} 秒之间`
        : !Number.isInteger(reportStep)
          ? '输出步长必须是整数秒'
          : reportStep < minStep
            ? `输出步长不能小于 ${minStep} 秒`
            : reportStep > duration
              ? '输出步长不能大于模拟时长'
              : options.require_report_step_divisible && duration % reportStep !== 0
                ? '模拟时长必须能被输出步长整除'
                : outputSteps > options.max_output_steps
                  ? `输出时间点不能超过 ${options.max_output_steps} 个`
                  : '';
  const rainError = !rainOptions
    ? ''
    : !Number.isInteger(rainStart) || !Number.isInteger(rainDuration)
      ? '降雨开始时间和时长必须是整数秒'
      : rainStart < 0 || rainDuration <= 0
        ? '降雨开始时间必须不小于 0，降雨时长必须大于 0'
        : rainStart + rainDuration > duration
          ? '降雨结束时间不能超过模拟时长'
          : rainStart % rainOptions.time_step_seconds ||
              rainDuration % rainOptions.time_step_seconds
            ? `降雨开始时间和时长必须是 ${rainOptions.time_step_seconds} 秒的整数倍`
            : !Number.isFinite(rainfall) || rainfall <= 0
              ? '总降雨量必须是大于 0 的有效数值'
              : '';
  const error = localError || simulationError || rainError;
  const nextVersion = Math.max(...store.versions.map((item) => item.version), 0) + 1;
  useEffect(() => {
    setDuration(options?.duration_seconds ?? 0);
    setReportStep(options?.report_step_seconds ?? 0);
  }, [options]);
  useEffect(() => {
    setRainStart(rainOptions?.start_seconds ?? 0);
    setRainDuration(rainOptions?.duration_seconds ?? 0);
    setRainfall(rainOptions?.total_rainfall_mm ?? 0);
  }, [rainOptions]);
  useEffect(() => {
    if (!groups.some((item) => item.id === groupId)) {
      setGroupId(groups[0]?.id ?? '');
      setTarget(groups[0]?.objects[0]?.target ?? '');
    }
  }, [groups, groupId]);
  useEffect(() => {
    if (!objects.some((item) => item.target === target)) setTarget(objects[0]?.target ?? '');
    setTargets([]);
  }, [groupId]);
  useEffect(() => {
    if (!commonFields.some((field) => field.key === batchKey))
      setBatchKey(commonFields[0]?.key ?? '');
  }, [commonFields, batchKey]);
  useEffect(() => {
    setDrafts({});
    setCreated(null);
  }, [store.selectedVersionId]);
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ layerId: string; target: string }>).detail;
      const matched = groups.find(
        (item) =>
          item.map_layer === detail.layerId &&
          item.objects.some((item) => item.target === detail.target),
      );
      if (!matched) return;
      setGroupId(matched.id);
      if (mode === 'batch')
        setTargets((current) =>
          current.includes(detail.target) ? current : [...current, detail.target],
        );
      else setTarget(detail.target);
    };
    window.addEventListener('swmm:map-feature-selected', handler);
    return () => window.removeEventListener('swmm:map-feature-selected', handler);
  }, [groups, mode]);
  const key = (field: EditableField, objectTarget = target) =>
    `${field.section}|${objectTarget}|${field.field}`;
  const value = (field: EditableField) => drafts[key(field)]?.newValue ?? field.value;
  const clear = () => {
    setDrafts({});
    setLocalError('');
    setDuration(options?.duration_seconds ?? 0);
    setReportStep(options?.report_step_seconds ?? 0);
    setRainStart(rainOptions?.start_seconds ?? 0);
    setRainDuration(rainOptions?.duration_seconds ?? 0);
    setRainfall(rainOptions?.total_rainfall_mm ?? 0);
  };
  const stage = (field: EditableField, raw: string) => {
    const numeric = Number(raw);
    if (
      !object ||
      !Number.isFinite(numeric) ||
      numeric < field.minimum ||
      numeric > field.maximum
    ) {
      setLocalError(`${field.label}必须在 ${field.minimum}～${field.maximum} ${field.unit} 之间`);
      return;
    }
    const draftKey = key(field);
    if (numeric === Number(field.value)) {
      setDrafts((current) => {
        const next = { ...current };
        delete next[draftKey];
        return next;
      });
    } else
      setDrafts((current) => ({
        ...current,
        [draftKey]: {
          key: draftKey,
          section: field.section,
          target: object.target,
          field: field.field,
          label: field.label,
          unit: field.unit,
          oldValue: field.value,
          newValue: String(numeric),
        },
      }));
  };
  const applyBatch = () => {
    if (!batchField || !Number.isFinite(Number(batchAmount)))
      return setLocalError('请选择参数并输入有效数值');
    const updates: Record<string, Draft | null> = {};
    for (const item of selectedObjects) {
      const field = item.fields.find((candidate) => candidate.key === batchField.key)!;
      const draftKey = key(field, item.target);
      const current = Number(drafts[draftKey]?.newValue ?? field.value);
      let next = Number(batchAmount);
      if (batchOperation === 'add') next = current + next;
      if (batchOperation === 'percent') next = current * (1 + next / 100);
      next = Number(next.toPrecision(12));
      if (!Number.isFinite(next) || next < field.minimum || next > field.maximum)
        return setLocalError(
          `${item.target} 的${field.label}计算后为 ${next}，超出 ${field.minimum}～${field.maximum} ${field.unit}`,
        );
      updates[draftKey] =
        next === Number(field.value)
          ? null
          : {
              key: draftKey,
              section: field.section,
              target: item.target,
              field: field.field,
              label: field.label,
              unit: field.unit,
              oldValue: field.value,
              newValue: String(next),
            };
    }
    setLocalError('');
    setDrafts((current) => {
      const next = { ...current };
      Object.entries(updates).forEach(([draftKey, draft]) =>
        draft ? (next[draftKey] = draft) : delete next[draftKey],
      );
      return next;
    });
  };
  const save = async () => {
    if (error) return;
    const result = await store.saveAdjustedVersion(
      draftsList.map((draft) => ({
        section: draft.section,
        target: draft.target,
        field: draft.field,
        new_value: draft.newValue,
      })),
      summary || undefined,
      durationChanged || stepChanged
        ? { duration_seconds: duration, report_step_seconds: reportStep }
        : undefined,
      rainChanged
        ? { start_seconds: rainStart, duration_seconds: rainDuration, total_rainfall_mm: rainfall }
        : undefined,
    );
    if (result) {
      setCreated(result.version);
      setSummary('');
      clear();
    }
  };
  const runCreated = async () => {
    const result = await store.runSelectedVersion();
    if (result) window.dispatchEvent(new CustomEvent('swmm:run-completed', { detail: result }));
  };
  const estimate = useMemo(() => {
    if (!options || duration <= 0) return '—';
    const date = new Date(parseDate(options.start_datetime).getTime() + duration * 1000);
    const pad = (part: number) => String(part).padStart(2, '0');
    return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
  }, [duration, options]);
  return (
    <section className="tuning-workspace" aria-label="参数设置">
      <div className="tuning-heading">
        <div>
          <h3>模拟参数设置</h3>
        </div>
        {(durationChanged || stepChanged || rainChanged) && (
          <span>
            {Number(durationChanged) + Number(stepChanged) + Number(rainChanged)} 项待保存
          </span>
        )}
      </div>
      {options && (
        <div className="simulation-settings">
          <div className="simulation-setting-fields">
            <label>
              <span>
                模拟时长 <small>秒</small>
              </span>
              <input
                value={duration}
                type="number"
                min={options.duration_min_seconds}
                max={options.duration_max_seconds}
                step="1"
                onChange={(event) => setDuration(Number(event.target.value))}
              />
              <small>
                {options.duration_min_seconds}～{options.duration_max_seconds} 秒
              </small>
            </label>
            <label>
              <span>
                输出步长 <small>秒</small>
              </span>
              <input
                value={reportStep}
                type="number"
                min={minStep}
                max={duration || undefined}
                step="1"
                onChange={(event) => setReportStep(Number(event.target.value))}
              />
              <small>
                不小于路由步长 {options.routing_step_seconds} 秒
              </small>
            </label>
          </div>
          <div className="simulation-projection">
            <span>预计结束</span>
            <strong>{estimate}</strong>
            <output>{outputSteps} 个输出点</output>
            {options.require_report_step_divisible && <em>时长须能被输出步长整除</em>}
          </div>
        </div>
      )}
      {rainOptions && (
        <div className="rainfall-settings">
          <div className="rainfall-setting-fields">
            <label>
              <span>
                降雨开始 <small>秒</small>
              </span>
              <input
                value={rainStart}
                type="number"
                min="0"
                max={duration}
                step={rainOptions.time_step_seconds}
                onChange={(event) => setRainStart(Number(event.target.value))}
              />
              <small>{time(rainStart)}</small>
            </label>
            <label>
              <span>
                降雨时长 <small>秒</small>
              </span>
              <input
                value={rainDuration}
                type="number"
                min="0"
                max={Math.max(0, duration - rainStart)}
                step={rainOptions.time_step_seconds}
                onChange={(event) => setRainDuration(Number(event.target.value))}
              />
              <small>{time(rainDuration)}</small>
            </label>
            <label>
              <span>
                总降雨量 <small>mm</small>
              </span>
              <input
                value={rainfall}
                type="number"
                min="0"
                step="0.1"
                onChange={(event) => setRainfall(Number(event.target.value))}
              />
              <small>
                当前峰值 {rainOptions.peak_rainfall_mm_h.toFixed(2)} mm/h
              </small>
            </label>
            <div className="rainfall-derived">
              <span>降雨结束</span>
              <strong>{time(rainStart + rainDuration)}</strong>
              <small>峰现系数 {rainOptions.peak_ratio}</small>
            </div>
          </div>
        </div>
      )}
      <div className="engineering-heading tuning-heading">
        <div>
          <h3>工程参数修改</h3>
        </div>
        {draftsList.length > 0 && <span>{draftsList.length} 项待保存</span>}
      </div>
      <div className="selection-mode" aria-label="选择方式">
        <button
          type="button"
          className={mode === 'single' ? 'active' : ''}
          onClick={() => setMode('single')}
        >
          单个选择
        </button>
        <button
          type="button"
          className={mode === 'batch' ? 'active' : ''}
          onClick={() => {
            setMode('batch');
            if (!targets.length && target) setTargets([target]);
          }}
        >
          批量选择 {targets.length > 0 && <b>{targets.length}</b>}
        </button>
      </div>
      <div className="group-tabs" role="tablist" aria-label="对象类型">
        {groups.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === groupId ? 'active' : ''}
            onClick={() => {
              setGroupId(item.id);
              setSearch('');
            }}
          >
            {item.label} <b>{item.objects.length}</b>
          </button>
        ))}
      </div>
      {group && (
        <div className="object-picker">
          <input
            value={search}
            type="search"
            placeholder="搜索对象编号"
            onChange={(event) => setSearch(event.target.value)}
          />
          {mode === 'single' ? (
            <select
              value={target}
              size={5}
              onChange={(event) => setTarget(event.target.value)}
            >
              {filtered.map((item) => (
                <option key={item.target} value={item.target}>
                  {item.target}
                </option>
              ))}
            </select>
          ) : (
            <div className="batch-object-list">
              <div className="batch-list-actions">
                <button
                  type="button"
                  onClick={() =>
                    setTargets(
                      Array.from(new Set([...targets, ...filtered.map((item) => item.target)])),
                    )
                  }
                >
                  全选搜索结果
                </button>
                <button type="button" onClick={() => setTargets([])}>
                  清空
                </button>
              </div>
              {filtered.map((item) => (
                <label
                  key={item.target}
                >
                  <input
                    type="checkbox"
                    checked={targets.includes(item.target)}
                    onChange={() =>
                      setTargets((current) =>
                        current.includes(item.target)
                          ? current.filter((value) => value !== item.target)
                          : [...current, item.target],
                      )
                    }
                  />
                  <span>{item.target}</span>
                </label>
              ))}
              {filtered.length === 0 && <p>没有匹配对象</p>}
            </div>
          )}
        </div>
      )}
      {mode === 'single' && object && (
        <div className="object-editor">
          <div className="object-identity">
            <span>当前对象</span>
            <strong>{object.target}</strong>
            <em>也可直接点击地图要素切换</em>
          </div>
          <div className="field-grid">
            {object.fields.map((field) => (
              <label key={field.key}>
                <span>
                  {field.label} <small>{field.unit}</small>
                </span>
                <input
                  type="number"
                  value={value(field)}
                  min={field.minimum}
                  max={field.maximum}
                  step={field.step}
                  onChange={(event) => stage(field, event.target.value)}
                />
                <small>
                  {field.minimum} ～ {field.maximum} {field.unit}
                </small>
              </label>
            ))}
          </div>
        </div>
      )}
      {mode === 'batch' && targets.length > 0 && (
        <div className="batch-editor">
          <div className="batch-editor-heading">
            <div>
              <strong>
                已选择 {targets.length} 个{group?.label}
              </strong>
            </div>
          </div>
          {commonFields.length ? (
            <div className="batch-controls">
              <label>
                <span>调整参数</span>
                <select value={batchKey} onChange={(event) => setBatchKey(event.target.value)}>
                  {commonFields.map((field) => (
                    <option key={field.key} value={field.key}>
                      {field.label} {field.unit ? `(${field.unit})` : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>调整方式</span>
                <select
                  value={batchOperation}
                  onChange={(event) =>
                    setBatchOperation(event.target.value as typeof batchOperation)
                  }
                >
                  <option value="set">设置为</option>
                  <option value="add">增加 / 减少</option>
                  <option value="percent">按比例调整</option>
                </select>
              </label>
              <label>
                <span>{batchOperation === 'percent' ? '调整比例' : '数值'}</span>
                <div className="batch-value-input">
                  <input
                    value={batchAmount}
                    type="number"
                    step={batchField?.step ?? 'any'}
                    onChange={(event) => setBatchAmount(event.target.value)}
                  />
                  <small>{batchOperation === 'percent' ? '%' : batchField?.unit}</small>
                </div>
              </label>
              <button type="button" onClick={applyBatch}>
                计算并加入变更预览
              </button>
            </div>
          ) : (
            <p className="no-common-fields">
              所选对象没有共同的可调参数，请选择同一种节点类型。
            </p>
          )}
        </div>
      )}
      {error && (
        <p className="tuning-error" role="alert">
          {error}
        </p>
      )}
      {draftsList.length || durationChanged || stepChanged || rainChanged ? (
        <div className="change-ruler">
          <div className="change-ruler-title">
            <span>变更预览</span>
            <button type="button" onClick={clear}>
              全部撤销
            </button>
          </div>
          {durationChanged && (
            <Change
              label="模拟时长"
              oldValue={`${options?.duration_seconds} 秒`}
              newValue={`${duration} 秒`}
              onRemove={() => setDuration(options?.duration_seconds ?? 0)}
            />
          )}
          {stepChanged && (
            <Change
              label="输出步长"
              oldValue={`${options?.report_step_seconds} 秒`}
              newValue={`${reportStep} 秒`}
              onRemove={() => setReportStep(options?.report_step_seconds ?? 0)}
            />
          )}
          {rainChanged && (
            <Change
              label="设计降雨"
              oldValue={`${time(rainOptions!.start_seconds)}–${time(rainOptions!.start_seconds + rainOptions!.duration_seconds)} · ${rainOptions!.total_rainfall_mm} mm`}
              newValue={`${time(rainStart)}–${time(rainStart + rainDuration)} · ${rainfall} mm`}
              onRemove={() => {
                setRainStart(rainOptions!.start_seconds);
                setRainDuration(rainOptions!.duration_seconds);
                setRainfall(rainOptions!.total_rainfall_mm);
              }}
            />
          )}
          {draftsList.map((draft) => (
            <Change
              key={draft.key}
              label={`${draft.target} · ${draft.label}`}
              oldValue={draft.oldValue}
              newValue={`${draft.newValue} ${draft.unit}`}
              onRemove={() =>
                setDrafts((current) => {
                  const next = { ...current };
                  delete next[draft.key];
                  return next;
                })
              }
            />
          ))}
          <input
            value={summary}
            maxLength={500}
            placeholder="版本说明，例如：降低管线粗糙度"
            onChange={(event) => setSummary(event.target.value)}
          />
          <button
            className="save-version"
            type="button"
            disabled={store.savingVersion || !!error}
            onClick={() => void save()}
          >
            {store.savingVersion ? '正在校验并生成…' : `校验并生成 V${nextVersion}`}
          </button>
        </div>
      ) : null}
      {created && (
        <div className="version-created">
          <div>
            <strong>新版本 V{created.version} 已生成</strong>
          </div>
          <button type="button" disabled={store.running} onClick={() => void runCreated()}>
            {store.running ? '正在运行…' : `运行 V${created.version}`}
          </button>
        </div>
      )}
    </section>
  );
}
function Change({
  label,
  oldValue,
  newValue,
  onRemove,
}: {
  label: string;
  oldValue: string;
  newValue: string;
  onRemove: () => void;
}) {
  return (
    <div className="change-line">
      <span>{label}</span>
      <code>{oldValue}</code>
      <i>→</i>
      <code>{newValue}</code>
      <button type="button" onClick={onRemove}>
        ×
      </button>
    </div>
  );
}
