"""Chicago rainfall generator migrated from the runswmm reference sample."""

from __future__ import annotations


STEP_MINUTES = 5
PEAK_RATIO = 0.4
_A = 20.0
_B = 8.0
_C = 0.7


def chicago_intensity_series(duration_hours: float, total_mm: float) -> list[tuple[int, float]]:
    """Return ``(offset_seconds, mm_per_hour)`` values using the sample algorithm."""
    if duration_hours <= 0 or total_mm <= 0:
        raise ValueError("降雨历时和总雨量必须大于 0")
    step_count = int(duration_hours * 60 / STEP_MINUTES)
    if step_count <= 0:
        raise ValueError("降雨历时不足一个 5 分钟步长")

    peak_minutes = duration_hours * 60 * PEAK_RATIO
    raw: list[float] = []
    for index in range(step_count):
        current_minutes = index * STEP_MINUTES
        distance = abs(current_minutes - peak_minutes)
        raw.append(_A / ((distance + _B) ** _C))

    scale = total_mm / (sum(raw) * STEP_MINUTES / 60.0)
    return [(index * STEP_MINUTES * 60, intensity * scale) for index, intensity in enumerate(raw)]


def chicago_rain_generator(duration_h: float, total_mm: float) -> tuple[str, str, str]:
    """Return the original runswmm ``[TIMESERIES]`` payload and summary text."""
    rows = chicago_intensity_series(duration_h, total_mm)
    name = f"TS{int(duration_h)}H{int(total_mm)}_CHI"
    lines = [
        "[TIMESERIES]",
        ";;Name           Date       Time       Value     ",
        ";;-------------- ---------- ---------- ----------",
    ]
    for offset_seconds, intensity in rows:
        minutes = offset_seconds // 60
        lines.append(
            f"{name}\t07/15/2025\t{minutes // 60:02d}:{minutes % 60:02d}:00\t{intensity:.4f}"
        )
    lines.append(f"{name}\t07/15/2025\t{int(duration_h):02d}:00:00\t0.0000")
    summary = (
        f"【生成完成】时序名:{name} | 历时:{duration_h}h | 设计雨量:{total_mm} mm\n"
        f"【校验】实际生成总雨量：{sum(value for _, value in rows) * STEP_MINUTES / 60.0:.2f} mm\n"
    )
    return name, "\n".join(lines), summary
