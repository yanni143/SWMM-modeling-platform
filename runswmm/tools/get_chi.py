"""
SWMM 芝加哥雨型生成器
- 时序命名：TS{DURATION}H{TOTALMM}_CHI
- 输出控制台 + 同名txt文件
- 步长5min，峰值系数 r=0.4
生成的value单位为mm/h

用法（交互式，和以前一样）:
    python tools/get_chi.py

用法（被别的脚本调用，例如 main.py 生成虚拟降雨）:
    from tools.get_chi import chicago_rain_generator, write_chicago_file
    ts_name, text, info = chicago_rain_generator(duration_h=1.0, total_mm=25.917)
    path = write_chicago_file(1.0, 25.917, out_path="data/results/chi_LC_MANUAL_23.txt",
                              date_str="07/15/2025")

说明：
  * 生成函数只依赖 (历时, 总雨量, 日期)，不改动任何降雨参数
    （r=0.4、步长 5 min、A=20/b=8/c=0.7 均保持现状）；
  * 总雨量按强度序列等比缩放，保证 Σ(i × Δt) == total_mm；
  * 时序名里的雨量按 int() 截断（沿用历史命名，例如 25.917 mm -> TS1H25_CHI）；
  * 文件末尾补一行 0 值，结束时刻 = 最后一个步长 + 5 min
    （整点历时与旧版一致；非整点历时旧版会写出倒退的时间戳，这里按步长推算）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 默认日期：与 data/swmm 下两份 MANUAL 模型的 [OPTIONS] START_DATE 一致。
# 被 main.py 调用时会传入模型自己的模拟起始日期。
DEFAULT_DATE = "07/15/2025"


def chicago_rain_generator(
    duration_h: float,
    total_mm: float,
    *,
    date_str: str = DEFAULT_DATE,
):
    """生成芝加哥雨型的 [TIMESERIES] 文本。

    Args:
        duration_h: 降雨历时（小时）。通常取模型的模拟时长。
        total_mm: 设计总雨量（mm）。虚拟降雨场景下取 .rpt 的
            Runoff Quantity Continuity -> Final Storage 的 mm 值。
        date_str: 时序日期，格式 MM/DD/YYYY（默认 07/15/2025）。

    Returns:
        (ts_name, full_text, info_text)
          * ts_name   —— 时序名，如 TS1H25_CHI
          * full_text —— 可直接写进 .inp 的 [TIMESERIES] 文本
          * info_text —— 人读的校验信息
    """
    duration_h = float(duration_h)
    total_mm = float(total_mm)
    if duration_h <= 0:
        raise ValueError(f"降雨历时必须为正数（小时），收到 {duration_h}")
    if total_mm <= 0:
        raise ValueError(f"设计总雨量必须为正数（mm），收到 {total_mm}")

    dt_min = 5
    dt_h = dt_min / 60.0
    r = 0.4
    A = 20.0
    b = 8.0
    c = 0.7

    step_num = int(duration_h * 60 / dt_min)
    if step_num <= 0:
        raise ValueError(
            f"降雨历时 {duration_h} h 不足一个步长（{dt_min} min），无法生成雨型。")
    time_list = []
    intensity_list = []

    for s in range(step_num):
        t_curr = s * dt_min
        t_peak = duration_h * 60 * r

        if t_curr < t_peak:
            t = t_peak - t_curr
            i = A / ((t + b) ** c)
        else:
            t = t_curr - t_peak
            i = A / ((t + b) ** c)

        time_list.append(t_curr)
        intensity_list.append(i)

    # 缩放至目标总雨量
    sum_raw = sum(intensity_list) * dt_h
    scale = total_mm / sum_raw
    intensity_list = [v * scale for v in intensity_list]

    ts_name = f"TS{int(duration_h)}H{int(total_mm)}_CHI"

    out_lines = []
    out_lines.append("[TIMESERIES]")
    out_lines.append(";;Name           Date       Time       Value     ")
    out_lines.append(";;-------------- ---------- ---------- ----------")

    for idx, t_min in enumerate(time_list):
        hh = int(t_min // 60)
        mm = int(t_min % 60)
        time_str = f"{hh:02d}:{mm:02d}:00"
        val = intensity_list[idx]
        out_lines.append(f"{ts_name}\t{date_str}\t{time_str}\t{val:.4f}")

    # 末尾补0结束：结束时刻 = 最后一个步长 + 一个步长
    end_min = step_num * dt_min
    end_hh = int(end_min // 60)
    end_mm = int(end_min % 60)
    out_lines.append(f"{ts_name}\t{date_str}\t{end_hh:02d}:{end_mm:02d}:00\t0.0000")

    real_total = sum(intensity_list) * dt_h
    info_text = (
        f"【生成完成】时序名:{ts_name} | 历时:{duration_h}h | 设计雨量:{total_mm} mm\n"
        f"【校验】实际生成总雨量：{real_total:.2f} mm\n"
    )

    full_text = "\n".join(out_lines)
    return ts_name, full_text, info_text


def write_chicago_file(
    duration_h: float,
    total_mm: float,
    out_path: str | Path | None = None,
    *,
    date_str: str = DEFAULT_DATE,
    quiet: bool = False,
) -> Path:
    """生成芝加哥雨型并写出 txt 文件，返回写出的路径。

    Args:
        duration_h / total_mm / date_str: 同 chicago_rain_generator()。
        out_path: 输出路径；None 时写到当前目录的 <时序名>.txt（旧版行为）。
        quiet: True 则不打印生成信息。

    Returns:
        写出的文件路径（已 resolve）。
    """
    ts_name, content, info = chicago_rain_generator(
        duration_h, total_mm, date_str=date_str)

    if out_path is None:
        output = Path(f"{ts_name}.txt").expanduser().resolve()
    else:
        output = Path(out_path).expanduser().resolve()

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(content)
        f.write("\n")

    if not quiet:
        print(info, end="")
        print(f"✅已保存文件：{output}")
    return output


if __name__ == "__main__":
    print("===== SWMM 芝加哥雨型生成器 =====")
    try:
        dura = float(input("请输入降雨历时(小时): "))
        rain = float(input("请输入总降雨量(mm): "))
        ts_name, content, info = chicago_rain_generator(dura, rain)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    print("\n" + info)
    print(content)

    # 输出同名文本文件（旧行为：写到当前目录的 <时序名>.txt）
    path = write_chicago_file(dura, rain, out_path=f"{ts_name}.txt", quiet=True)
    print(f"\n✅已保存文件：{path}")
