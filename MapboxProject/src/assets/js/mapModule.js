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

function getDepthPaint(type, maximum) {
  const safeMaximum = Number.isFinite(maximum) && maximum > 0 ? maximum : 1
  const color = [
    'case',
    ['!', ['has', 'depth']],
    '#a8b1b5',
    [
      'interpolate',
      ['linear'],
      ['max', 0, ['to-number', ['get', 'depth'], 0]],
      0,
      DEPTH_COLORS[0],
      safeMaximum * 0.33,
      DEPTH_COLORS[1],
      safeMaximum * 0.66,
      DEPTH_COLORS[2],
      safeMaximum,
      DEPTH_COLORS[3],
    ],
  ]
  if (type === 'circle') {
    return {
      'circle-color': color,
      'circle-radius': 5,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
    }
  }
  return {
    'line-color': color,
    'line-width': 3,
    'line-opacity': 0.92,
  }
}

export { DEPTH_COLORS, getDepthPaint, getPaint }
