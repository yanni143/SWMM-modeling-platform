"""
SWMM 芝加哥雨型生成器
- 时序命名：TS{DURATION}H{TOTALMM}_CHI
- 输出控制台 + 同名txt文件
- 步长5min，峰值系数 r=0.4
生成的value单位为mm/h
用法: python get_chi.py
"""

def chicago_rain_generator(duration_h: float, total_mm: float):
    dt_min = 5
    dt_h = dt_min / 60.0
    r = 0.4
    A = 20.0
    b = 8.0
    c = 0.7

    step_num = int(duration_h * 60 / dt_min)
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
    date_str = "07/15/2025"

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

    # 末尾补0结束
    end_hh = int(duration_h)
    out_lines.append(f"{ts_name}\t{date_str}\t{end_hh:02d}:00:00\t0.0000")

    real_total = sum(intensity_list) * dt_h
    info_text = (
        f"【生成完成】时序名:{ts_name} | 历时:{duration_h}h | 设计雨量:{total_mm} mm\n"
        f"【校验】实际生成总雨量：{real_total:.2f} mm\n"
    )

    full_text = "\n".join(out_lines)
    return ts_name, full_text, info_text


if __name__ == "__main__":
    print("===== SWMM 芝加哥雨型生成器 =====")
    dura = float(input("请输入降雨历时(小时): "))
    rain = float(input("请输入总降雨量(mm): "))

    ts_name, content, info = chicago_rain_generator(dura, rain)

    print("\n" + info)
    print(content)

    # 输出同名文本文件
    filename = f"{ts_name}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅已保存文件：{filename}")