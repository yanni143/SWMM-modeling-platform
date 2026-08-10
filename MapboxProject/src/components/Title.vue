<template>
  <div class="title-container">
    <h1>SWMM Modeling and Simulation System</h1>
  </div>
</template>

<script>
export default {
  name: 'Title',
}
</script>

<style scoped>
.title-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  background-color: rgb(57, 126, 190);
  z-index: 5;
  text-align: left;
  padding: 10px 0;
}

.title-container h1 {
  color: rgb(255, 255, 255);
  margin: 0;
  margin-left: 20px;
  font-size: 26px;
}
</style>
