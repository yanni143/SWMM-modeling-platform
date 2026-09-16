import { useCallback, useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import '@/assets/css/MapComponent.css';
import { getConduitDepthPaint, getNodeResultPaint, getPaint } from '@/assets/js/mapModule';
import {
  fetchLatestVersionResultLayers,
  fetchProjectLayers,
  fetchResultStep,
  fetchResultTimeline,
  type ProjectGeoJsonLayer,
  type ResultTimeline,
  type SimulationTimelineStep,
} from '@/api/models';
import FeaturePopupTool from '@/utils/showFeaturePopup';
import { loadWorkspaceState, saveWorkspaceState } from '@/utils/workspaceState';
import { useModelStore } from '@/stores/modelStore';
import SidebarPanel from './SidebarPanel';
import type { LayerDescriptor } from './LayerControl';

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || '';
type State = {
  steps: SimulationTimelineStep[];
  ranges: ResultTimeline['result_ranges'];
  metadata: ResultTimeline['result_metadata'];
};
const emptyTimeline: State = { steps: [], ranges: {}, metadata: {} };

export default function MapView() {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const popupToolRef = useRef<any>(null);
  const loadedRef = useRef(new Set<string>());
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const selectedVersionId = useModelStore((state) => state.selectedVersionId);
  const activeResultVersionId = useModelStore((state) => state.activeResultVersionId);
  const running = useModelStore((state) => state.running);
  const [layers, setLayers] = useState<LayerDescriptor[]>([]);
  const layersRef = useRef(layers);
  useEffect(() => {
    layersRef.current = layers;
  }, [layers]);
  const [visibility, setVisibility] = useState<Record<string, boolean>>({});
  const visibilityRef = useRef(visibility);
  useEffect(() => {
    visibilityRef.current = visibility;
  }, [visibility]);
  const [timeline, setTimeline] = useState<State>(emptyTimeline);
  const timelineRef = useRef(timeline);
  useEffect(() => {
    timelineRef.current = timeline;
  }, [timeline]);
  const [activeTime, setActiveTime] = useState(0);
  const activeTimeRef = useRef(activeTime);
  useEffect(() => {
    activeTimeRef.current = activeTime;
  }, [activeTime]);
  const [playing, setPlaying] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const timelineLoadingRef = useRef(timelineLoading);
  useEffect(() => {
    timelineLoadingRef.current = timelineLoading;
  }, [timelineLoading]);
  const removeBySource = useCallback((source: LayerDescriptor['source']) => {
    const map = mapRef.current;
    const removed = layersRef.current.filter((layer) => layer.source === source);
    removed.forEach((layer) => {
      const layerId = `${layer.id}-layer`;
      const sourceId = `${layer.id}-source`;
      if (map?.getLayer(layerId)) map.removeLayer(layerId);
      if (map?.getSource(sourceId)) map.removeSource(sourceId);
      loadedRef.current.delete(layer.id);
    });
    setLayers((current) => current.filter((layer) => layer.source !== source));
    setVisibility((current) => {
      const next = { ...current };
      removed.forEach((layer) => delete next[layer.id]);
      return next;
    });
  }, []);
  const syncOrder = useCallback(() => {
    const map = mapRef.current;
    if (!map?.loaded()) return;
    [...layersRef.current].reverse().forEach((layer) => {
      const id = `${layer.id}-layer`;
      if (map.getLayer(id)) map.moveLayer(id);
    });
  }, []);
  const toggleVisibility = useCallback((id: string, visible: boolean, persist = true) => {
    setVisibility((current) => {
      const next = { ...current, [id]: visible };
      if (persist) saveWorkspaceState({ layerVisibility: next });
      return next;
    });
    const mapLayer = mapRef.current?.getLayer(`${id}-layer`);
    if (mapLayer)
      mapRef.current!.setLayoutProperty(mapLayer.id, 'visibility', visible ? 'visible' : 'none');
  }, []);
  const restorePresentation = useCallback(() => {
    const saved = loadWorkspaceState();
    const defaultOrder = [
      'result-nodes',
      'result-conduits',
      'result-subcatchments',
      'inp-nodes',
      'inp-conduits',
      'inp-subcatchments',
    ];
    const newResults = defaultOrder.filter(
      (id) => id.startsWith('result-') && !(saved.layerOrder ?? []).includes(id),
    );
    const positions = new Map(
      [...newResults, ...(saved.layerOrder ?? [])].map((id, index) => [id, index]),
    );
    setLayers((current) =>
      [...current].sort((a, b) => (positions.get(a.id) ?? 999) - (positions.get(b.id) ?? 999)),
    );
    Object.entries(saved.layerVisibility ?? {}).forEach(([id, visible]) =>
      toggleVisibility(id, visible, false),
    );
    queueMicrotask(syncOrder);
  }, [syncOrder, toggleVisibility]);
  const register = useCallback((layer: LayerDescriptor) => {
    const map = mapRef.current;
    if (!map) return;
    const sourceId = `${layer.id}-source`;
    const mapLayerId = `${layer.id}-layer`;
    const saved = loadWorkspaceState().layerVisibility?.[layer.id] ?? true;
    setVisibility((current) => ({ ...current, [layer.id]: current[layer.id] ?? saved }));
    const source = map.getSource(sourceId) as mapboxgl.GeoJSONSource | undefined;
    if (source) source.setData(layer.data as never);
    else map.addSource(sourceId, { type: 'geojson', data: layer.data as never });
    if (!map.getLayer(mapLayerId))
      map.addLayer({
        id: mapLayerId,
        type: layer.type,
        source: sourceId,
        paint: getPaint(layer.type, layer.source),
        layout: { visibility: (visibilityRef.current[layer.id] ?? saved) ? 'visible' : 'none' },
      });
    loadedRef.current.add(layer.id);
    setLayers((current) => [layer, ...current.filter((item) => item.id !== layer.id)]);
  }, []);
  const fitToProject = useCallback((incoming: ProjectGeoJsonLayer[]) => {
    const points: number[][] = [];
    const collect = (coordinates: any): void => {
      if (typeof coordinates?.[0] === 'number') points.push(coordinates);
      else coordinates?.forEach(collect);
    };
    incoming.forEach((layer) =>
      layer.geojson.features.forEach((feature: any) => collect(feature.geometry?.coordinates)),
    );
    if (!points.length || points.some(([x, y]) => x < -180 || x > 180 || y < -90 || y > 90)) return;
    const bounds = points.reduce(
      (box, point) => box.extend(point as [number, number]),
      new mapboxgl.LngLatBounds(points[0] as [number, number], points[0] as [number, number]),
    );
    mapRef.current?.fitBounds(bounds, { padding: 80, maxZoom: 16, duration: 600 });
  }, []);
  const resetTimeline = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    setPlaying(false);
    setTimelineLoading(false);
    setTimeline(emptyTimeline);
    setActiveTime(0);
  }, []);
  const loadTimeline = useCallback(
    async (versionId: string) => {
      resetTimeline();
      try {
        const value = await fetchResultTimeline(versionId);
        if (useModelStore.getState().activeResultVersionId !== versionId) return;
        setTimeline({
          steps: value.steps,
          ranges: value.result_ranges,
          metadata: value.result_metadata,
        });
        const last = value.steps.at(-1);
        if (last) {
          setActiveTime(last.time_index);
          const map = mapRef.current;
          const paints: Record<string, Record<string, unknown>> = {
            'result-nodes': getNodeResultPaint(
              value.result_ranges['result-nodes']?.depth,
              value.result_ranges['result-nodes']?.flooding,
            ),
            'result-conduits': getConduitDepthPaint(value.result_ranges['result-conduits']?.depth),
          };
          Object.entries(paints).forEach(([id, paint]) =>
            Object.entries(paint).forEach(([property, setting]) => {
              if (map?.getLayer(`${id}-layer`))
                (map as any).setPaintProperty(`${id}-layer`, property, setting);
            }),
          );
        }
      } catch (error) {
        console.error('模拟时间轴加载失败：', error);
      }
    },
    [resetTimeline],
  );
  const loadInp = useCallback(
    async (versionId: string) => {
      if (!mapRef.current?.loaded()) return;
      removeBySource('inp');
      try {
        const incoming = await fetchProjectLayers(versionId);
        incoming.forEach((layer) =>
          register({
            id: layer.id,
            name: layer.name,
            displayName: layer.name,
            type: layer.geometry_type,
            source: 'inp',
            data: layer.geojson as never,
          }),
        );
        restorePresentation();
        fitToProject(incoming);
      } catch (error) {
        console.error('INP 空间图层加载失败：', error);
      }
    },
    [fitToProject, register, removeBySource, restorePresentation],
  );
  const loadResults = useCallback(
    async (versionId: string) => {
      if (!mapRef.current?.loaded()) return;
      try {
        const result = await fetchLatestVersionResultLayers(versionId);
        removeBySource('simulation');
        result.layers.forEach((layer) =>
          register({
            id: layer.id,
            name: layer.name,
            displayName: layer.name,
            type: layer.geometry_type,
            source: 'simulation',
            version: result.version,
            versionId: result.version_id,
            data: layer.geojson as never,
          }),
        );
        restorePresentation();
        await loadTimeline(versionId);
      } catch (error) {
        console.error('历史模拟结果图层加载失败：', error);
      }
    },
    [loadTimeline, register, removeBySource, restorePresentation],
  );
  const selectTime = useCallback(async (timeIndex: number) => {
    const versionId = useModelStore.getState().activeResultVersionId;
    if (!versionId || (timeIndex === activeTimeRef.current && !timelineLoadingRef.current)) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setTimelineLoading(true);
    try {
      const result = await fetchResultStep(versionId, timeIndex, controller.signal);
      if (controller.signal.aborted || useModelStore.getState().activeResultVersionId !== versionId)
        return;
      result.layers.forEach((incoming) => {
        const source = mapRef.current?.getSource(`${incoming.id}-source`) as
          mapboxgl.GeoJSONSource | undefined;
        source?.setData(incoming.geojson as never);
        setLayers((current) =>
          current.map((layer) =>
            layer.id === incoming.id ? { ...layer, data: incoming.geojson as never } : layer,
          ),
        );
      });
      setActiveTime(timeIndex);
      popupToolRef.current?.closePopup();
    } catch (error: any) {
      if (error?.name !== 'AbortError') console.error('模拟时间步加载失败：', error);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setTimelineLoading(false);
      }
    }
  }, []);
  const togglePlayback = useCallback(() => {
    if (playing) {
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = null;
      setPlaying(false);
      return;
    }
    if (timelineRef.current.steps.length < 2) return;
    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      const steps = timelineRef.current.steps;
      const index = steps.findIndex((step) => step.time_index === activeTimeRef.current);
      const next = steps[index + 1];
      if (next) void selectTime(next.time_index);
      else {
        if (timerRef.current) window.clearInterval(timerRef.current);
        timerRef.current = null;
        setPlaying(false);
      }
    }, 900);
  }, [playing, selectTime]);
  useEffect(() => {
    const map = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v12?language=zh-Hans',
      center: [120.85, 31.0365],
      zoom: 11,
    });
    mapRef.current = map;
    const popup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, maxWidth: '500px' });
    popupRef.current = popup;
    const facade = {
      get activeResultVersionId() {
        return useModelStore.getState().activeResultVersionId;
      },
      get availableResults() {
        return useModelStore.getState().availableResults;
      },
    };
    popupToolRef.current = new FeaturePopupTool(map, popup, facade as any);
    const click = (event: mapboxgl.MapMouseEvent) => {
      const query = [...loadedRef.current]
        .map((id) => `${id}-layer`)
        .filter((id) => map.getLayer(id));
      const feature = query.length
        ? (map.queryRenderedFeatures(event.point, { layers: query })[0] as any)
        : undefined;
      if (!feature) return popupToolRef.current?.closePopup();
      const descriptor = layersRef.current.find(
        (layer) => layer.id === feature.layer.id.replace(/-layer$/, ''),
      );
      if (!descriptor) return;
      popupToolRef.current.showFeaturePopup(feature, event.lngLat, descriptor);
      if (descriptor.source === 'inp' && feature.properties?.name)
        window.dispatchEvent(
          new CustomEvent('swmm:map-feature-selected', {
            detail: { layerId: descriptor.id, target: feature.properties.name },
          }),
        );
    };
    const mousemove = (event: mapboxgl.MapMouseEvent) => {
      const query = [...loadedRef.current]
        .map((id) => `${id}-layer`)
        .filter((id) => map.getLayer(id));
      map.getCanvas().style.cursor =
        query.length && map.queryRenderedFeatures(event.point, { layers: query }).length
          ? 'pointer'
          : '';
    };
    map.on('click', click);
    map.on('mousemove', mousemove);
    map.on('load', () => {
      const state = useModelStore.getState();
      if (state.selectedVersionId) void loadInp(state.selectedVersionId);
      if (state.activeResultVersionId) void loadResults(state.activeResultVersionId);
    });
    return () => {
      resetTimeline();
      map.off('click', click);
      map.off('mousemove', mousemove);
      map.remove();
      mapRef.current = null;
    };
  }, [loadInp, loadResults, resetTimeline]);
  useEffect(() => {
    if (selectedVersionId) void loadInp(selectedVersionId);
  }, [loadInp, selectedVersionId]);
  useEffect(() => {
    if (activeResultVersionId && !running) void loadResults(activeResultVersionId);
    if (!activeResultVersionId) {
      resetTimeline();
      removeBySource('simulation');
    }
  }, [activeResultVersionId, loadResults, removeBySource, resetTimeline, running]);
  useEffect(() => {
    const done = (event: Event) => {
      const result = (event as CustomEvent).detail;
      if (result?.status === 'success') void loadResults(result.model_version_id);
    };
    const reset = () => {
      popupToolRef.current?.closePopup();
      resetTimeline();
      removeBySource('simulation');
      Object.keys(visibilityRef.current).forEach((id) => toggleVisibility(id, true, false));
    };
    window.addEventListener('swmm:run-completed', done);
    window.addEventListener('swmm:workspace-reset', reset);
    return () => {
      window.removeEventListener('swmm:run-completed', done);
      window.removeEventListener('swmm:workspace-reset', reset);
    };
  }, [loadResults, removeBySource, resetTimeline, toggleVisibility]);
  return (
    <div className="sidebar-container">
      <SidebarPanel
        layers={layers}
        visibility={visibility}
        steps={timeline.steps}
        activeTimeIndex={activeTime}
        ranges={timeline.ranges}
        metadata={timeline.metadata}
        playing={playing}
        loading={timelineLoading}
        onVisibilityChange={toggleVisibility}
        onOrderChange={({ draggedId, targetId, position }) => {
          setLayers((current) => {
            const from = current.findIndex((item) => item.id === draggedId);
            const next = [...current];
            const [moved] = next.splice(from, 1);
            let to = next.findIndex((item) => item.id === targetId);
            next.splice(position === 'after' ? to + 1 : to, 0, moved);
            saveWorkspaceState({ layerOrder: next.map((item) => item.id) });
            return next;
          });
          queueMicrotask(syncOrder);
        }}
        onTimeChange={selectTime}
        onToggle={togglePlayback}
      />
      <div id="map" className="map-container" />
    </div>
  );
}
