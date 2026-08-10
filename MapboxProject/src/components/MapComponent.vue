<template>
  <div class="sidebar-container">
    <SidebarPanel
      :layers="layers"
      :layer-visibility="layerVisibility"
      @layer-visibility-change="toggleLayerVisibility"
    />
    <div id="map" class="map-container"></div>
  </div>
</template>

<script>
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import '@/assets/css/MapComponent.css'
import { getPaint } from '@/assets/js/mapModule'
import { fetchProjectLayers } from '@/api/models'
import eventBus from '@/eventBus'
import SidebarPanel from './SidebarPanel.vue'
import FeaturePopupTool from '@/utils/showFeaturePopup'
import { useProjectStore } from '@/stores/projectStore'
import { useModelStore } from '@/stores/modelStore'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''
export default {
  name: 'MapComponent',
  components: { SidebarPanel },
  setup() {
    return {
      projectStore: useProjectStore(),
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
    stopVersionWatch: null,
    stopProjectWatch: null,
  }),
  mounted() {
    this.mapInstance = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v12?language=zh-Hans',
      center: [120.85, 31.0365],
      zoom: 11,
    })
    this.popup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, maxWidth: '500px' })
    this.featurePopupTool = new FeaturePopupTool(this.mapInstance, this.popup, this.projectStore)

    this.mapInstance.on('load', () => {
      if (this.engineeringStore.selectedVersionId) {
        this.loadInpLayers(this.engineeringStore.selectedVersionId)
      }
    })
    this.mapInstance.on('click', this.handleMapClick)
    this.mapInstance.on('mousemove', this.handleMouseMove)

    this.stopVersionWatch = this.$watch(
      () => this.engineeringStore.selectedVersionId,
      (versionId) => versionId && this.loadInpLayers(versionId),
    )
    this.stopProjectWatch = this.$watch(
      () => this.engineeringStore.selectedModelId,
      (projectId) => projectId && this.projectStore.setProjectId(projectId),
      { immediate: true },
    )
    this.modelRunCompletedListener = (data) => this.handleModelRunCompleted(data)
    eventBus.on('modelRunCompleted', this.modelRunCompletedListener)
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
        this.fitToProjectLayers(incoming)
      } catch (error) {
        console.error('INP 空间图层加载失败：', error)
      }
    },

    handleModelRunCompleted({ run_id: runId, status, layers }) {
      if (status !== 'success' || !runId) return
      this.projectStore.setOutId(runId)
      this.removeLayersBySource('simulation')
      layers.forEach((layer) => this.registerLayer({
        id: layer.id,
        name: layer.name,
        displayName: layer.name,
        type: layer.geometry_type,
        source: 'simulation',
        data: layer.geojson,
      }))
    },

    registerLayer(layer) {
      const current = this.layers.findIndex((item) => item.id === layer.id)
      if (current >= 0) this.layers.splice(current, 1, layer)
      else this.layers.push(layer)
      this.layerVisibility[layer.id] = true
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
          layout: { visibility: 'visible' },
        })
      }
      this.loadedLayers.add(layer.id)
    },

    removeLayersBySource(source) {
      this.layers.filter((layer) => layer.source === source).forEach((layer) => {
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
      incoming.forEach((layer) => layer.geojson.features.forEach((feature) => {
        const collect = (coordinates) => {
          if (typeof coordinates?.[0] === 'number') points.push(coordinates)
          else coordinates?.forEach(collect)
        }
        collect(feature.geometry?.coordinates)
      }))
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
      const feature = this.mapInstance.queryRenderedFeatures(event.point, { layers: queryLayers })[0]
      if (!feature) return this.featurePopupTool?.closePopup()
      const descriptorId = feature.layer.id.replace(/-layer$/, '')
      const descriptor = this.layers.find((layer) => layer.id === descriptorId)
      if (descriptor) this.featurePopupTool.showFeaturePopup(feature, event.lngLat, descriptor)
    },

    handleMouseMove(event) {
      const layers = this.getQueryableLayers()
      const features = layers.length ? this.mapInstance.queryRenderedFeatures(event.point, { layers }) : []
      this.mapInstance.getCanvas().style.cursor = features.length ? 'pointer' : ''
    },

    toggleLayerVisibility(layerId, visible) {
      this.layerVisibility[layerId] = visible
      const mapLayerId = `${layerId}-layer`
      if (this.mapInstance?.getLayer(mapLayerId)) {
        this.mapInstance.setLayoutProperty(mapLayerId, 'visibility', visible ? 'visible' : 'none')
      }
    },
  },
  beforeUnmount() {
    if (this.modelRunCompletedListener) eventBus.off('modelRunCompleted', this.modelRunCompletedListener)
    this.stopVersionWatch?.()
    this.stopProjectWatch?.()
    this.mapInstance?.remove()
  },
}
</script>
