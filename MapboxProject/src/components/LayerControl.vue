<template>
  <div class="layer-control" :class="{ collapsed: isCollapsed }">
    <div class="layer-top" @click="toggleCollapse">
      <label>Layer Manage</label>
      <span class="collapse-icon">{{ isCollapsed ? '+' : '-' }}</span>
    </div>

    <div class="collapse-content" :class="{ collapsed: isCollapsed }">
      <div class="tab-buttons">
        <button :class="{ active: currentTab === 'original' }" @click="currentTab = 'original'">
          Original data
        </button>
        <button :class="{ active: currentTab === 'simulation' }" @click="currentTab = 'simulation'">
          Simulation result
        </button>
      </div>

      <div v-if="currentTab === 'original'" class="layer-list">
        <div v-for="file in originalDataFiles" :key="file.name" class="layer-item">
          <input
            type="checkbox"
            :id="file.name"
            v-model="layerVisibility[file.name]"
            @change="handleLayerChange(file.name)"
          />
          <label :for="file.name">{{ file.displayName || file.name }}</label>
        </div>
        <div v-if="originalDataFiles.length === 0" class="no-layers">No layers data</div>
      </div>

      <div v-if="currentTab === 'simulation'" class="layer-list">
        <div v-for="file in simulationResultFiles" :key="file.name" class="layer-item">
          <input
            type="checkbox"
            :id="file.name"
            v-model="layerVisibility[file.name]"
            @change="handleLayerChange(file.name)"
          />
          <label :for="file.name">{{ file.displayName || file.name }}</label>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import '@/assets/css/LayerControl.css'

export default {
  name: 'LayerControl',
  props: {
    originalDataFiles: {
      type: Array,
      required: true,
    },
    simulationResultFiles: {
      type: Array,
      required: true,
    },
    layerVisibility: {
      type: Object,
      required: true,
    }
  },
  data() {
    return {
      currentTab: 'original',
      isCollapsed: false,
    }
  },
  methods: {
    handleLayerChange(layerName) {
      this.$emit('layer-visibility-change', layerName, this.layerVisibility[layerName])
    },

    toggleCollapse() {
      this.isCollapsed = !this.isCollapsed
      this.$emit('collapse-state-change', this.isCollapsed)
    },
  },
}
</script>
