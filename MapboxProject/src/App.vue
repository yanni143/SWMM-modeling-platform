<template>
  <div id="app">
    <Title></Title>
    <MapComponent></MapComponent>
    <ModelWorkspace></ModelWorkspace>
  </div>
</template>

<script setup lang="ts">
import Title from './components/Title.vue'
import MapComponent from './components/MapComponent.vue'
import ModelWorkspace from './components/ModelWorkspace.vue'
</script>

<style scoped>
body {
  margin: 0;
  padding: 0;
}
</style>
