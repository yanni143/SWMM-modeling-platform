// CSV/paste contract: one depth per row, or explicit offset_seconds,rainfall_mm.
// Offsets denote interval starts; blanks are ignored, missing intervals are errors.
export function parseRainfallText(text: string, step: number): number[] {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
  const values: number[] = [];
  let columns = 0;
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index].trim();
    if (!line) continue;
    if (!values.length && /^(rainfall_mm|offset_seconds\s*[,\t]\s*rainfall_mm)$/i.test(line))
      continue;
    const cells = line.split(/[,\t]/).map((cell) => cell.trim());
    if (!columns) columns = cells.length;
    if (cells.length !== columns || ![1, 2].includes(cells.length) || cells.some((cell) => !cell))
      throw new Error(`第 ${index + 1} 行格式无效：每行填写雨量，或“偏移秒数,雨量”`);
    if (cells.length === 2 && Number(cells[0]) !== values.length * step)
      throw new Error(`第 ${index + 1} 行时间应为 ${values.length * step} 秒，序列须从 0 连续排列`);
    const raw = cells.at(-1)!;
    const value = Number(raw);
    if (
      !/^[+]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw) ||
      !Number.isFinite(value) ||
      value < 0
    )
      throw new Error(`第 ${index + 1} 行雨量必须是不小于 0 的有限数值（mm）`);
    values.push(value);
    if (values.length > 10000) throw new Error('降雨序列最多支持 10000 条记录');
  }
  if (!values.length) throw new Error('请粘贴或导入降雨序列');
  return values;
}

export function rainfallStats(values: number[], step: number) {
  return {
    duration: values.length * step,
    total: values.reduce((sum, value) => sum + value, 0),
    peak: (Math.max(0, ...values) * 3600) / step,
  };
}
