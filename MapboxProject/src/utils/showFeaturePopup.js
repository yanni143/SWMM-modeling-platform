export default class FeaturePopupTool {
  constructor(mapInstance, popup, simulationResultFiles, projectStore = null) {
    this.mapInstance = mapInstance
    this.popup = popup
    this.simulationResultFiles = simulationResultFiles
    this.projectStore = projectStore
  }

  /**
   * 显示要素弹窗
   */
  showFeaturePopup(feature, lngLat, layerName) {
    const properties = feature.properties

    // 检查当前是否为模拟结果图层
    const isSimulationResult = this.simulationResultFiles.some((file) => file.name === layerName)
    if (isSimulationResult) {
      // 对模拟结果图层，收集同一位置的时序数据
      const timeSeriesData = this.collectTimeSeriesData(feature, layerName)
      if (timeSeriesData && timeSeriesData.length > 1) {
        this.showTimeSeriesPopup(feature, lngLat, layerName, timeSeriesData)
        return
      }
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
   * 收集时序数据
   */
  collectTimeSeriesData(clickedFeature, layerName) {
    if (!this.mapInstance) return null

    const sourceId = `${layerName}-source`
    const source = this.mapInstance.getSource(sourceId)
    if (!source || !source._data) return null

    const clickedProperties = clickedFeature.properties
    const featureName = clickedProperties.name

    // 从数据源中取出所有同名要素
    const allFeatures = source._data.features || []
    const timeSeriesFeatures = allFeatures.filter(
      (feature) => feature.properties.name === featureName,
    )

    // 按时间排序
    return timeSeriesFeatures.sort((a, b) => a.properties.time - b.properties.time)
  }

  /**
   * 显示时序数据弹窗
   */
  showTimeSeriesPopup(feature, lngLat, layerName, timeSeriesData) {
    const properties = feature.properties

    // 生成包含图表的弹窗内容
    const popupContent = this.createTimeSeriesChart(feature, layerName, timeSeriesData)

    if (this.popup) {
      this.popup.remove()
    }

    // 使用 setDOMContent 以支持更复杂的 HTML 结构
    const popupElement = document.createElement('div')
    popupElement.innerHTML = popupContent
    this.popup.setLngLat(lngLat).setDOMContent(popupElement).addTo(this.mapInstance)

    // 等待 DOM 就绪后渲染图表
    setTimeout(() => {
      this.renderTimeSeriesChart(feature, layerName, timeSeriesData)
    }, 0)
  }

  /**
   * 生成时序图表的 HTML 结构
   */
  createTimeSeriesChart(feature, layerName, timeSeriesData) {
    // 根据图层类型获取参数选项
    const paramOptions = this.getParamOptionsByLayer(layerName, timeSeriesData[0]?.properties)

    // 从 store 中读取当前 out_id 和历史记录
    const currentOutId = this.projectStore?.currentOutId || 'N/A'
    const outIdHistory = this.projectStore?.outIdHistory || []
    
    // 生成 out_id 选项，倒序显示最新记录
    const outIdOptions = outIdHistory.length > 0
      ? [...outIdHistory].reverse().map(outId => 
          `<option value="${outId}" ${outId === currentOutId ? 'selected' : ''}>${outId}</option>`
        ).join('')
      : `<option value="${currentOutId}">${currentOutId}</option>`

    return `
      <div class="time-series-popup" style="max-width: 500px; max-height: 450px; overflow-y: auto;">
        <div style="padding: 12px;">
          <h4 style="margin: 0 0 8px 0; font-size: 16px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 8px;">
            ${this.getLayerDisplayName(layerName)} - ${feature.properties.name}
          </h4>
          
          <div style="margin: 12px 0;">
            <label style="font-size: 13px; font-weight: bold; margin-bottom: 6px; display: block;">
              Simulation ID:
            </label>
            <select id="out-id-selector" style="width: 100%; padding: 6px 8px; border: 1px solid #1890ff; border-radius: 4px; font-size: 13px; font-family: monospace; background: #f0f8ff; color: #1890ff; cursor: pointer;">
              ${outIdOptions}
            </select>
            <div style="font-size: 11px; color: #999; margin-top: 4px;">
              ${outIdHistory.length > 0 ? `Total ${outIdHistory.length} simulation(s)` : 'Current simulation'}
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
  getParamOptionsByLayer(layerName, sampleProperties = {}) {
    // 定义各图层的参数配置
    const layerParams = {
      // 节点模拟结果
      '管点模拟结果': [
        { value: 'depth', label: 'Depth' },
        { value: 'head', label: 'Head' },
        { value: 'lateral_i', label: 'Lateral inflow' },
        { value: 'total_i', label: 'Total inflow' },
        { value: 'flooding', label: 'Flooding' },
        { value: 'ponded_v', label: 'Ponded volume' },
        { value: 'pollut', label: 'Pollutant' },
      ],
      // 管段模拟结果
      '管段模拟结果': [
        { value: 'rate', label: 'Flow rate' },
        { value: 'depth', label: 'Depth' },
        { value: 'velocity', label: 'Velocity' },
        { value: 'volume', label: 'Volume' },
        { value: 'capacity', label: 'Capacity' },
        { value: 'pollut', label: 'Pollutant' },
      ],
      // 子汇水区模拟结果
      '子汇水区模拟结果': [
        { value: 'rain', label: 'Rainfall' },
        { value: 'runoff', label: 'Runoff' },
        { value: 'infilt', label: 'Infiltration' },
        { value: 'evap', label: 'Evaporation' },
        { value: 'snow', label: 'Snow' },
        { value: 'gw_flow', label: 'Groundwater flow' },
        { value: 'soil_moist', label: 'Soil moisture' },
        { value: 'pollut', label: 'Pollutant' },
      ],
    }

    // 获取当前图层对应的参数配置
    const params = layerParams[layerName] || []

    // 动态过滤：仅保留数据中实际存在的参数
    const availableParams = params.filter((param) => {
      // 检查样本数据中是否存在该参数
      return sampleProperties[param.value] !== undefined
    })

    // 如果没有可用参数，则回退到完整配置
    const finalParams = availableParams.length > 0 ? availableParams : params

    // 生成下拉选项 HTML
    return finalParams
      .map((param) => `<option value="${param.value}">${param.label}</option>`)
      .join('')
  }

  /**
   * 渲染时序图表
   */
  renderTimeSeriesChart(feature, layerName, timeSeriesData) {
    const chartContainer = document.getElementById('time-series-chart')
    const paramSelect = document.getElementById('time-series-param')
    const outIdSelect = document.getElementById('out-id-selector')

    if (!chartContainer || !paramSelect) return

    // 保存当前要素和图层信息，便于后续重新加载
    this.currentFeature = feature
    this.currentLayerName = layerName

    // 初次渲染
    this.updateTimeSeriesChart(chartContainer, timeSeriesData, paramSelect.value)

    // 监听参数切换
    paramSelect.addEventListener('change', () => {
      this.updateTimeSeriesChart(chartContainer, timeSeriesData, paramSelect.value)
    })

    // 监听 out_id 切换
    if (outIdSelect) {
      outIdSelect.addEventListener('change', async () => {
        const selectedOutId = outIdSelect.value
        console.log('Switching to out_id:', selectedOutId)
        
        // 显示加载状态
        chartContainer.innerHTML = '<div style="color: #666; text-align: center;">Loading data...</div>'
        
        try {
          // 根据选中的 out_id 拉取新的时序数据
          const newTimeSeriesData = await this.fetchTimeSeriesDataByOutId(
            feature,
            layerName,
            selectedOutId
          )
          
          if (newTimeSeriesData && newTimeSeriesData.length > 0) {
            // 用新数据更新图表
            this.updateTimeSeriesChart(chartContainer, newTimeSeriesData, paramSelect.value)
            
            // 更新数据点数量信息
            const dataPointsInfo = document.getElementById('data-points-info')
            if (dataPointsInfo) {
              dataPointsInfo.textContent = `Number of data points: ${newTimeSeriesData.length}`
            }
          } else {
            chartContainer.innerHTML = '<div style="color: #999; text-align: center;">No data available for this simulation</div>'
          }
        } catch (error) {
          console.error('Error loading time series data:', error)
          chartContainer.innerHTML = '<div style="color: #f56565; text-align: center;">Failed to load data</div>'
        }
      })
    }
  }

  /**
   * 根据指定 out_id 获取时序数据
   */
  async fetchTimeSeriesDataByOutId(feature, layerName, outId) {
    if (!this.projectStore) {
      console.error('ProjectStore is not available')
      return null
    }

    const projectId = this.projectStore.currentProjectId
    if (!projectId) {
      console.error('Project ID is not available')
      return null
    }

    // 根据图层名称确定文件名
    const filenameMap = {
      '管点模拟结果': 'out_nodes.json',
      '管段模拟结果': 'out_links.json',
      '子汇水区模拟结果': 'out_subcatchments.json',
    }

    const filename = filenameMap[layerName]
    if (!filename) {
      console.error('Unknown layer name:', layerName)
      return null
    }

    try {
      // 拼接接口地址
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
      const params = new URLSearchParams({ project_id: projectId, out_id: outId, filename })
      const apiUrl = `${apiBaseUrl}/get_simulation_result?${params}`
      console.log('Fetching data from:', apiUrl)

      const response = await fetch(apiUrl)
      if (!response.ok) {
        console.error('Failed to fetch data:', response.status)
        return null
      }

      const data = await response.json()
      
      // 过滤出与当前点击要素同名的要素
      const featureName = feature.properties.name
      const allFeatures = data.features || []
      const timeSeriesFeatures = allFeatures.filter(
        (f) => f.properties.name === featureName
      )

      // 按时间排序
      return timeSeriesFeatures.sort((a, b) => a.properties.time - b.properties.time)
    } catch (error) {
      console.error('Error fetching time series data:', error)
      return null
    }
  }

  /**
   * 更新图表
   */
  updateTimeSeriesChart(container, timeSeriesData, param) {
    // 提取数据并过滤未定义值，同时保持数据同步
    const validData = timeSeriesData
      .map((d) => ({
        time: d.properties.time,
        value: d.properties[param],
      }))
      .filter((item) => item.time !== undefined && item.value !== undefined)

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
    const svg = this.createSimpleChart(container, times, values, param)
    container.appendChild(svg)
  }

  /**
   * 创建简单的 SVG 折线图
   */
  createSimpleChart(container, times, values, param) {
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
    this.addChartAxes(svg, times, values, param, width, height, padding)

    return svg
  }

  /**
   * 添加坐标轴
   */
  addChartAxes(svg, times, values, param, width, height, padding) {
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
    yLabel.textContent = this.getParamDisplayName(param)
    svg.appendChild(yLabel)
  }

  /**
   * 获取带单位的参数显示名
   */
  getParamDisplayName(param) {
    const paramUnits = {
      // 节点参数
      depth: 'Depth (m)',
      head: 'Head (m)',
      lateral_i: 'Lateral inflow (m³/s)',
      total_i: 'Total inflow (m³/s)',
      flooding: 'Flooding (m³/s)',
      ponded_v: 'Ponded volume (m³)',

      // 管段参数
      rate: 'Flow rate (m³/s)',
      velocity: 'Velocity (m/s)',
      volume: 'Volume (m³)',
      capacity: 'Capacity (m³)',

      // 子汇水区参数
      rain: 'Rainfall (mm)',
      runoff: 'Runoff (mm)',
      infilt: 'Infiltration (mm)',
      evap: 'Evaporation (mm)',
      snow: 'Snow (mm)',
      gw_flow: 'Groundwater flow (mm)',
      soil_moist: 'Soil moisture (%)',

      // 通用参数
      pollut: 'Pollutant concentration',
    }
    return paramUnits[param] || param
  }

  /**
   * 获取图层显示名称
   */
  getLayerDisplayName(layerName) {
    const nameMap = {
      points: 'Points',
      '土地': 'Land',
      '子汇水区': 'Subcatchment',
      '建筑物': 'Building',
      '堤坝': 'Dam',
      '湖泊': 'Lake',
      '道路': 'Road',
      '管段': 'Conduit',
      '管点': 'Junction',
      '排水口': 'Outfall',
      '河流': 'River',
      '子汇水区模拟结果': 'Subcatchment Results',
      '管段模拟结果': 'Conduit Results',
      '管点模拟结果': 'Junction Results'
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
