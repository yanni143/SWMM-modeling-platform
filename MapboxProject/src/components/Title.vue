<template>
  <header class="title-container">
    <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
    <div>
      <p>FENHU / HYDRAULIC OPERATIONS</p>
      <h1>SWMM 工程运行与分析平台</h1>
    </div>
  </header>
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
  display: flex;
  align-items: center;
  gap: 13px;
  box-sizing: border-box;
  height: 56px;
  background: #102a37;
  z-index: 5;
  text-align: left;
  padding: 8px 20px;
  box-shadow: 0 1px 0 rgba(104, 196, 206, 0.45);
  font-family: Bahnschrift, 'Segoe UI', sans-serif;
}

.title-container h1 {
  color: rgb(255, 255, 255);
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.title-container p {
  margin: 0 0 2px;
  color: #68c4ce;
  font: 9px/1 Consolas, monospace;
  letter-spacing: 0.15em;
}

.brand-mark { display: flex; align-items: end; gap: 3px; height: 29px; }
.brand-mark span { width: 4px; background: #68c4ce; }
.brand-mark span:nth-child(1) { height: 11px; }
.brand-mark span:nth-child(2) { height: 27px; }
.brand-mark span:nth-child(3) { height: 18px; }
</style>
