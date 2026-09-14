# runswmm

把 SWMM 的模拟结果整理成**二维水动力模型（LISFLOOD）可以用的输入**：

- 一张**点位流量表**（节点名 + 平均流量 + 坐标），
- 一份**虚拟降雨雨型**（代表模拟结束时还滞留在汇水区地表的水量）。

| | |
|---|---|
| 入口 | 仓库根目录的 `main.py` |
| 输入 | `data\swmm\` 下的模型文件：`<模型名>.inp` |
| 输出 | `data\results\` 下的 2 个 JSON + 1 个 TXT（详见 §3、§4） |

---

## 1. 运行前

```powershell
cd C:\work\runswmm
```

模型文件放在 `data\swmm\` 下时，**只写文件名**即可（会自动去那里找）；也可以直接给完整路径。

下面的命令都建议用绝对路径的解释器（`main.py` 需要它来复算汇水区蓄水量）：

```powershell
C:\Users\sshao\.conda\envs\gistoswmm5\python.exe main.py --help
```

---

## 2. `main.py` 怎么用

### 2.1 最常用：解析已有报告

```powershell
C:\Users\sshao\.conda\envs\gistoswmm5\python.exe main.py --report LC_MANUAL_23.rpt
```

**不会重跑模型，也不会改动 `data\swmm\` 下的任何原始文件。** 只要 `data\swmm\` 里有配对的 `.inp` 和 `.rpt` 就能跑。

### 2.2 其它三种用法

```powershell
# ① 先跑一遍模型，再解析新生成的报告
#    （如果同名 .rpt / .out 已存在会报错，不会覆盖）
C:\Users\sshao\.conda\envs\gistoswmm5\python.exe main.py LC_MANUAL_23.inp

# ② 覆盖已有的 .rpt / .out 后重新跑
#    ⚠️ 会就地覆盖 data\swmm 下的原始报告文件，请确认后再用
C:\Users\sshao\.conda\envs\gistoswmm5\python.exe main.py --force LC_MANUAL_23.inp

# ③ 指定输出位置（含蓄水那份会自动跟着改名：rate_demo_with_sub.json）
C:\Users\sshao\.conda\envs\gistoswmm5\python.exe main.py --report LC_MANUAL_23.rpt -o D:\out\rate_demo.json
```

### 2.3 全部参数

| 参数 | 说明 |
|---|---|
| `target` | 要运行的 `.inp` 路径或文件名（不给就必须用 `--report`） |
| `--report <x.rpt>` | **只解析**已有的报告，不重跑模型（推荐） |
| `--force` | 允许覆盖已存在的 `.rpt` / `.out` |
| `-o`, `--out <路径>` | 指定"不含汇水区蓄水"那份 JSON 的输出路径 |
| `--no-chi` | 不生成虚拟降雨雨型 TXT |
| `--surface-storage off` | 跳过汇水区地表蓄水量计算（快一些；含蓄水那份会偏低，仅供调试） |
| `--no-scale-storage` | 不把反推的蓄水量按报告的 Final Storage 缩放 |
| `--include-real-outfalls` | 把 `out1`/`out2`… 这类实际排放口也放进流量表（默认不放） |
| `-q`, `--quiet` | 只打印输出文件路径 |

### 2.4 运行完的屏幕输出

```text
INP : C:\work\runswmm\data\swmm\LC_MANUAL_23.inp
RPT : C:\work\runswmm\data\swmm\LC_MANUAL_23.rpt
[不含蓄水：溢流+出水口排放] JSON: ...\data\results\rate_LC_MANUAL_23.json
[不含蓄水：溢流+出水口排放] rate 条目数            : 828
[不含蓄水：溢流+出水口排放] Σ 参与 rate 的水量     : 1,806,898.000 m3 (折合 501.916 m3/s)
[不含蓄水：溢流+出水口排放]   ├ 节点溢流量        : 1,528,724.000 m3
[不含蓄水：溢流+出水口排放]   └ 排放口出流量      : 278,174.000 m3
[不含蓄水：溢流+出水口排放]   （+ 汇水区地表蓄水量 3,065,208.963 m3 = 含蓄水口径 ...）
...
[含蓄水：+汇水区地表蓄水] JSON: ...\data\results\rate_LC_MANUAL_23_with_sub.json
...
CHI : ...\data\results\chi_LC_MANUAL_23.txt   # 虚拟降雨雨型：雨量 25.917 mm = ...，历时 1 h，日期 07/15/2025

JSON saved: ...\data\results\rate_LC_MANUAL_23.json
JSON saved: ...\data\results\rate_LC_MANUAL_23_with_sub.json
```

---

## 3. 一次运行输出什么文件

全部写在 `data\results\` 下；用 `-o` 指定路径时，两个 JSON 会写到指定位置，`chi_*.txt` 仍然写在 `data\results\`：

| 文件 | 内容 | 什么时候用 |
|---|---|---|
| `rate_<模型名>.json` | 点位流量表：**只算离开管网的水**（节点溢流量 + 出水口排放量），不含汇水区滞蓄 | 配 `chi_<模型名>.txt` 一起送给二维模型 |
| `rate_<模型名>_with_sub.json` | 同样的点位，但**把汇水区地表蓄水量按汇水区归属加到了对应节点上** | 想只用一张点位表就把全部水量送出去时用 |
| `chi_<模型名>.txt` | 虚拟降雨雨型：把"留在汇水区的水"转成一场雨 | 配 `rate_<模型名>.json` 一起用 |

三者都是同一份结果的**不同切法，水量不重不漏**

---

## 4. `data\results` 文件夹里是什么

### 4.1 命名规则

`<模型名>` = 输入文件的主干名，例如 `data\swmm\LC_MANUAL_23.inp` → `rate_LC_MANUAL_23.json`、`chi_LC_MANUAL_23.txt`。

```text
data\results\
├── rate_LC_MANUAL_23.json            ← 点位流量表（不含汇水区蓄水）
├── rate_LC_MANUAL_23_with_sub.json   ← 点位流量表（含蓄水）
├── chi_LC_MANUAL_23.txt              ← 虚拟降雨雨型
├── rate_JJ_MANUAL_7.json
├── rate_JJ_MANUAL_7_with_sub.json
└── chi_JJ_MANUAL_7.txt
```

每次运行某个模型，只会覆盖它自己那三个文件。

---

### 4.2 `rate_*.json` 的格式

顶层结构（两个文件的字段完全相同，只有 `rate` 的数值和口径标注不同）：

```json
{
  "rate": [
    {"node": "J273", "rate": 0.650556,  "coordinate": [405822.3911, 2210839.4801]},
    {"node": "J266", "rate": 0.393333,  "coordinate": [406758.4689, 2211023.1981]},
    {"node": "sea41", "rate": 11.912222, "coordinate": [394754.6039, 2202059.4810]}
  ],
  "original": { "...": "明细与核对信息，见 4.2.2" },
  "rate_basis": "without_subcatchment_storage",
  "rate_basis_note": "不含汇水区地表蓄水：rate = (...)"
}
```

#### 4.2.1 `rate` —— 给下游直接用的表

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `node` | string | — | 节点名（`J*` / `sea*` / `mount*` / `vir*` …） |
| `rate` | number | **m³/s** | 模拟时段内的**平均**流量 |
| `coordinate` | `[x, y]` 或 `null` | 工程坐标 | 与 `.inp` 的 `[COORDINATES]` 同坐标系；该节点没有坐标时为 `null` |

`rate` 的计算口径由文件名区分（模拟时长即 `.inp` 里 `[OPTIONS]` 的起止时间之差）：

```text
rate_<模型名>.json
    rate = (该节点累计溢流量 + 该节点排放口排放量) / (模拟时长 × 3600)
           └ 节点漫出管网的水        └ sea*/mount* 排走的水

rate_<模型名>_with_sub.json
    rate = (上面两项 + Σ该节点关联汇水区的地表蓄水量) / (模拟时长 × 3600)
```

实测对照（`LC_MANUAL_23`，模拟 1 h）：

| 节点 | 类型 | 溢流量 | 排放量 | 关联汇水区蓄水 | `rate_*.json` | `..._with_sub.json` |
|---|---|---:|---:|---:|---:|---:|
| `J273` | junction | 2 342 m³ | — | 196.8 m³ | **0.650556** | 0.705232 |
| `sea41` | 虚拟出水口 | — | 42 884 m³ | 324 504 m³ | **11.912222** | 102.052336 |

> 一个节点既没有溢流也没有排放量时，`rate` 就是 `0`。

**哪些节点会进这张表**：被汇水区指定为出口的节点，以及名字是 `sea*` / `mount*` / `vir*` 的排放口，
加溢流的节点。

#### 4.2.2 `original` —— 明细与核对（下游可以整块忽略）

| 字段 | 说明 |
|---|---|
| `report_path` / `inp_path` | 本次解析的两个输入文件 |
| `flow_unit` | 报告用的流量单位（本项目模型是 `LPS`） |
| `rate_basis` | 本文件的 rate 口径（与顶层同名） |
| `start_date` `start_time` `end_date` `end_time` | 模拟起止时间 |
| `sim_hours` | 模拟时长（小时），`rate` 的分母就是它 |
| `runoff_continuity_error` / `routing_continuity_error` | 两张 Continuity 表的误差（%） |
| `flooding_loss_volume` / `flooding_loss_volume_secondary` | Flow Routing Continuity 的 Flooding Loss（hectare-m / 10⁶ ltr 两列） |
| `outfall_flows` | **逐排放口**：`node, flow_frequency, average_flow, maximum_flow, total_volume`（体积单位 10⁶ ltr）+ 追加的 `surface_storage_m3`、`subcatchments`；末尾还有一行 `System` 是系统汇总，不是真实节点 |
| `node_flooding` | **逐溢流节点**：`node, hours_flooded, maximum_rate, time_of_max, total_flood_volume, maximum_ponded_volume`（10⁶ ltr）+ 追加的 `surface_storage_m3`、`subcatchments` |
| `link_peak_flows` | **逐管段**峰值：`link, link_type, maximum_flow, time_of_max, maximum_velocity, max_full_flow, max_full_depth` |
| `conduit_surcharge` | **逐管段**满流时长：`conduit, hours_full_both_ends, hours_full_upstream, hours_full_downstream, hours_above_full_normal_flow, hours_capacity_limited` |
| `coordinates` | 全部节点坐标 `{节点名: [x, y]}`（本案例 919 个） |
| `outlet_storage` | **逐节点的水量构成 + 两套 rate 数值**（见下表），是 `rate` 的核对版，与它一一对应 |
| `subcatch_surface_storage` | **逐汇水区**的水量平衡（见下表） |
| `surface_storage_meta` | 取数方法、总量核对、告警（见下表） |
| `excluded_real_outfalls` | 未进入 `rate` 表的实际排放口明细（默认规则下才有；保证"没进表"不等于"丢数据"） |
| `kept_real_outfalls_by_subcatchment` | 因被汇水区指定为出口而保留在表里的实际排放口 |
| `subcatchment_outlets` | 汇水区 → 出口节点 映射 `{汇水区: 节点}` |
| `subcatchments` / `outfalls` | `.inp` 里 `[SUBCATCHMENTS]` / `[OUTFALLS]` 的解析结果 |

`outlet_storage` 每一条：

```json
{
  "node": "J273", "node_class": "junction", "is_virtual_outfall": true,
  "coordinate": [405822.3911, 2210839.4801], "coordinate_source": "coordinates",
  "n_subcatchments": 1, "subcatchments": ["S851"],
  "surface_storage_m3": 196.833599, "node_flood_volume_m3": 2342.0,
  "outfall_outflow_m3": 0.0, "total_volume_m3": 2538.833599,
  "without_sub_volume_m3": 2342.0,
  "rate_basis": "without_subcatchment_storage",
  "rate_basis_volume_m3": 2342.0,
  "rate_m3s": 0.650556, "rate_without_sub_m3s": 0.650556, "rate_with_sub_m3s": 0.705232
}
```

`subcatch_surface_storage` 每一条（单位统一 m³ / mm；`*_raw` 是未缩放的原始反推值）：

```json
{
  "name": "S851", "outlet": "J273", "area_m2": 24595.37,
  "precip_m3": 1229.7685, "runon_m3": 0.0, "evap_m3": 0.0,
  "infil_m3": 24.847824, "runoff_m3": 1017.22103,
  "surface_storage_raw_m3": 187.699646, "surface_storage_m3": 196.833599,
  "surface_storage_depth_mm": 8.002872
}
```

`surface_storage_meta` 里最值得看的几个键：

| 键 | 含义 |
|---|---|
| `rate_basis` / `rate_basis_note` / `rate_basis_components` | 本文件的口径、说明、分子由哪些分项组成 |
| `rate_basis_volume_in_rate_m3` / `rate_basis_total_m3s` | 参与 rate 的总水量 / 折合总流量 |
| `rate_basis_water_balance_check` | 两套口径的水量守恒核对（`difference_m3` 应为 0） |
| `total_surface_storage_in_rate_m3` | Σ 汇水区地表蓄水量 |
| `raw_total_m3` / `reported_total_m3` / `scale_factor` | 反推总量 / 报告官方总量 / 缩放系数 |
| `flooding_retention_check` | 溢流水有多少还留在 SWMM 里（见 §5） |
| `warnings` | **务必阅读**的告警列表（口径提醒、数据异常等） |

---

### 4.3 `chi_*.txt` 的格式

就是一段 SWMM 的 `[TIMESERIES]` 文本，可以直接整段粘进 `.inp`，也可以整体替换已有的 `[TIMESERIES]` 段：

```text
[TIMESERIES]
;;Name           Date       Time       Value     
;;-------------- ---------- ---------- ----------
TS1H25_CHI	07/15/2025	00:00:00	18.5698
TS1H25_CHI	07/15/2025	00:05:00	20.9149
TS1H25_CHI	07/15/2025	00:10:00	24.1388
...
TS1H25_CHI	07/15/2025	00:55:00	16.1684
TS1H25_CHI	07/15/2025	01:00:00	0.0000
```

| 项 | 规则 |
|---|---|
| 时序名 | `TS<历时小时>H<雨量mm>_CHI`，例如 `TS1H25_CHI`（1 h、25 mm） |
| 每行 | `时序名 TAB 日期 MM/DD/YYYY TAB 时刻 HH:MM:SS TAB 强度值` |
| 强度值 | **mm/h**，5 min 一个 |
| 时段数 | 模拟时长 / 5 min（1 h → 12 个），最后另补一行 `0` 表示降雨结束 |
| 总雨量 | Σ(强度 × 5 min) = 报告里 **Runoff Quantity Continuity → Final Storage 的 mm 值**（`LC_MANUAL_23`：25.917 mm，取整后命名 `TS1H25_CHI`） |
| 日期 | 模型 `.inp` 里的起始日期（两小时以内跨天的情形请自行核对） |
| 用途 | 代表"模拟结束时还留在汇水区地表、没进管网"的水量，与 `rate_<模型名>.json` 配套使用 |

