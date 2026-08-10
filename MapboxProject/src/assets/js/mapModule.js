function getPaint(type, source = 'inp') {
  const isResult = source === 'simulation'
  const color = isResult ? '#d75838' : '#23748c'
  if (type === 'fill') {
    return {
      'fill-color': color,
      'fill-opacity': isResult ? 0.5 : 0.24,
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

export { getPaint }
