<template>
  <div class="sidebar-container">
    <SidebarPanel
      :original-data-files="originalDataFiles"
      :simulation-result-files="simulationResultFiles"
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
import { originalDataFiles, simulationResultFiles, getPaint } from '@/assets/js/mapModule'
import eventBus from '@/eventBus.js'
import SidebarPanel from './SidebarPanel.vue'
import FeaturePopupTool from '@/utils/showFeaturePopup'
import { useProjectStore } from '@/stores/projectStore'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

export default {
  name: 'MapComponent',
  components: { SidebarPanel },
  setup() {
    return { projectStore: useProjectStore() }
  },
  data() {
    const visibility = {}
    originalDataFiles.forEach((file) => {
      visibility[file.name] = true
    })
    simulationResultFiles.forEach((file) => {
      visibility[file.name] = false
    })

    return {
      layerVisibility: visibility,
      mapInstance: null,
      originalDataFiles,
      simulationResultFiles,
      popup: null,
      featurePopupTool: null,
      loadedLayers: new Set(),
      modelRunCompletedListener: null,
    }
  },
  mounted() {
    const map = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v12?language=en',
      center: [120.85, 31.0365],
      zoom: 15,
    })

    this.mapInstance = map
    this.popup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, maxWidth: '500px' })
    this.featurePopupTool = new FeaturePopupTool(
      map,
      this.popup,
      this.simulationResultFiles,
      this.projectStore,
    )

    map.on('load', async () => {
      this.applyEnglishBasemapLabels()
      await this.loadPredefinedLayers()
    })
    map.on('click', this.handleMapClick)
    map.on('mousemove', this.handleMouseMove)

    this.modelRunCompletedListener = (data) => this.handleModelRunCompleted(data)
    eventBus.on('modelRunCompleted', this.modelRunCompletedListener)
  },
  methods: {
    applyEnglishBasemapLabels() {
      const layers = this.mapInstance?.getStyle()?.layers || []
      layers.forEach((layer) => {
        if (layer.type === 'symbol' && layer.layout?.['text-field']) {
          this.mapInstance.setLayoutProperty(layer.id, 'text-field', [
            'coalesce',
            ['get', 'name_en'],
            ['get', 'name'],
          ])
        }
      })
    },

    async handleModelRunCompleted({ out_id: outId, status }) {
      if (status !== 'success' || !outId) return

      this.projectStore.setOutId(outId)
      await this.loadSimulationResults()
      this.simulationResultFiles.forEach((file) => this.toggleLayerVisibility(file.name, true))
    },

    async loadPredefinedLayers() {
      await Promise.all(
        this.originalDataFiles.map(async (file) => {
          try {
            const response = await fetch(file.path)
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            this.addLayerToMap(file.name, await response.json(), file.type)
          } catch (error) {
            console.error(`Failed to load layer ${file.name}:`, error)
          }
        }),
      )
    },

    async loadSimulationResults() {
      const projectId = this.projectStore.currentProjectId
      const outId = this.projectStore.currentOutId
      if (!projectId || !outId) {
        console.warn('Cannot load simulation results without project_id and out_id')
        return
      }

      await Promise.all(
        this.simulationResultFiles.map(async (file) => {
          const params = new URLSearchParams({
            project_id: projectId,
            out_id: outId,
            filename: file.filename,
          })
          try {
            const response = await fetch(`${apiBaseUrl}/get_simulation_result?${params}`)
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            this.addLayerToMap(file.name, await response.json(), file.type)
          } catch (error) {
            console.error(`Failed to load simulation result ${file.name}:`, error)
          }
        }),
      )
    },

    addLayerToMap(layerName, data, type) {
      const map = this.mapInstance
      if (!map) return

      const sourceId = `${layerName}-source`
      const layerId = `${layerName}-layer`
      const source = map.getSource(sourceId)

      if (source) {
        source.setData(data)
      } else {
        map.addSource(sourceId, { type: 'geojson', data })
      }

      if (!map.getLayer(layerId)) {
        map.addLayer({
          id: layerId,
          type,
          source: sourceId,
          paint: getPaint(type, layerName),
          layout: { visibility: this.layerVisibility[layerName] ? 'visible' : 'none' },
        })
      }
      this.loadedLayers.add(layerName)
    },

    getQueryableLayers() {
      if (!this.mapInstance) return []
      return [...this.loadedLayers]
        .map((name) => `${name}-layer`)
        .filter((layerId) => this.mapInstance.getLayer(layerId))
    },

    handleMapClick(event) {
      const layers = this.getQueryableLayers()
      if (layers.length === 0) return

      const features = this.mapInstance.queryRenderedFeatures(event.point, { layers })
      if (features.length === 0) {
        this.featurePopupTool?.closePopup()
        return
      }

      const feature = features[0]
      const layerName = feature.layer.id.replace(/-layer$/, '')
      this.featurePopupTool.showFeaturePopup(feature, event.lngLat, layerName)
    },

    handleMouseMove(event) {
      const layers = this.getQueryableLayers()
      const features = layers.length
        ? this.mapInstance.queryRenderedFeatures(event.point, { layers })
        : []
      this.mapInstance.getCanvas().style.cursor = features.length ? 'pointer' : ''
    },

    toggleLayerVisibility(layerName, isVisible) {
      this.layerVisibility[layerName] = isVisible
      const layerId = `${layerName}-layer`
      if (this.mapInstance?.getLayer(layerId)) {
        this.mapInstance.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none')
      }
    },
  },
  beforeUnmount() {
    if (this.modelRunCompletedListener) {
      eventBus.off('modelRunCompleted', this.modelRunCompletedListener)
    }
    this.mapInstance?.remove()
  },
}
</script>
