import { useState, type DragEvent, type KeyboardEvent } from 'react';
import '@/assets/css/LayerControl.css';

export interface LayerDescriptor {
  id: string;
  name: string;
  displayName: string;
  type: 'fill' | 'line' | 'circle';
  source: 'inp' | 'simulation';
  version?: number;
  versionId?: string;
  data: any;
}
export default function LayerControl({
  layers,
  visibility,
  onVisibilityChange,
  onOrderChange,
}: {
  layers: LayerDescriptor[];
  visibility: Record<string, boolean>;
  onVisibilityChange: (id: string, value: boolean) => void;
  onOrderChange: (change: {
    draggedId: string;
    targetId: string;
    position: 'before' | 'after';
  }) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [dragged, setDragged] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [position, setPosition] = useState<'before' | 'after' | null>(null);
  const reset = () => {
    setDragged(null);
    setOver(null);
    setPosition(null);
  };
  const dragOver = (id: string, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!dragged || dragged === id) return reset();
    const bounds = event.currentTarget.getBoundingClientRect();
    setOver(id);
    setPosition(event.clientY < bounds.top + bounds.height / 2 ? 'before' : 'after');
  };
  const moveByKeyboard = (id: string, offset: number, event: KeyboardEvent<HTMLSpanElement>) => {
    event.preventDefault();
    const target = layers[layers.findIndex((layer) => layer.id === id) + offset];
    if (target)
      onOrderChange({
        draggedId: id,
        targetId: target.id,
        position: offset < 0 ? 'before' : 'after',
      });
  };
  return (
    <section className="layer-control" aria-label="工程图层">
      <button
        className="layer-top"
        type="button"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span>图层管理</span>
        <i aria-hidden="true">{collapsed ? '+' : '−'}</i>
      </button>
      {!collapsed && (
        <div className="layer-list">
          {layers.map((layer) => (
            <div
              key={layer.id}
              className={`layer-item${dragged === layer.id ? ' dragging' : ''}${over === layer.id && position === 'before' ? ' drop-before' : ''}${over === layer.id && position === 'after' ? ' drop-after' : ''}`}
              onDragOver={(event) => dragOver(layer.id, event)}
              onDrop={() => {
                if (dragged && over === layer.id && position)
                  onOrderChange({ draggedId: dragged, targetId: layer.id, position });
                reset();
              }}
            >
              <span
                className="drag-handle"
                draggable
                tabIndex={0}
                role="button"
                aria-label={`拖动${layer.displayName}调整压盖顺序`}
                title="拖动调整图层压盖顺序"
                onDragStart={(event) => {
                  setDragged(layer.id);
                  event.dataTransfer.effectAllowed = 'move';
                  event.dataTransfer.setData('text/plain', layer.id);
                }}
                onDragEnd={reset}
                onKeyDown={(event) =>
                  event.key === 'ArrowUp'
                    ? moveByKeyboard(layer.id, -1, event)
                    : event.key === 'ArrowDown'
                      ? moveByKeyboard(layer.id, 1, event)
                      : undefined
                }
              >
                ⠿
              </span>
              <input
                type="checkbox"
                checked={visibility[layer.id] ?? true}
                aria-label={`${layer.displayName}可见性`}
                onChange={(event) => onVisibilityChange(layer.id, event.target.checked)}
              />
              <span className="layer-swatch" data-geometry={layer.type} />
              <span className="layer-name">
                {layer.displayName}
              </span>
              <small>
                {layer.source === 'inp' ? 'INP' : `V${layer.version ?? '—'}·RUN`}
              </small>
            </div>
          ))}
          {layers.length === 0 && (
            <div className="no-layers">
              <span>⌁</span>
              <strong>地图中还没有工程图层</strong>
              <p>
                正在加载内置研究区图层，或尚未完成一次模型运行。
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
