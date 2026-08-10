const originalDataFiles = [
  { name: '土地', displayName: 'Land', path: '/json/land.json', type: 'fill' },
  { name: '子汇水区', displayName: 'Subcatchment', path: '/json/subcatchment.json', type: 'fill' },
  { name: '建筑物', displayName: 'Building', path: '/json/build.json', type: 'fill' },
  { name: '堤坝', displayName: 'Dam', path: '/json/dam.json', type: 'line' },
  { name: '湖泊', displayName: 'Lake', path: '/json/lake.json', type: 'fill' },
  { name: '道路', displayName: 'Road', path: '/json/road.json', type: 'fill' },
  { name: '管段', displayName: 'Conduit', path: '/json/pipes_conduit.json', type: 'line' },
  { name: '管点', displayName: 'Junction', path: '/json/pipes_junction.json', type: 'circle' },
  { name: '排水口', displayName: 'Outfall', path: '/json/pipes_outfall.json', type: 'circle' },
  { name: '河流', displayName: 'River', path: '/json/river.json', type: 'line' },
]

const simulationResultFiles = [
  {
    name: '子汇水区模拟结果',
    displayName: 'Subcatchment Results',
    filename: 'out_subcatchments.json',
    type: 'fill',
  },

  {
    name: '管段模拟结果',
    displayName: 'Conduit Results',
    filename: 'out_links.json',
    type: 'line',
  },
  {
    name: '管点模拟结果',
    displayName: 'Junction Results',
    filename: 'out_nodes.json',
    type: 'circle',
  },
]

function getColor(name) {
  switch (name) {
    case '建筑物':
      return '#880000'
    case '堤坝':
      return '#FF8707'
    case '湖泊':
      return '#7fc8f8'
    case '土地':
      return '#FFFFFF'
    case '管段':
      return '#666666'
    case '管点':
      return '#550088'
    case '排水口':
      return '#770077'
    case '子汇水区':
      return '#9b9393'
    case '河流':
      return '#0153F8'
    case '道路':
      return '#FFFF00'
    case '管段模拟结果':
      return '#000000'
    case '管点模拟结果':
      return '#FF0088'
    case '子汇水区模拟结果':
      return '#929090'
    default:
      return '#000000'
  }
}

function getLanduseFillColor() {
  return [
    'match',
    ['get', 'landuse'],
    '水体',
    '#7fc8f8',
    '林地',
    '#5b8c5a',
    '草地',
    '#9fd356',
    '裸露土地',
    '#caa472',
    '硬化地面',
    '#9aa3ad',
    '#d9d9d9',
  ]
}

function getPaint(type, name) {
  if (type === 'fill') {
    const paintConfig = {
      'fill-color': name === '土地' ? getLanduseFillColor() : getColor(name),
      'fill-opacity': 0.6,
    }

    // 为子汇水区相关图层添加边框
    if (name === '子汇水区模拟结果') {
      paintConfig['fill-outline-color'] = '#5e5e5e' // 深灰色边框
    }
    return paintConfig
  } else if (type === 'circle') {
    return {
      'circle-color': getColor(name),
      'circle-radius': 5,
      'circle-opacity': 0.7,
    }
  }
  return {}
}

export { originalDataFiles, simulationResultFiles, getColor, getPaint }
