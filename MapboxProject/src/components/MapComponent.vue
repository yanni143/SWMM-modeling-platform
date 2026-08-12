<template>
  <div class="sidebar-container">
    <SidebarPanel
      :layers="layers"
      :layer-visibility="layerVisibility"
      :timeline-steps="timelineSteps"
      :active-time-index="activeTimeIndex"
      :max-depths="maxDepths"
      :timeline-playing="timelinePlaying"
      :timeline-loading="timelineLoading"
      @layer-visibility-change="toggleLayerVisibility"
      @layer-order-change="reorderLayer"
      @time-change="selectTimeStep"
      @toggle-playback="toggleTimelinePlayback"
    />
    <div id="map" class="map-container"></div>
  </div>
</template>

<script>
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import '@/assets/css/MapComponent.css'
import { getDepthPaint, getPaint } from '@/assets/js/mapModule'
import {
  fetchDepthStep,
  fetchDepthTimeline,
  fetchLatestVersionResultLayers,
  fetchProjectLayers,
} from '@/api/models'
import eventBus from '@/eventBus'
import SidebarPanel from './SidebarPanel.vue'
import FeaturePopupTool from '@/utils/showFeaturePopup'
import { useModelStore } from '@/stores/modelStore'
import { loadWorkspaceState, saveWorkspaceState } from '@/utils/workspaceState'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''
export default {
  name: 'MapComponent',
  components: { SidebarPanel },
  setup() {
    return {
      engineeringStore: useModelStore(),
    }
  },
  data: () => ({
    layers: [],
    layerVisibility: {},
    mapInstance: null,
    popup: null,
    featurePopupTool: null,
    loadedLayers: new Set(),
    modelRunCompletedListener: null,
    workspaceResetListener: null,
    stopVersionWatch: null,
    stopResultVersionWatch: null,
    timelineSteps: [],
    activeTimeIndex: 0,
    maxDepths: {},
    timelinePlaying: false,
    timelineLoading: false,
    timelineTimer: null,
    timelineRequestController: null,
  }),
  mounted() {
    this.mapInstance = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v12?language=zh-Hans',
      center: [120.85, 31.0365],
      zoom: 11,
    })
    this.popup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, maxWidth: '500px' })
    this.featurePopupTool = new FeaturePopupTool(
      this.mapInstance,
      this.popup,
      this.engineeringStore,
    )

    this.mapInstance.on('load', () => {
      if (this.engineeringStore.selectedVersionId) {
        this.loadInpLayers(this.engineeringStore.selectedVersionId)
      }
      if (this.engineeringStore.activeResultVersionId) {
        this.loadResultLayers(this.engineeringStore.activeResultVersionId)
      }
    })
    this.mapInstance.on('click', this.handleMapClick)
    this.mapInstance.on('mousemove', this.handleMouseMove)

    this.stopVersionWatch = this.$watch(
      () => this.engineeringStore.selectedVersionId,
      (versionId) => versionId && this.loadInpLayers(versionId),
    )
    this.stopResultVersionWatch = this.$watch(
      () => this.engineeringStore.activeResultVersionId,
      (versionId) => {
        if (versionId) {
          if (!this.engineeringStore.running) this.loadResultLayers(versionId)
        } else {
          this.resetTimeline()
          this.removeLayersBySource('simulation')
        }
      },
    )
    this.modelRunCompletedListener = (data) => this.handleModelRunCompleted(data)
    this.workspaceResetListener = () => this.handleWorkspaceReset()
    eventBus.on('modelRunCompleted', this.modelRunCompletedListener)
    eventBus.on('workspaceReset', this.workspaceResetListener)
  },
  methods: {
    async loadInpLayers(versionId) {
      if (!this.mapInstance?.loaded()) return
      this.removeLayersBySource('inp')
      try {
        const incoming = await fetchProjectLayers(versionId)
        incoming.forEach((layer) => {
          this.registerLayer({
            id: layer.id,
            name: layer.name,
            displayName: layer.name,
            type: layer.geometry_type,
            source: 'inp',
            data: layer.geojson,
          })
        })
        this.restoreLayerPresentation()
        this.fitToProjectLayers(incoming)
      } catch (error) {
        console.error('INP 空间图层加载失败：', error)
      }
    },

    async loadResultLayers(versionId) {
      if (!this.mapInstance?.loaded()) return
      try {
        const result = await fetchLatestVersionResultLayers(versionId)
        this.removeLayersBySource('simulation')
        result.layers.forEach((layer) =>
          this.registerLayer({
            id: layer.id,
            name: layer.name,
            displayName: layer.name,
            type: layer.geometry_type,
            source: 'simulation',
            version: result.version,
            versionId: result.version_id,
            data: layer.geojson,
          }),
        )
        this.restoreLayerPresentation()
        await this.loadTimeline(versionId)
      } catch (error) {
        console.error('历史模拟结果图层加载失败：', error)
      }
    },

    async handleModelRunCompleted({
      run_id: runId,
      status,
      layers,
      version,
      model_version_id: versionId,
    }) {
      if (status !== 'success' || !runId) return
      this.removeLayersBySource('simulation')
      layers.forEach((layer) =>
        this.registerLayer({
          id: layer.id,
          name: layer.name,
          displayName: layer.name,
          type: layer.geometry_type,
          source: 'simulation',
          version,
          versionId,
          data: layer.geojson,
        }),
      )
      this.restoreLayerPresentation()
      await this.loadTimeline(versionId)
    },

    async loadTimeline(versionId) {
      this.resetTimeline()
      try {
        const timeline = await fetchDepthTimeline(versionId)
        if (versionId !== this.engineeringStore.activeResultVersionId) return
        this.timelineSteps = timeline.steps
        this.maxDepths = timeline.max_depths
        const lastStep = timeline.steps[timeline.steps.length - 1]
        if (lastStep) {
          this.activeTimeIndex = lastStep.time_index
          this.applyDepthPaints()
        }
      } catch (error) {
        console.error('模拟时间轴加载失败：', error)
      }
    },

    async selectTimeStep(timeIndex) {
      const versionId = this.engineeringStore.activeResultVersionId
      if (!versionId || (timeIndex === this.activeTimeIndex && !this.timelineLoading)) return
      this.timelineRequestController?.abort()
      const controller = new AbortController()
      this.timelineRequestController = controller
      this.timelineLoading = true
      try {
        const result = await fetchDepthStep(versionId, timeIndex, controller.signal)
        if (controller.signal.aborted || versionId !== this.engineeringStore.activeResultVersionId)
          return
        result.layers.forEach((incoming) => {
          const source = this.mapInstance?.getSource(`${incoming.id}-source`)
          if (source) source.setData(incoming.geojson)
          const descriptor = this.layers.find((layer) => layer.id === incoming.id)
          if (descriptor) descriptor.data = incoming.geojson
        })
        this.activeTimeIndex = timeIndex
        this.featurePopupTool?.closePopup()
      } catch (error) {
        if (error?.name !== 'AbortError') console.error('模拟时间步加载失败：', error)
      } finally {
        if (this.timelineRequestController === controller) {
          this.timelineLoading = false
          this.timelineRequestController = null
        }
      }
    },

    toggleTimelinePlayback() {
      if (this.timelinePlaying) return this.stopTimelinePlayback()
      if (this.timelineSteps.length < 2) return
      const currentPosition = this.timelineSteps.findIndex(
        (step) => step.time_index === this.activeTimeIndex,
      )
      if (currentPosition === this.timelineSteps.length - 1) {
        this.selectTimeStep(this.timelineSteps[0].time_index)
      }
      this.timelinePlaying = true
      this.timelineTimer = window.setInterval(() => this.advanceTimeline(), 900)
    },

    async advanceTimeline() {
      if (this.timelineLoading) return
      const currentPosition = this.timelineSteps.findIndex(
        (step) => step.time_index === this.activeTimeIndex,
      )
      const nextStep = this.timelineSteps[currentPosition + 1]
      if (!nextStep) return this.stopTimelinePlayback()
      await this.selectTimeStep(nextStep.time_index)
    },

    stopTimelinePlayback() {
      if (this.timelineTimer) window.clearInterval(this.timelineTimer)
      this.timelineTimer = null
      this.timelinePlaying = false
    },

    resetTimeline() {
      this.stopTimelinePlayback()
      this.timelineRequestController?.abort()
      this.timelineRequestController = null
      this.timelineLoading = false
      this.timelineSteps = []
      this.activeTimeIndex = 0
      this.maxDepths = {}
    },

    applyDepthPaints() {
      ;[
        ['result-nodes', 'circle'],
        ['result-conduits', 'line'],
      ].forEach(([layerId, type]) => {
        const mapLayerId = `${layerId}-layer`
        if (!this.mapInstance?.getLayer(mapLayerId)) return
        const paints = getDepthPaint(type, this.maxDepths[layerId])
        Object.entries(paints).forEach(([property, value]) => {
          this.mapInstance.setPaintProperty(mapLayerId, property, value)
        })
      })
    },

    registerLayer(layer) {
      const current = this.layers.findIndex((item) => item.id === layer.id)
      if (current >= 0) this.layers.splice(current, 1, layer)
      else this.layers.unshift(layer)
      const savedVisibility = loadWorkspaceState().layerVisibility?.[layer.id]
      this.layerVisibility[layer.id] = savedVisibility ?? true
      this.addLayerToMap(layer)
    },

    addLayerToMap(layer) {
      const sourceId = `${layer.id}-source`
      const layerId = `${layer.id}-layer`
      const source = this.mapInstance.getSource(sourceId)
      if (source) source.setData(layer.data)
      else this.mapInstance.addSource(sourceId, { type: 'geojson', data: layer.data })

      if (!this.mapInstance.getLayer(layerId)) {
        this.mapInstance.addLayer({
          id: layerId,
          type: layer.type,
          source: sourceId,
          paint: getPaint(layer.type, layer.source),
          layout: { visibility: this.layerVisibility[layer.id] ? 'visible' : 'none' },
        })
      } else {
        this.mapInstance.setLayoutProperty(
          layerId,
          'visibility',
          this.layerVisibility[layer.id] ? 'visible' : 'none',
        )
      }
      this.loadedLayers.add(layer.id)
    },

    reorderLayer({ draggedId, targetId, position }) {
      if (draggedId === targetId) return
      const sourceIndex = this.layers.findIndex((layer) => layer.id === draggedId)
      if (sourceIndex < 0) return

      const [movedLayer] = this.layers.splice(sourceIndex, 1)
      let targetIndex = this.layers.findIndex((layer) => layer.id === targetId)
      if (targetIndex < 0) {
        this.layers.splice(sourceIndex, 0, movedLayer)
        return
      }
      if (position === 'after') targetIndex += 1
      this.layers.splice(targetIndex, 0, movedLayer)
      this.syncMapLayerOrder()
      saveWorkspaceState({ layerOrder: this.layers.map((layer) => layer.id) })
    },

    syncMapLayerOrder() {
      if (!this.mapInstance?.loaded()) return
      // The panel is top-first; Mapbox's style stack is bottom-first.
      this.layers
        .slice()
        .reverse()
        .forEach((layer) => {
          const mapLayerId = `${layer.id}-layer`
          if (this.mapInstance.getLayer(mapLayerId)) this.mapInstance.moveLayer(mapLayerId)
        })
    },

    restoreLayerPresentation() {
      const state = loadWorkspaceState()
      const savedOrder = state.layerOrder || []
      const defaultOrder = [
        'result-nodes',
        'result-conduits',
        'result-subcatchments',
        'inp-nodes',
        'inp-conduits',
        'inp-subcatchments',
      ]
      const newResultLayers = defaultOrder.filter(
        (id) => id.startsWith('result-') && !savedOrder.includes(id),
      )
      const order = [...newResultLayers, ...savedOrder]
      const positions = new Map(order.map((id, index) => [id, index]))
      this.layers.sort((left, right) => {
        const leftPosition = positions.get(left.id)
        const rightPosition = positions.get(right.id)
        if (leftPosition === undefined && rightPosition === undefined) return 0
        if (leftPosition === undefined) return 1
        if (rightPosition === undefined) return -1
        return leftPosition - rightPosition
      })
      this.layers.forEach((layer) => {
        const visible = state.layerVisibility?.[layer.id]
        if (visible !== undefined) this.toggleLayerVisibility(layer.id, visible, false)
      })
      this.syncMapLayerOrder()
    },

    async handleWorkspaceReset() {
      this.featurePopupTool?.closePopup()
      this.resetTimeline()
      this.removeLayersBySource('simulation')
      Object.keys(this.layerVisibility).forEach((layerId) => {
        this.toggleLayerVisibility(layerId, true, false)
      })
      const defaultOrder = ['inp-nodes', 'inp-conduits', 'inp-subcatchments']
      this.layers.sort(
        (left, right) => defaultOrder.indexOf(left.id) - defaultOrder.indexOf(right.id),
      )
      this.syncMapLayerOrder()
      if (this.engineeringStore.selectedVersionId) {
        await this.loadInpLayers(this.engineeringStore.selectedVersionId)
      }
    },

    removeLayersBySource(source) {
      this.layers
        .filter((layer) => layer.source === source)
        .forEach((layer) => {
          const layerId = `${layer.id}-layer`
          const sourceId = `${layer.id}-source`
          if (this.mapInstance?.getLayer(layerId)) this.mapInstance.removeLayer(layerId)
          if (this.mapInstance?.getSource(sourceId)) this.mapInstance.removeSource(sourceId)
          this.loadedLayers.delete(layer.id)
          delete this.layerVisibility[layer.id]
        })
      this.layers = this.layers.filter((layer) => layer.source !== source)
    },

    fitToProjectLayers(incoming) {
      const points = []
      incoming.forEach((layer) =>
        layer.geojson.features.forEach((feature) => {
          const collect = (coordinates) => {
            if (typeof coordinates?.[0] === 'number') points.push(coordinates)
            else coordinates?.forEach(collect)
          }
          collect(feature.geometry?.coordinates)
        }),
      )
      const geographic = points.filter(([x, y]) => x >= -180 && x <= 180 && y >= -90 && y <= 90)
      if (geographic.length !== points.length || geographic.length === 0) return
      const bounds = geographic.reduce(
        (box, point) => box.extend(point),
        new mapboxgl.LngLatBounds(geographic[0], geographic[0]),
      )
      this.mapInstance.fitBounds(bounds, { padding: 80, maxZoom: 16, duration: 600 })
    },

    getQueryableLayers() {
      return [...this.loadedLayers]
        .map((id) => `${id}-layer`)
        .filter((id) => this.mapInstance?.getLayer(id))
    },

    handleMapClick(event) {
      const queryLayers = this.getQueryableLayers()
      if (!queryLayers.length) return
      const feature = this.mapInstance.queryRenderedFeatures(event.point, {
        layers: queryLayers,
      })[0]
      if (!feature) return this.featurePopupTool?.closePopup()
      const descriptorId = feature.layer.id.replace(/-layer$/, '')
      const descriptor = this.layers.find((layer) => layer.id === descriptorId)
      if (descriptor) {
        this.featurePopupTool.showFeaturePopup(feature, event.lngLat, descriptor)
        if (descriptor.source === 'inp' && feature.properties?.name) {
          eventBus.emit('mapFeatureSelected', {
            layerId: descriptor.id,
            target: feature.properties.name,
          })
        }
      }
    },

    handleMouseMove(event) {
      const layers = this.getQueryableLayers()
      const features = layers.length
        ? this.mapInstance.queryRenderedFeatures(event.point, { layers })
        : []
      this.mapInstance.getCanvas().style.cursor = features.length ? 'pointer' : ''
    },

    toggleLayerVisibility(layerId, visible, persist = true) {
      this.layerVisibility[layerId] = visible
      const mapLayerId = `${layerId}-layer`
      if (this.mapInstance?.getLayer(mapLayerId)) {
        this.mapInstance.setLayoutProperty(mapLayerId, 'visibility', visible ? 'visible' : 'none')
      }
      if (persist) {
        saveWorkspaceState({ layerVisibility: { ...this.layerVisibility } })
      }
    },
  },
  beforeUnmount() {
    this.resetTimeline()
    if (this.modelRunCompletedListener)
      eventBus.off('modelRunCompleted', this.modelRunCompletedListener)
    if (this.workspaceResetListener) eventBus.off('workspaceReset', this.workspaceResetListener)
    this.stopVersionWatch?.()
    this.stopResultVersionWatch?.()
    this.mapInstance?.remove()
  },
}
</script>
