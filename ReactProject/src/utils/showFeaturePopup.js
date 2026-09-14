// @ts-nocheck
import { fetchLatestVersionTimeSeries } from '@/api/models'

export default class FeaturePopupTool {
  constructor(mapInstance, popup, modelStore = null) {
    this.mapInstance = mapInstance
    this.popup = popup
    this.modelStore = modelStore
  }

  /**
   * 显示要素弹窗
   */
  showFeaturePopup(feature, lngLat, layer) {
    const layerName = layer.name
    if (layer.source === 'simulation') {
      // 地图只保留最后一个时间步，完整时序由结果查询接口加载。
      this.showTimeSeriesPopup(feature, lngLat, layer)
      return
    }

    // 显示普通属性弹窗
    this.showStandardPopup(feature, lngLat, layerName)
  }

  /**
   * 显示普通属性弹窗
   */
  showStandardPopup(feature, lngLat, layerName) {
    const properties = feature.properties
    const displayProperties = {
      name: 'Name',
      Name: 'Name',
      height: 'Height',
      width: 'Width',
      Depth: 'Depth',
      Area: 'Area',
      area: 'Area',
      manning: 'Manning coefficient',
      InvertEL: 'Invert elevation',
      MaxDepth: 'Max depth',
      InitDepth: 'Initial depth',
      InletNode: 'Upstream node',
      OutletNode: 'Downstream node',
      Roughness: 'Roughness',
      Type: 'Type',
      GJ: 'Diameter',
      imperv: 'Imperviousness',
      Imperv_Per: 'Imperviousness',
      Slope: 'Slope',
      landuse: 'Land use',
    }

    let popupContent = `<div><h4 style="margin: 0 0 8px 0; font-size: 16px; color: #333;">${this.getLayerDisplayName(layerName)}</h4>`

    Object.keys(displayProperties).forEach((key) => {
      if (properties[key]) {
        popupContent += `<div style="margin-bottom: 4px; font-size: 14px;">
          <span style="font-weight: bold; color: #666;">${displayProperties[key]}:</span>
          <span style="color: #333; margin-left: 8px;">${properties[key]}</span>
        </div>`
      }
    })

    popupContent += `</div>`

    if (this.popup) {
      this.popup.remove()
    }

    this.popup.setLngLat(lngLat).setHTML(popupContent).addTo(this.mapInstance)
  }

  /**
   * 显示时序数据弹窗
   */
  showTimeSeriesPopup(feature, lngLat, layer) {
    const latestStepData = [feature]
    // 生成包含图表的弹窗内容
    const popupContent = this.createTimeSeriesChart(feature, layer, latestStepData)

    if (this.popup) {
      this.popup.remove()
    }

    // 使用 setDOMContent 以支持更复杂的 HTML 结构
    const popupElement = document.createElement('div')
    popupElement.innerHTML = popupContent
    this.popup.setLngLat(lngLat).setDOMContent(popupElement).addTo(this.mapInstance)

    // 等待 DOM 就绪后，从专用接口加载完整时序并渲染图表。
    setTimeout(async () => {
      const versionId = layer.versionId || this.modelStore?.activeResultVersionId
      const timeSeriesData = versionId
        ? await this.fetchTimeSeriesDataByVersion(feature, layer, versionId)
        : latestStepData

      if (timeSeriesData?.length) {
        this.renderTimeSeriesChart(feature, layer, timeSeriesData)
        return
      }

      const chartContainer = document.getElementById('time-series-chart')
      if (chartContainer) {
        chartContainer.innerHTML =
          '<div style="color: #f56565; text-align: center;">Failed to load data</div>'
      }
    }, 0)
  }

  /**
   * 生成时序图表的 HTML 结构
   */
  createTimeSeriesChart(feature, layer, timeSeriesData) {
    const layerName = layer.name
    // 根据图层类型获取参数选项
    const paramOptions = this.getParamOptionsByLayer(layer, timeSeriesData)

    const currentVersionId = layer.versionId || this.modelStore?.activeResultVersionId
    const resultVersions = this.modelStore?.availableResults || []
    const versionOptions = resultVersions
      .map(
        (result) => `
        <option value="${result.version_id}" ${result.version_id === currentVersionId ? 'selected' : ''}>
          V${result.version}
        </option>
      `,
      )
      .join('')

    return `
      <div class="time-series-popup" style="max-width: 500px; max-height: 450px; overflow-y: auto;">
        <div style="padding: 12px;">
          <h4 style="margin: 0 0 8px 0; font-size: 16px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 8px;">
            ${this.getLayerDisplayName(layerName)} - ${feature.properties.name}
          </h4>
          
          <div style="margin: 12px 0;">
            <label style="font-size: 13px; font-weight: bold; margin-bottom: 6px; display: block;">
              结果版本：
            </label>
            <select id="result-version-selector" style="width: 100%; padding: 6px 8px; border: 1px solid #1890ff; border-radius: 4px; font-size: 13px; font-family: monospace; background: #f0f8ff; color: #1890ff; cursor: pointer;">
              ${versionOptions}
            </select>
            <div style="font-size: 11px; color: #999; margin-top: 4px;">
              共 ${resultVersions.length} 个有成功结果的版本；同版本仅显示最新结果
            </div>
          </div>
          
          <div style="margin: 16px 0;">
            <label style="font-size: 13px; font-weight: bold; margin-bottom: 6px; display: block;">
              Select parameter:
            </label>
            <select id="time-series-param" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;">
              ${paramOptions}
            </select>
          </div>
          
          <div style="margin: 16px 0;">
            <div id="time-series-chart" style="width: 100%; height: 180px; background: #f8f9fa; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #666;">
              Loading chart...
            </div>
          </div>
          
          <div style="margin-top: 12px; font-size: 12px; color: #888;">
            <span id="data-points-info">Number of data points: ${timeSeriesData.length}</span>
          </div>
        </div>
      </div>
    `
  }

  /**
   * 根据图层类型获取参数选项
   */
  getParamsByLayer(layer) {
    // 定义各图层的参数配置
    const layerParams = {
      // 节点模拟结果
      'result-nodes': [
        { value: 'depth', label: 'Depth' },
        { value: 'head', label: 'Head' },
        { value: 'lateral_i', label: 'Lateral inflow' },
        { value: 'total_i', label: 'Total inflow' },
        { value: 'flooding', label: 'Flooding' },
        { value: 'ponded_v', label: 'Ponded volume' },
      ],
      // 管段模拟结果
      'result-conduits': [
        { value: 'rate', label: 'Flow rate' },
        { value: 'depth', label: 'Depth' },
        { value: 'velocity', label: 'Velocity' },
        { value: 'volume', label: 'Volume' },
        { value: 'capacity', label: 'Capacity' },
      ],
      // 子汇水区模拟结果
      'result-subcatchments': [
        { value: 'rain', label: 'Rainfall' },
        { value: 'runoff', label: 'Runoff' },
        { value: 'infilt', label: 'Infiltration' },
        { value: 'evap', label: 'Evaporation' },
        { value: 'snow', label: 'Snow' },
        { value: 'gw_flow', label: 'Groundwater flow' },
        { value: 'soil_moist', label: 'Soil moisture' },
      ],
    }

    const legacyLayerIds = {
      管点模拟结果: 'result-nodes',
      节点模拟结果: 'result-nodes',
      管段模拟结果: 'result-conduits',
      管线模拟结果: 'result-conduits',
      子汇水区模拟结果: 'result-subcatchments',
    }
    const layerId = layer?.id || legacyLayerIds[layer?.name]
    return layerParams[layerId] || []
  }

  getAvailableParams(layer, timeSeriesData = []) {
    return this.getParamsByLayer(layer).filter((param) =>
      timeSeriesData.some((feature) => Number.isFinite(feature.properties?.[param.value])),
    )
  }

  getParamOptionsByLayer(layer, timeSeriesData = []) {
    const params = this.getParamsByLayer(layer)
    const availableParams = this.getAvailableParams(layer, timeSeriesData)
    const finalParams = availableParams.length > 0 ? availableParams : params

    return finalParams
      .map((param) => `<option value="${param.value}">${param.label}</option>`)
      .join('')
  }

  refreshParamOptions(paramSelect, layer, timeSeriesData, preferredParam = '') {
    const availableParams = this.getAvailableParams(layer, timeSeriesData)
    paramSelect.innerHTML = availableParams
      .map((param) => `<option value="${param.value}">${param.label}</option>`)
      .join('')

    const selectedParam = availableParams.some((param) => param.value === preferredParam)
      ? preferredParam
      : availableParams[0]?.value || ''
    paramSelect.value = selectedParam
    paramSelect.disabled = availableParams.length === 0
    return selectedParam
  }

  /**
   * 渲染时序图表
   */
  renderTimeSeriesChart(feature, layer, timeSeriesData) {
    const chartContainer = document.getElementById('time-series-chart')
    const paramSelect = document.getElementById('time-series-param')
    const versionSelect = document.getElementById('result-version-selector')

    if (!chartContainer || !paramSelect) return

    // 初次渲染
    let displayedTimeSeriesData = timeSeriesData
    let displayedFieldMetadata = timeSeriesData.fieldMetadata || {}
    const initialParam = this.refreshParamOptions(
      paramSelect,
      layer,
      displayedTimeSeriesData,
      paramSelect.value,
    )
    this.updateTimeSeriesChart(
      chartContainer,
      displayedTimeSeriesData,
      initialParam,
      displayedFieldMetadata,
    )
    const dataPointsInfo = document.getElementById('data-points-info')
    if (dataPointsInfo) {
      dataPointsInfo.textContent = `Number of data points: ${displayedTimeSeriesData.length}`
    }

    // 监听参数切换
    paramSelect.addEventListener('change', () => {
      this.updateTimeSeriesChart(
        chartContainer,
        displayedTimeSeriesData,
        paramSelect.value,
        displayedFieldMetadata,
      )
    })

    // 按版本查询该版本最新一次成功运行的结果
    if (versionSelect) {
      versionSelect.addEventListener('change', async () => {
        const selectedVersionId = versionSelect.value

        // 显示加载状态
        chartContainer.innerHTML =
          '<div style="color: #666; text-align: center;">Loading data...</div>'

        try {
          const newTimeSeriesData = await this.fetchTimeSeriesDataByVersion(
            feature,
            layer,
            selectedVersionId,
          )

          if (newTimeSeriesData && newTimeSeriesData.length > 0) {
            displayedTimeSeriesData = newTimeSeriesData
            displayedFieldMetadata = newTimeSeriesData.fieldMetadata || {}
            const selectedParam = this.refreshParamOptions(
              paramSelect,
              layer,
              displayedTimeSeriesData,
              paramSelect.value,
            )
            this.updateTimeSeriesChart(
              chartContainer,
              displayedTimeSeriesData,
              selectedParam,
              displayedFieldMetadata,
            )

            // 更新数据点数量信息
            const dataPointsInfo = document.getElementById('data-points-info')
            if (dataPointsInfo) {
              dataPointsInfo.textContent = `Number of data points: ${newTimeSeriesData.length}`
            }
          } else {
            chartContainer.innerHTML =
              '<div style="color: #999; text-align: center;">No data available for this simulation</div>'
          }
        } catch (error) {
          console.error('Error loading time series data:', error)
          chartContainer.innerHTML =
            '<div style="color: #f56565; text-align: center;">Failed to load data</div>'
        }
      })
    }
  }

  async fetchTimeSeriesDataByVersion(feature, layer, versionId) {
    try {
      const featureName = feature.properties.name
      const data = await fetchLatestVersionTimeSeries(versionId, layer.id, featureName)
      const features = (data.features || []).sort(
        (a, b) => a.properties.time_index - b.properties.time_index,
      )
      features.fieldMetadata = data.field_metadata || {}
      return features
    } catch (error) {
      console.error('Error fetching version time series data:', error)
      return null
    }
  }

  /**
   * 更新图表
   */
  updateTimeSeriesChart(container, timeSeriesData, param, fieldMetadata = {}) {
    // 提取数据并过滤未定义值，同时保持数据同步
    const validData = timeSeriesData
      .map((d) => ({
        time: d.properties.time_index,
        value: d.properties[param],
      }))
      .filter((item) => Number.isFinite(item.time) && Number.isFinite(item.value))

    if (validData.length === 0) {
      container.innerHTML = '<div style="color: #999; text-align: center;">No data available</div>'
      return
    }

    // 分离时间和值数组
    const times = validData.map((item) => item.time)
    const values = validData.map((item) => item.value)

    // 清空容器
    container.innerHTML = ''

    // 创建简单的 SVG 图表
    const svg = this.createSimpleChart(container, times, values, param, fieldMetadata[param]?.unit)
    container.appendChild(svg)
  }

  /**
   * 创建简单的 SVG 折线图
   */
  createSimpleChart(container, times, values, param, unit) {
    const width = container.clientWidth - 40
    const height = container.clientHeight - 40
    const padding = { top: 20, right: 20, bottom: 30, left: 50 }

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('width', '100%')
    svg.setAttribute('height', '100%')
    svg.setAttribute(
      'viewBox',
      `0 0 ${width + padding.left + padding.right} ${height + padding.top + padding.bottom}`,
    )

    // 防止除零和 NaN 问题
    const maxTime = Math.max(...times)
    const maxValue = Math.max(...values)

    // 确保最大值不为 0
    const safeMaxTime = maxTime === 0 ? 1 : maxTime
    const safeMaxValue = maxValue === 0 ? 1 : maxValue

    // 数据校验
    const xScale = (timeValue) => {
      const scaled = padding.left + (timeValue / safeMaxTime) * width
      return isNaN(scaled) ? padding.left : scaled
    }

    const yScale = (dataValue) => {
      const scaled = padding.top + height - (dataValue / safeMaxValue) * height
      return isNaN(scaled) ? padding.top + height : scaled
    }

    // 在校验后构建折线路径
    let pathData = ''
    let hasValidPoints = false

    for (let i = 0; i < times.length; i++) {
      const x = xScale(times[i])
      const y = yScale(values[i])

      // 确保坐标是有效数字
      if (!isNaN(x) && !isNaN(y)) {
        if (!hasValidPoints) {
          pathData = `M ${x} ${y}`
          hasValidPoints = true
        } else {
          pathData += ` L ${x} ${y}`
        }
      }
    }

    // 如果没有有效数据点，则显示提示
    if (!hasValidPoints) {
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      text.setAttribute('x', '50%')
      text.setAttribute('y', '50%')
      text.setAttribute('text-anchor', 'middle')
      text.setAttribute('fill', '#999')
      text.textContent = 'Unable to draw chart: invalid data'
      svg.appendChild(text)
      return svg
    }

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    path.setAttribute('d', pathData)
    path.setAttribute('fill', 'none')
    path.setAttribute('stroke', '#007cbf')
    path.setAttribute('stroke-width', '2')
    svg.appendChild(path)

    // 在校验后添加数据点
    times.forEach((time, i) => {
      const x = xScale(time)
      const y = yScale(values[i])

      if (!isNaN(x) && !isNaN(y)) {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
        circle.setAttribute('cx', x.toString())
        circle.setAttribute('cy', y.toString())
        circle.setAttribute('r', '3')
        circle.setAttribute('fill', '#007cbf')
        svg.appendChild(circle)
      }
    })

    // 添加坐标轴
    this.addChartAxes(svg, times, values, param, unit, width, height, padding)

    return svg
  }

  /**
   * 添加坐标轴
   */
  addChartAxes(svg, times, values, param, unit, width, height, padding) {
    // X 轴
    const xAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line')
    xAxis.setAttribute('x1', padding.left.toString())
    xAxis.setAttribute('y1', (padding.top + height).toString())
    xAxis.setAttribute('x2', (padding.left + width).toString())
    xAxis.setAttribute('y2', (padding.top + height).toString())
    xAxis.setAttribute('stroke', '#666')
    xAxis.setAttribute('stroke-width', '1')
    svg.appendChild(xAxis)

    // Y 轴
    const yAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line')
    yAxis.setAttribute('x1', padding.left.toString())
    yAxis.setAttribute('y1', padding.top.toString())
    yAxis.setAttribute('x2', padding.left.toString())
    yAxis.setAttribute('y2', (padding.top + height).toString())
    yAxis.setAttribute('stroke', '#666')
    yAxis.setAttribute('stroke-width', '1')
    svg.appendChild(yAxis)

    // X 轴标签
    const xLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    xLabel.setAttribute('x', (padding.left + width / 2).toString())
    xLabel.setAttribute('y', (padding.top + height + 20).toString())
    xLabel.setAttribute('text-anchor', 'middle')
    xLabel.setAttribute('font-size', '12')
    xLabel.setAttribute('fill', '#666')
    xLabel.textContent = 'Time (hours)'
    svg.appendChild(xLabel)

    // Y 轴标签
    const yLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    yLabel.setAttribute('x', (padding.left - 30).toString())
    yLabel.setAttribute('y', (padding.top + height / 2).toString())
    yLabel.setAttribute('text-anchor', 'middle')
    yLabel.setAttribute('transform', `rotate(-90 ${padding.left - 30} ${padding.top + height / 2})`)
    yLabel.setAttribute('font-size', '12')
    yLabel.setAttribute('fill', '#666')
    yLabel.textContent = this.getParamDisplayName(param, unit)
    svg.appendChild(yLabel)
  }

  /**
   * 获取带单位的参数显示名
   */
  getParamDisplayName(param, unit) {
    const paramNames = {
      depth: 'Depth',
      head: 'Head',
      lateral_i: 'Lateral inflow',
      total_i: 'Total inflow',
      flooding: 'Flooding',
      ponded_v: 'Ponded volume',
      rate: 'Flow rate',
      velocity: 'Velocity',
      volume: 'Volume',
      capacity: 'Capacity',
      rain: 'Rainfall',
      runoff: 'Runoff',
      infilt: 'Infiltration',
      evap: 'Evaporation',
      snow: 'Snow',
      gw_flow: 'Groundwater flow',
      soil_moist: 'Soil moisture',
    }
    const name = paramNames[param] || param
    return unit ? `${name} (${unit})` : name
  }

  /**
   * 获取图层显示名称
   */
  getLayerDisplayName(layerName) {
    const nameMap = {
      points: 'Points',
      土地: 'Land',
      子汇水区: 'Subcatchment',
      建筑物: 'Building',
      堤坝: 'Dam',
      湖泊: 'Lake',
      道路: 'Road',
      管段: 'Conduit',
      管点: 'Junction',
      排水口: 'Outfall',
      河流: 'River',
      子汇水区模拟结果: 'Subcatchment Results',
      管段模拟结果: 'Conduit Results',
      管点模拟结果: 'Junction Results',
      节点模拟结果: 'Node Results',
      管线模拟结果: 'Conduit Results',
    }
    return nameMap[layerName] || layerName
  }

  /**
   * 关闭弹窗
   */
  closePopup() {
    if (this.popup) {
      this.popup.remove()
    }
  }
}
