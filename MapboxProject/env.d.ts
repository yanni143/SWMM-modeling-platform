/// <reference types="vite/client" />

// src/env.d.ts
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // 声明 Vue 组件的类型
  const component: DefineComponent<{}, {}, any>
  export default component
}
