// eventBus.js
class EventBus {
  constructor() {
    this.events = {}
  }

  // 监听事件
  on(eventName, callback) {
    if (!this.events[eventName]) {
      this.events[eventName] = []
    }
    this.events[eventName].push(callback)
  }

  // 发送事件
  emit(eventName, data) {
    if (this.events[eventName]) {
      this.events[eventName].forEach((callback) => callback(data))
    }
  }

  // 移除特定事件监听
  off(eventName, callback) {
    if (this.events[eventName]) {
      this.events[eventName] = this.events[eventName].filter((cb) => cb !== callback)
    }
  }

  // 移除事件的所有监听器
  offAll(eventName) {
    if (this.events[eventName]) {
      delete this.events[eventName]
    }
  }
}

// 创建事件总线实例
const eventBus = new EventBus()

// 导出事件总线
export default eventBus
