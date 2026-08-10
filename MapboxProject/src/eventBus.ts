type EventCallback = (payload: any) => void

class EventBus {
  private events: Record<string, EventCallback[]> = {}

  on(eventName: string, callback: EventCallback) {
    if (!this.events[eventName]) this.events[eventName] = []
    this.events[eventName].push(callback)
  }

  emit(eventName: string, data: any) {
    this.events[eventName]?.forEach((callback) => callback(data))
  }

  off(eventName: string, callback: EventCallback) {
    if (this.events[eventName]) {
      this.events[eventName] = this.events[eventName].filter((item) => item !== callback)
    }
  }

  offAll(eventName: string) {
    delete this.events[eventName]
  }
}

export default new EventBus()
