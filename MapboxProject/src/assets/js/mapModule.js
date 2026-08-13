function getPaint(type, source = 'inp') {
  const isResult = source === 'simulation'
  const color = isResult ? '#d75838' : '#23748c'
  if (type === 'fill') {
    return {
      'fill-color': color,
      'fill-opacity': isResult ? 0.3 : 0.24,
      'fill-outline-color': color,
    }
  }
  if (type === 'circle') {
    return {
      'circle-color': color,
      'circle-radius': isResult ? 5 : 4,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
    }
  }
  return {
    'line-color': color,
    'line-width': isResult ? 3 : 2,
    'line-opacity': 0.9,
  }
}

const DEPTH_COLORS = ['#eaf6f8', '#9ddce5', '#318eae', '#083f66']
const FLOODING_COLORS = ['#fff3df', '#ffc46b', '#f28c28', '#b84600']

function getGradient(field, range, colors) {
  const minimum = Number.isFinite(range?.minimum) ? range.minimum : 0
  const maximum = Number.isFinite(range?.maximum) ? range.maximum : minimum
  const span = maximum > minimum ? maximum - minimum : 1
  return [
    'interpolate',
    ['linear'],
    ['max', minimum, ['to-number', ['get', field], minimum]],
    minimum,
    colors[0],
    minimum + span * 0.33,
    colors[1],
    minimum + span * 0.66,
    colors[2],
    minimum + span,
    colors[3],
  ]
}

function getNodeResultPaint(depthRange, floodingRange) {
  const flooding = ['to-number', ['get', 'flooding'], 0]
  const hasFlooding = ['>', flooding, 0]
  return {
    'circle-color': [
      'case',
      hasFlooding,
      getGradient('flooding', floodingRange, FLOODING_COLORS),
      ['has', 'depth'],
      getGradient('depth', depthRange, DEPTH_COLORS),
      '#a8b1b5',
    ],
    'circle-radius': 5,
    'circle-stroke-width': 0,
  }
}

function getConduitDepthPaint(depthRange) {
  return {
    'line-color': [
      'case',
      ['has', 'depth'],
      getGradient('depth', depthRange, DEPTH_COLORS),
      '#a8b1b5',
    ],
    'line-width': 3,
    'line-opacity': 0.92,
  }
}

export { DEPTH_COLORS, FLOODING_COLORS, getConduitDepthPaint, getNodeResultPaint, getPaint }
