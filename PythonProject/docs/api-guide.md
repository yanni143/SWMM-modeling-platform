# SWMM 后端 API 使用指南

本文档整理当前后端实际注册的全部 HTTP 接口，包括接口用途、请求格式、响应格式和常见错误。接口实现以 `Controller/model_routes.py`、`Controller/run_routes.py` 和 `Controller/controller.py` 为准。

## 1. 系统约束

- 系统是固定研究区系统：LC 为老城，JJ 为金江；接口继续使用 `LC`、`JJ` 编码。
- 后端启动时幂等初始化两区的模拟降雨基线 V1，并为金江登记真实降雨的独立完整 INP 基线。
- 金江可选 `design`（模拟降雨）或 `real`（真实降雨），老城仅支持 `design`。切换方案是选择对应的版本，不是参数修改，无需先创建新版本即可运行。
- 模拟降雨的默认模拟时长上限为 172800 秒（48 小时），实际限制以参数目录返回值为准。
- 真实降雨固定覆盖 2026-09-13 00:00 至 2026-09-15 00:00，模拟时长 172800 秒、降雨开始偏移 0 秒、资料覆盖时长 172800 秒、总雨量 226.2 mm；工程参数及输出步长仍可调整。
- 不提供用户上传 INP 文件的接口。
- 参数调整不会覆盖原版本，而是以指定版本为父版本创建一个新版本。
- 同一版本允许执行多次模拟。数据库和 MinIO 保留每次运行，但面向用户的历史结果列表只展示每个版本最新一次成功运行。
- 地图结果接口只返回最后一个模拟时间步，避免同一几何重复压盖。
- 时间序列接口返回指定对象的全部时间步，供结果弹窗和图表使用。
- 当前接口没有鉴权机制。

真实降雨基线来自 `resources/rainfall/jj/JJ_real_20260913_2d.inp`，采用 5 分钟累计雨量。资料覆盖时长包含无雨时段。版本号在同一研究区内统一递增，真实降雨基线不是固定的 V2；应使用 `rainfall_inputs[].baseline_version_id` 定位方案基线，使用版本的 `rainfall_mode` 区分方案。两个方案都可以包含多个调参版本。

## 2. 基础约定

### 2.1 服务地址

本地开发环境通常使用：

```text
http://localhost:8000
```

业务接口统一使用 `/api` 前缀，健康检查除外。

### 2.2 数据格式

- 普通请求和响应：`application/json`
- INP 下载响应：`text/plain; charset=utf-8`
- LISFLOOD 点源输入下载响应：`application/json`，文件名为 `rate_<研究区>_without_sub.json`
- LISFLOOD 虚拟降雨下载响应：`text/plain; charset=utf-8`，文件名为 `chi_<研究区>.txt`
- ID：标准 UUID 字符串，例如 `10000000-0000-0000-0000-000000000101`
- 数据库记录时间：ISO 8601 字符串，例如 `2026-08-11T05:59:30.123456Z`
- 模拟开始/结束时间和结果 `timestamp`：模型中的无时区时间，例如 `2026-09-13T00:05:00`；不应自行按浏览器时区平移
- GeoJSON 坐标：地图输出统一为 `EPSG:4326`，坐标顺序为 `[longitude, latitude]`
- JSON 字段为 `null` 时表示该值不存在或当前结果无法提供

### 2.3 自动接口文档

FastAPI 默认提供：

| 地址 | 用途 |
| --- | --- |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI JSON |

### 2.4 通用错误格式

业务错误通常返回：

```json
{
  "detail": "工程版本不存在"
}
```

路径、查询参数或请求体校验失败时，FastAPI 返回 `422 Unprocessable Entity`，`detail` 为校验错误数组：

```json
{
  "detail": [
    {
      "type": "uuid_parsing",
      "loc": [
        "path",
        "version_id"
      ],
      "msg": "Input should be a valid UUID",
      "input": "invalid-id"
    }
  ]
}
```

常见状态码：

| 状态码 | 含义 |
| --- | --- |
| `200` | 查询、运行或下载成功 |
| `201` | 新工程版本创建成功 |
| `404` | 模型、版本或 INP section 不存在 |
| `422` | 参数校验失败、INP 无效、模拟失败或业务条件不满足 |
| `500` | 未分类的服务端错误 |
| `503` | MinIO 对象存储不可用 |

## 3. 接口总览

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/health` | 检查数据库和 MinIO 状态 |
| `GET` | `/api/models` | 获取固定研究区模型列表 |
| `GET` | `/api/study-areas/latest-model-versions` | 按降雨方案获取研究区最新版本 ID，默认 `design` |
| `GET` | `/api/models/{model_id}` | 获取模型详情 |
| `GET` | `/api/models/{model_id}/versions` | 获取模型的全部版本 |
| `GET` | `/api/model-versions/{version_id}/sections` | 获取版本中的 INP section 摘要 |
| `GET` | `/api/model-versions/{version_id}/sections/{section_name}` | 获取一个 INP section 的记录 |
| `GET` | `/api/model-versions/{version_id}/layers` | 获取版本的原始 INP 空间图层 |
| `GET` | `/api/model-versions/{version_id}/editable-parameters` | 获取可调参数目录 |
| `POST` | `/api/model-versions/{version_id}/versions` | 基于指定版本和参数修改创建新版本 |
| `GET` | `/api/model-versions/{version_id}/download` | 下载指定版本的 INP 文件 |
| `POST` | `/api/model-versions/{version_id}/runs` | 运行指定版本 |
| `GET` | `/api/model-results` | 获取每个版本最新一次成功结果的摘要 |
| `GET` | `/api/model-versions/{version_id}/latest-result/layers` | 获取版本最新结果的地图图层 |
| `GET` | `/api/model-versions/{version_id}/latest-result/timeseries` | 查询单个对象的完整时间序列 |
| `GET` | `/api/model-versions/{version_id}/latest-result/timeline` | 获取完整结果时间轴、字段范围和单位元数据 |
| `GET` | `/api/model-versions/{version_id}/latest-result/steps/{time_index}` | 获取指定时间步的全部结果图层 |
| `GET` | `/api/runs/{run_id}/layers` | 按具体运行 ID 获取地图结果图层 |
| `GET` | `/api/runs/{run_id}/lisflood-input` | 下载某一次运行的 LISFLOOD 点源输入 |
| `GET` | `/api/model-versions/{version_id}/latest-result/lisflood-input` | 下载版本最近一次成功运行的 LISFLOOD 点源输入 |
| `GET` | `/api/runs/{run_id}/lisflood-virtual-rainfall` | 下载某一次运行的 LISFLOOD 虚拟降雨 |
| `GET` | `/api/model-versions/{version_id}/latest-result/lisflood-virtual-rainfall` | 下载版本最近一次成功运行的 LISFLOOD 虚拟降雨 |

## 4. 通用数据结构

### 4.1 工程版本 `ModelVersionRead`

```json
{
  "id": "10000000-0000-0000-0000-000000000101",
  "model_id": "10000000-0000-0000-0000-000000000001",
  "parent_version_id": null,
  "version": 1,
  "checksum": "7d8f...",
  "size_bytes": 872653,
  "change_summary": null,
  "created_by": "system",
  "created_at": "2026-08-11T05:30:00Z",
  "rainfall_mode": "design"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 版本 ID |
| `model_id` | UUID | 所属模型 ID |
| `parent_version_id` | UUID \| null | 父版本；各内置输入基线均为 `null`，不能仅据此判断降雨类型 |
| `version` | integer | 用户可见版本号，如 `1`、`2` |
| `checksum` | string \| null | MinIO 对象校验值 |
| `size_bytes` | integer \| null | INP 文件大小 |
| `change_summary` | object \| null | 本版本的修改摘要 |
| `created_by` | string \| null | 创建者 |
| `created_at` | datetime | 创建时间 |
| `rainfall_mode` | string | `design` 或 `real`；没有降雨类型摘要的历史版本按 `design` 返回 |

调参版本继承父版本的降雨方案。`change_summary` 会记录 `rainfall_mode` 和 `rainfall_event_id`；实测基线的 `source` 为 `system_rainfall_input`，实测事件标识为 `jj_real_20260913_2d`。这些新增字段不改变现有版本 ID。

### 4.2 地图图层 `GeoJsonLayer`

```json
{
  "id": "inp-subcatchments",
  "name": "子汇水区",
  "geometry_type": "fill",
  "source": "inp",
  "source_crs": "EPSG:4549",
  "display_crs": "EPSG:4326",
  "geojson": {
    "type": "FeatureCollection",
    "features": []
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定图层 ID |
| `name` | string | 图层显示名 |
| `geometry_type` | string | Mapbox 图层类型：`fill`、`line` 或 `circle` |
| `source` | string | `inp` 或 `simulation` |
| `source_crs` | string \| null | 原始坐标系；模拟结果可能为 `null` |
| `display_crs` | string | 输出坐标系，默认 `EPSG:4326` |
| `geojson` | GeoJSON FeatureCollection | 图层空间数据 |

当前图层 ID：

| 数据来源 | 图层 ID | 几何类型 |
| --- | --- | --- |
| 原始 INP | `inp-subcatchments` | Polygon / `fill` |
| 原始 INP | `inp-conduits` | LineString / `line` |
| 原始 INP | `inp-nodes` | Point / `circle` |
| 模拟结果 | `result-subcatchments` | Polygon / `fill` |
| 模拟结果 | `result-conduits` | LineString / `line` |
| 模拟结果 | `result-nodes` | Point / `circle` |

### 4.3 模拟结果 Feature 属性

所有模拟结果 Feature 都包含：

```json
{
  "name": "211",
  "time_index": 11,
  "timestamp": "2025-07-15T01:00:00"
}
```

其中 `time_index` 是从 `0` 开始的时间步索引，`timestamp` 是模型时间。历史产物可能使用旧字段 `time`，读取时可用 `properties.time_index ?? properties.time` 兼容。不同结果图层还包含：

| 图层 | 结果字段 |
| --- | --- |
| `result-nodes` | `depth`、`head`、`ponded_v`、`lateral_i`、`total_i`、`flooding` |
| `result-conduits` | `rate`、`depth`、`velocity`、`volume`、`capacity` |
| `result-subcatchments` | `rain`、`snow`、`evap`、`infilt`、`runoff`、`gw_flow`、`soil_moist` |

结果值为 number 或 `null`。

## 5. 健康检查

### `GET /health`

检查数据库连接和 MinIO bucket 是否可用。无需请求参数或请求体。

成功响应始终为 `200`；依赖异常通过 `status: "degraded"` 表达：

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "minio": "ok"
  }
}
```

`checks.database` 和 `checks.minio` 的值为 `ok` 或 `unavailable`。

## 6. 模型与版本接口

### 6.1 获取研究区最新版本

`GET /api/study-areas/latest-model-versions`

用途：供 LISFLOOD 按降雨方案获取内置研究区当前最新的模型版本。在选定方案内按最大版本号（`version`）确定，而不是跨方案取最大值。模拟降雨按 `LC`、`JJ` 顺序返回，真实降雨仅返回 `JJ`。取得 `version_id` 后，可调用对应的 `latest-result/lisflood-input` 和 `latest-result/lisflood-virtual-rainfall` 下载接口。

查询参数（无请求体）：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `rainfall_mode` | string | 否 | `design` | `design` 为模拟降雨，`real` 为真实降雨；其他值返回 `422` |

```http
GET /api/study-areas/latest-model-versions
GET /api/study-areas/latest-model-versions?rainfall_mode=real
```

不传参数现在明确表示查询模拟降雨方案；原有调用若想取得真实降雨的最新版本，必须指定 `rainfall_mode=real`。最新模型版本可能尚未运行成功，此时其 `latest-result/*` 接口返回 `422`，本接口不会回退到上一个有结果的版本。

响应：`200 OK`，返回 `StudyAreaLatestVersion[]`。

```json
[
  {
    "study_area": "LC",
    "model_id": "10000000-0000-0000-0000-000000000001",
    "version_id": "10000000-0000-0000-0000-000000000101",
    "version": 1
  },
  {
    "study_area": "JJ",
    "model_id": "20000000-0000-0000-0000-000000000001",
    "version_id": "20000000-0000-0000-0000-000000000101",
    "version": 1
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `study_area` | string | 稳定的研究区编码：`LC` 或 `JJ` |
| `model_id` | UUID | 研究区模型 ID |
| `version_id` | UUID | 后续 LISFLOOD 下载接口所需的版本 ID |
| `version` | integer | 该研究区所选降雨方案内的最新版本号 |

### 6.2 获取模型列表

`GET /api/models`

用途：获取系统内置研究区模型列表。

请求：无参数、无请求体。

响应：`200 OK`，返回 `ModelListItem[]`。

```json
[
  {
    "id": "10000000-0000-0000-0000-000000000001",
    "name": "LC",
    "description": "LC_MANUAL_23 SWMM 研究区",
    "status": "active",
    "created_at": "2026-08-11T05:30:00Z",
    "updated_at": "2026-08-11T05:30:00Z",
    "version_count": 1,
    "latest_version": 1,
    "rainfall_inputs": [
      {
        "mode": "design",
        "label": "模拟降雨",
        "baseline_version_id": "10000000-0000-0000-0000-000000000101",
        "filename": "model.inp"
      }
    ]
  },
  {
    "id": "20000000-0000-0000-0000-000000000001",
    "name": "JJ",
    "description": "JJ_MANUAL_7 SWMM 研究区",
    "status": "active",
    "created_at": "2026-08-11T05:30:00Z",
    "updated_at": "2026-08-11T05:30:00Z",
    "version_count": 2,
    "latest_version": 2,
    "rainfall_inputs": [
      {
        "mode": "design",
        "label": "模拟降雨",
        "baseline_version_id": "20000000-0000-0000-0000-000000000101",
        "filename": "model.inp"
      },
      {
        "mode": "real",
        "label": "真实降雨（20260913）",
        "baseline_version_id": "20000000-0000-0000-0000-000000000102",
        "filename": "JJ_real_20260913_2d.inp"
      }
    ]
  }
]
```

以上为全新部署的示意数据，升级已有系统时版本数与编号可能不同。`latest_version` 在没有版本时可能为 `null`。`version_count` 和 `latest_version` 是整个研究区的统计，包含两个降雨方案；不能用它们判断当前方案的最新版本。

`rainfall_inputs` 为可选输入方案数组：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | string | `design` 或 `real` |
| `label` | string | 方案显示名称 |
| `baseline_version_id` | UUID | 可直接加载、运行的基线版本 ID |
| `filename` | string | 内置源 INP 的文件名 |

模型列表顺序不作保证。前端应将 `LC` 显示为“老城”、`JJ` 显示为“金江”，方案选项以各模型的 `rainfall_inputs` 为准。模型详情接口不包含列表专有的统计字段和 `rainfall_inputs`。

### 6.3 获取模型详情

`GET /api/models/{model_id}`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | UUID | 模型 ID |

响应：`200 OK`。

```json
{
  "id": "10000000-0000-0000-0000-000000000001",
  "name": "LC",
  "description": "LC_MANUAL_23 SWMM 研究区",
  "status": "active",
  "created_at": "2026-08-11T05:30:00Z",
  "updated_at": "2026-08-11T05:30:00Z"
}
```

可能错误：`404` 模型不存在；`422` UUID 格式错误；`503` MinIO 不可用；`500` 工程服务异常。

### 6.4 获取模型版本列表

`GET /api/models/{model_id}/versions`

路径参数：`model_id`，UUID。

响应：`200 OK`，返回 `ModelVersionRead[]`，按版本号降序排列。该列表包含研究区全部降雨方案；本接口没有 `rainfall_mode` 筛选参数。前端应按返回的 `rainfall_mode` 筛选，再选择相应 `baseline_version_id` 或该方案中已保存的版本。

```json
[
  {
    "id": "10000000-0000-0000-0000-000000000101",
    "model_id": "10000000-0000-0000-0000-000000000001",
    "parent_version_id": null,
    "version": 1,
    "checksum": "7d8f...",
    "size_bytes": 872653,
    "change_summary": null,
    "created_by": "system",
    "created_at": "2026-08-11T05:30:00Z",
    "rainfall_mode": "design"
  }
]
```

可能错误：`404` 模型不存在；`422` UUID 格式错误；`503` MinIO 不可用；`500` 工程服务异常。

### 6.5 获取版本 INP section 摘要

`GET /api/model-versions/{version_id}/sections`

用途：列出 INP 文件中的全部 section，以及每个 section 的记录数、可编辑状态和字段定义。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "10000000-0000-0000-0000-000000000101",
  "sections": [
    {
      "name": "SUBCATCHMENTS",
      "record_count": 560,
      "editable": true,
      "fields": [
        "name",
        "raingage",
        "outlet",
        "area",
        "imperv",
        "width",
        "slope",
        "curb_length",
        "snowpack"
      ]
    }
  ]
}
```

可能错误：`404` 版本不存在；`422` INP 无效或 UUID 格式错误；`503` MinIO 不可用。

### 6.6 获取单个 INP section

`GET /api/model-versions/{version_id}/sections/{section_name}`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `version_id` | UUID | 工程版本 ID |
| `section_name` | string | INP section 名称，不带方括号，例如 `CONDUITS` |

section 名称在服务中会转换为大写。

响应：`200 OK`。

```json
{
  "version_id": "10000000-0000-0000-0000-000000000101",
  "section": {
    "name": "CONDUITS",
    "editable": true,
    "fields": [
      "name",
      "from_node",
      "to_node",
      "length",
      "roughness",
      "in_offset",
      "out_offset",
      "init_flow",
      "max_flow"
    ],
    "record_count": 1,
    "records": [
      {
        "index": 0,
        "target": "C1",
        "values": {
          "name": "C1",
          "from_node": "J1",
          "to_node": "J2",
          "length": "100",
          "roughness": "0.013",
          "in_offset": "0",
          "out_offset": "0",
          "init_flow": "0",
          "max_flow": "0"
        },
        "extra_values": [],
        "raw": "C1 J1 J2 100 0.013 0 0 0 0"
      }
    ]
  }
}
```

注意：section 中的原始值以字符串返回；未知 section 没有字段映射时，数据保存在 `extra_values` 中。

可能错误：`404` 版本或 section 不存在；`422` UUID 格式错误、INP 无效；`503` MinIO 不可用。

### 6.7 获取原始 INP 地图图层

`GET /api/model-versions/{version_id}/layers`

用途：把 `[POLYGONS]`、`[COORDINATES]`、`[VERTICES]` 等空间 section 转成地图可直接使用的 GeoJSON。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "10000000-0000-0000-0000-000000000101",
  "layers": [
    {
      "id": "inp-subcatchments",
      "name": "子汇水区",
      "geometry_type": "fill",
      "source": "inp",
      "source_crs": "EPSG:4549",
      "display_crs": "EPSG:4326",
      "geojson": {
        "type": "FeatureCollection",
        "features": [
          {
            "type": "Feature",
            "geometry": {
              "type": "Polygon",
              "coordinates": [
                [
                  [
                    120.84,
                    31.03
                  ],
                  [
                    120.85,
                    31.03
                  ],
                  [
                    120.84,
                    31.03
                  ]
                ]
              ]
            },
            "properties": {
              "name": "S1",
              "area": "1.2",
              "imperv": "35"
            }
          }
        ]
      }
    }
  ]
}
```

补充规则：

- `[COORDINATES]` 中可能存在子汇水区中心点，但只有在实际节点 section 中声明的标识才会进入 `inp-nodes`。
- 投影坐标会按配置的 `SWMM_INPUT_CRS` 转换成 `EPSG:4326`。
- 没有有效 Feature 的图层不会出现在 `layers` 数组中。

可能错误：`404` 版本不存在；`422` INP 无效；`503` MinIO 不可用。

### 6.8 获取可调参数目录

`GET /api/model-versions/{version_id}/editable-parameters`

用途：为前端调参面板返回安全、受限的对象字段目录、模拟设置，以及当前输入方案的降雨设置和只读状态。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "10000000-0000-0000-0000-000000000101",
  "groups": [
    {
      "id": "subcatchments",
      "label": "子汇水区",
      "map_layer": "inp-subcatchments",
      "objects": [
        {
          "target": "S1",
          "element_type": "subcatchment",
          "fields": [
            {
              "key": "SUBCATCHMENTS.imperv",
              "section": "SUBCATCHMENTS",
              "field": "imperv",
              "label": "不透水率",
              "unit": "%",
              "value": "35",
              "minimum": 0,
              "maximum": 100,
              "step": 0.1
            }
          ]
        }
      ]
    }
  ],
  "simulation_options": {
    "start_datetime": "2025-01-01T00:00:00",
    "end_datetime": "2025-01-01T02:00:00",
    "duration_seconds": 7200,
    "report_step_seconds": 600,
    "routing_step_seconds": 10.0,
    "duration_min_seconds": 60,
    "duration_max_seconds": 172800,
    "report_step_min_seconds": 10,
    "max_output_steps": 1000,
    "require_report_step_divisible": false
  },
  "rainfall_options": {
    "start_seconds": 0,
    "duration_seconds": 7200,
    "end_seconds": 7200,
    "total_rainfall_mm": 120.0,
    "peak_rainfall_mm_h": 129.23,
    "gage_name": "RG1",
    "series_name": "Rainfall01",
    "time_step_seconds": 300,
    "peak_ratio": 0.4,
    "formula": "runswmm_chicago",
    "mode": "design",
    "event_id": null,
    "read_only": false,
    "real_event": null
  }
}
```

字段约束：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | string | 前端使用的稳定字段键 |
| `section` | string | INP section |
| `field` | string | 可修改字段名 |
| `label` | string | 显示名称 |
| `unit` | string | 单位，可能为空字符串 |
| `value` | string | 当前 INP 原始值 |
| `minimum` | number | 最小允许值 |
| `maximum` | number | 最大允许值 |
| `step` | number | 建议调节步长 |

客户端应以接口返回的字段目录为准，不应自行构造任意 section 或字段名。

模拟与降雨字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `simulation_options.duration_seconds` | integer | 从模型开始时刻计算的模拟总时长，单位秒 |
| `simulation_options.report_step_seconds` | integer | 结果输出步长，单位秒 |
| `simulation_options.routing_step_seconds` | number | 当前路由步长，单位秒，只读 |
| `rainfall_options.start_seconds` | integer | 相对模拟开始时刻的起雨时间，单位秒 |
| `rainfall_options.duration_seconds` | integer | 降雨持续时间，单位秒 |
| `rainfall_options.end_seconds` | integer | 后端根据开始时间和时长计算的停雨时间，单位秒 |
| `rainfall_options.total_rainfall_mm` | number | 总降雨量，单位 mm |
| `rainfall_options.peak_rainfall_mm_h` | number | 生成曲线的峰值雨强，单位 mm/h，只读 |
| `rainfall_options.gage_name` | string | `[RAINGAGES]` 中使用该时间序列的雨量计名称 |
| `rainfall_options.series_name` | string | 被替换的 `[TIMESERIES]` 时间序列名称 |
| `rainfall_options.time_step_seconds` | integer | 时间序列间隔；新生成的模拟降雨和当前实测事件均为 300 秒，旧序列按雨量计间隔读取 |
| `rainfall_options.peak_ratio` | number | 设计降雨峰现系数为 0.4；真实降雨模式不使用该系数生成曲线 |
| `rainfall_options.formula` | string | 新设计降雨为 `runswmm_chicago`，未带设计元数据的序列为 `existing_timeseries`，真实降雨为 `observed_cumulative` |
| `rainfall_options.mode` | string | 当前版本对应的 `design` 或 `real` |
| `rainfall_options.event_id` | string \| null | 真实降雨为 `jj_real_20260913_2d`，模拟降雨为 `null` |
| `rainfall_options.read_only` | boolean | 为 `true` 时降雨开始、时长及总雨量只读；模拟时长同时固定为实测覆盖时长，工程参数及输出步长仍可调整 |
| `rainfall_options.real_event` | object \| null | 金江返回内置实测事件元数据，即使当前版本属于模拟降雨；老城为 `null` |

设计降雨元数据仅解析带有 `schema=2` 的 `;@DESIGN_RAIN` 注释。没有该标记的旧注释和没有注释的基线版本，都会根据现有降雨时间序列的非零范围、累计雨量和峰值推算当前设置；新创建的设计降雨版本会写入 `schema=2` 元数据以便准确回显。

真实降雨原始 INP 不需要该注释，其类型来自版本元数据。`CUMULATIVE` 累计雨量按相邻值差分统计，总雨量为 226.2 mm，峰值雨强为 132 mm/h；不能将累计值直接按雨强求和。

`real_event` 示例（这里的 `duration_seconds` 为降雨资料覆盖时长，`simulation_duration_seconds` 为固定模拟时长）：

```json
{
  "event_id": "jj_real_20260913_2d",
  "label": "真实降雨（20260913）",
  "start_datetime": "2026-09-13T00:00:00",
  "end_datetime": "2026-09-15T00:00:00",
  "simulation_duration_seconds": 172800,
  "report_step_seconds": 300,
  "start_seconds": 0,
  "duration_seconds": 172800,
  "total_rainfall_mm": 226.2,
  "peak_rainfall_mm_h": 132.0,
  "time_step_seconds": 300
}
```

### 6.9 创建调参版本

`POST /api/model-versions/{version_id}/versions`

用途：基于路径中的父版本应用普通对象参数、模拟设置和/或设计降雨设置，并创建新的不可变版本。

请求头：

```text
Content-Type: application/json
```

路径参数：`version_id`，父版本 UUID。

请求体 `CreateAdjustedVersionRequest`：

```json
{
  "summary": "调整不透水率、模拟时长和设计降雨",
  "created_by": "demo-user",
  "changes": [
    {
      "section": "SUBCATCHMENTS",
      "target": "S1",
      "field": "imperv",
      "new_value": "42"
    },
    {
      "section": "CONDUITS",
      "target": "C1",
      "field": "roughness",
      "new_value": "0.015"
    }
  ],
  "simulation_options": {
    "duration_seconds": 7200,
    "report_step_seconds": 300
  },
  "rainfall_options": {
    "start_seconds": 600,
    "duration_seconds": 4800,
    "total_rainfall_mm": 120.0
  }
}
```

请求约束：

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| `summary` | 否 | string 或 `null`，最长 500 字符 |
| `created_by` | 否 | string 或 `null`，最长 100 字符 |
| `changes` | 条件必填 | 0 到 5000 项；与 `simulation_options`、`rainfall_options` 至少提交一种修改 |
| `changes[].section` | 是 | string，最长 64 字符 |
| `changes[].target` | 是 | string，1 到 200 字符 |
| `changes[].field` | 是 | string，1 到 100 字符 |
| `changes[].new_value` | 是 | string，1 到 100 字符 |
| `simulation_options` | 条件必填 | 对象或 `null`；提供时必须同时包含以下两个字段 |
| `simulation_options.duration_seconds` | 是 | 严格整数，默认范围 60～172800 秒；真实降雨固定 172800 秒 |
| `simulation_options.report_step_seconds` | 是 | 严格整数，不小于路由步长、不大于模拟时长，并满足最大输出点约束 |
| `rainfall_options` | 条件必填 | 对象或 `null`；模拟降雨提供时必须同时包含开始、时长、总雨量三个字段 |
| `rainfall_options.mode` | 否 | 默认 `design`；必须与父版本方案一致，不用于切换输入方案 |
| `rainfall_options.event_id` | 否 | 模拟降雨必须省略或为 `null`；真实降雨仅支持 `jj_real_20260913_2d` |
| `rainfall_options.start_seconds` | 模拟降雨必填 | 严格整数且不小于 0，必须为 300 秒的整数倍 |
| `rainfall_options.duration_seconds` | 模拟降雨必填 | 严格正整数，必须为 300 秒的整数倍 |
| `rainfall_options.total_rainfall_mm` | 模拟降雨必填 | 严格正数且为有限值，单位 mm |

原有仅提交三个数值的模拟降雨请求仍受支持。真实降雨版本修改工程参数时，省略 `rainfall_options`；修改输出步长时提交 `simulation_options`，同时保持 `duration_seconds=172800`。若显式提供真实降雨配置，必须设置 `mode=real`，且提供的数值必须与实测事件一致；仅提交未变化的事件配置不能创建新版本。方案切换应直接选择另一个方案的版本 ID，跨方案保存返回 `422`。

例如，基于金江真实降雨基线调整管道粗糙度，无需提交任何降雨字段（对象名称以参数目录为准）：

```http
POST /api/model-versions/20000000-0000-0000-0000-000000000102/versions
Content-Type: application/json
```

```json
{
  "summary": "调整实测方案管道粗糙度",
  "changes": [
    {
      "section": "CONDUITS",
      "target": "C4",
      "field": "roughness",
      "new_value": "0.02"
    }
  ]
}
```

该请求创建新的 `rainfall_mode=real` 版本，保留原实测降雨序列及时间范围。

两天模拟使用 300 秒输出步长为 576 个输出点，在默认 1000 点限制内；300 秒是实测文件的初始输出步长，用户可以在现有约束内修改。

设计降雨生成和写入规则：

- 后端采用 `Tools/InpTools/ChicagoRainfall.py` 中的样例算法，标识为 `runswmm_chicago`，峰现系数 `r=0.4`。
- 原始权重为 `20 / (abs(t - 0.4 * T) + 8)^0.7`，其中 `t`、`T` 以分钟计；再统一缩放使离散总雨量等于 `total_rainfall_mm`。当前不接收重现期参数。
- 起雨前与停雨后的时间点写入 0；降雨区间按 300 秒步长生成。
- 后端根据 `[RAINGAGES]` 的 `TIMESERIES` 引用定位目标名称，只替换该名称在 `[TIMESERIES]` 中的记录，其他时间序列保持不变。
- 雨量计格式同步为 `INTENSITY`，记录间隔为 `0:05`。英制流量模型写入前会将 mm/h 转换为 in/h。
- 第一版要求所有使用内嵌时间序列的雨量计引用同一个降雨时间序列；否则返回 `422`。
- `end_seconds` 由 `start_seconds + duration_seconds` 计算；同时修改模拟时长和降雨时，以修改后的模拟时长校验降雨结束时间。
- 这些生成规则仅用于模拟降雨；真实降雨版本调整工程参数或输出步长时保留完整实测序列。

响应：`201 Created`。

```json
{
  "version": {
    "id": "da2e27c4-7dfa-4b0b-a1a4-77bce5710ff0",
    "model_id": "10000000-0000-0000-0000-000000000001",
    "parent_version_id": "10000000-0000-0000-0000-000000000101",
    "version": 2,
    "checksum": "9a31...",
    "size_bytes": 872701,
    "change_summary": {
      "summary": "调整子汇水区不透水率与管道粗糙系数"
    },
    "created_by": "demo-user",
    "created_at": "2026-08-11T06:00:00Z",
    "rainfall_mode": "design"
  },
  "changes": [
    {
      "operation": "set",
      "section": "SUBCATCHMENTS",
      "target": "S1",
      "field": "imperv",
      "old_value": "35",
      "new_value": "42",
      "label": "Imperviousness",
      "unit": "%"
    }
  ]
}
```

可能错误：

- `404`：父版本不存在。
- `422`：字段不可编辑、对象不存在、数值越界、降雨范围超过模拟时长、修改真实降雨固定条件、试图跨方案保存、存在多个不同降雨时间序列、提交内容未变化、请求体不符合约束或生成的 INP 无效。
- `503`：MinIO 不可用。

### 6.10 下载版本 INP

`GET /api/model-versions/{version_id}/download`

路径参数：`version_id`，UUID。

响应：`200 OK`，响应体为 INP 原始文本。

```text
Content-Type: text/plain; charset=utf-8
Content-Disposition: attachment; filename="model-v2.inp"
```

此接口不是 JSON 响应。客户端可以按文件流下载。

可能错误：`404` 版本不存在；`422` UUID 格式错误；`503` MinIO 不可用。

## 7. 模拟运行与结果接口

### 7.1 运行指定版本

`POST /api/model-versions/{version_id}/runs`

用途：下载版本 INP、调用 SWMM、解析 OUT/RPT 文件、保存输入/输出/报告/可视化产物，并生成方案三所需的 LISFLOOD 点源输入与虚拟降雨。

路径参数：`version_id`，UUID。无请求体。

当前接口是同步接口：HTTP 请求会等待模拟和结果解析完成。

响应：`200 OK`。

```json
{
  "run_id": "c8b121e0-264f-4b2f-8179-8b230c4a00ae",
  "model_version_id": "10000000-0000-0000-0000-000000000101",
  "version": 1,
  "status": "success",
  "layers": [
    {
      "id": "result-subcatchments",
      "name": "子汇水区模拟结果",
      "geometry_type": "fill",
      "source": "simulation",
      "source_crs": null,
      "display_crs": "EPSG:4326",
      "geojson": {
        "type": "FeatureCollection",
        "features": [
          {
            "type": "Feature",
            "geometry": {
              "type": "Polygon",
              "coordinates": []
            },
            "properties": {
              "name": "S1",
              "rain": 0.0,
              "runoff": 0.0021,
              "infilt": 0.0,
              "evap": 0.0,
              "snow": 0.0,
              "gw_flow": null,
              "soil_moist": null,
              "time_index": 11,
              "timestamp": "2025-07-15T01:00:00"
            }
          }
        ]
      }
    }
  ],
  "artifacts": [
    {
      "type": "visual",
      "bucket": "swmm-artifacts",
      "object_key": "runs/c8b121e0-264f-4b2f-8179-8b230c4a00ae/visual/result-subcatchments.geojson",
      "filename": "result-subcatchments.geojson",
      "size_bytes": 2841201
    }
  ]
}
```

`layers` 只包含每个对象最后一个时间步。MinIO 中的 visual GeoJSON 仍保存全部时间步。

产物 `type` 可能包括：

| type | 说明 |
| --- | --- |
| `input` | 本次运行使用的 INP |
| `raw_out` | SWMM 原始 OUT 文件 |
| `report` | SWMM RPT 报告 |
| `visual` | 完整时间步 GeoJSON |
| `lisflood` | 不含汇水区滞蓄的 LISFLOOD 点源输入 JSON |
| `lisflood_virtual_rainfall` | 由 RPT Final Storage 生成的 LISFLOOD 虚拟降雨 TXT |

可能错误：`422` 版本不存在、运行失败或 OUT 未生成；`503` MinIO 不可用；`500` 未分类运行服务错误。

### 7.2 获取历史结果摘要

`GET /api/model-results`

用途：按工程版本聚合成功运行。每个版本只返回最新一次成功运行，用于历史结果下拉框。

查询参数：可选 `model_id`（UUID），不传时返回全部模型的成功结果；无请求体。

此接口没有 `rainfall_mode` 参数。金江结果列表可能同时包含两套方案，前端需将 `version_id` 与当前方案的版本 ID 集合关联过滤；响应本身不包含降雨类型字段。

响应：`200 OK`。

```json
[
  {
    "version_id": "10000000-0000-0000-0000-000000000101",
    "version": 1,
    "effective_run_id": "c8b121e0-264f-4b2f-8179-8b230c4a00ae",
    "created_at": "2026-08-11T05:59:00Z",
    "finished_at": "2026-08-11T05:59:30Z"
  }
]
```

没有成功运行时返回空数组。`finished_at` 可能为 `null`。

### 7.3 获取版本最新结果地图图层

`GET /api/model-versions/{version_id}/latest-result/layers`

用途：取得指定版本最新一次成功运行的结果，用于刷新后恢复 RUN 图层。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "10000000-0000-0000-0000-000000000101",
  "version": 1,
  "effective_run_id": "c8b121e0-264f-4b2f-8179-8b230c4a00ae",
  "created_at": "2026-08-11T05:59:00Z",
  "finished_at": "2026-08-11T05:59:30Z",
  "layers": [
    {
      "id": "result-nodes",
      "name": "节点模拟结果",
      "geometry_type": "circle",
      "source": "simulation",
      "source_crs": null,
      "display_crs": "EPSG:4326",
      "geojson": {
        "type": "FeatureCollection",
        "features": []
      }
    }
  ]
}
```

响应中的每个对象只保留最后一个 `time_index`（历史数据可能为 `time`）。完整时序应通过下一接口查询。

可能错误：`422` 版本不存在或该版本没有成功结果；`503` MinIO 不可用。

### 7.4 查询对象时间序列

`GET /api/model-versions/{version_id}/latest-result/timeseries`

用途：从指定版本最新一次成功运行的完整 visual GeoJSON 中，查询某个对象的全部时间步。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `version_id` | UUID | 工程版本 ID |

查询参数：

| 参数 | 类型 | 必填 | 约束 | 示例 |
| --- | --- | --- | --- | --- |
| `layer_id` | string | 是 | 1 到 100 字符 | `result-subcatchments` |
| `feature_name` | string | 是 | 1 到 200 字符 | `S1` |

请求示例：

```http
GET /api/model-versions/10000000-0000-0000-0000-000000000101/latest-result/timeseries?layer_id=result-subcatchments&feature_name=S1
```

允许的 `layer_id`：

- `result-subcatchments`
- `result-conduits`
- `result-nodes`

响应：`200 OK`，返回 GeoJSON FeatureCollection。Feature 按时间步索引升序排列（优先 `properties.time_index`，兼容历史 `properties.time`）。响应还包含 `field_metadata`，提供各结果字段的单位；单位由模型 `FLOW_UNITS` 决定。

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      },
      "properties": {
        "name": "S1",
        "rain": 0.0,
        "runoff": 0.0,
        "infilt": 0.0,
        "evap": 0.0,
        "snow": 0.0,
        "gw_flow": null,
        "soil_moist": null,
        "time_index": 0,
        "timestamp": "2025-07-15T00:05:00"
      }
    },
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      },
      "properties": {
        "name": "S1",
        "rain": 1.3,
        "runoff": 0.12,
        "infilt": 0.4,
        "evap": 0.0,
        "snow": 0.0,
        "gw_flow": null,
        "soil_moist": null,
        "time_index": 1,
        "timestamp": "2025-07-15T00:10:00"
      }
    }
  ],
  "field_metadata": {
    "rain": {
      "unit": "mm/hr"
    },
    "snow": {
      "unit": "mm"
    },
    "evap": {
      "unit": "mm/hr"
    },
    "infilt": {
      "unit": "mm/hr"
    },
    "runoff": {
      "unit": "L/s"
    },
    "gw_flow": {
      "unit": "L/s"
    },
    "soil_moist": {
      "unit": null
    }
  }
}
```

对象不存在时目前返回 `200` 和空 `features` 数组。

可能错误：

- `422`：查询参数缺失或过长、`layer_id` 不支持、版本没有成功结果或缺少结果产物。
- `503`：MinIO 不可用。

### 7.5 按运行 ID 获取结果图层

`GET /api/runs/{run_id}/layers`

用途：读取某一次具体运行的 visual 产物。与按版本查询不同，本接口不会自动选择该版本的最新运行。

路径参数：`run_id`，UUID。

响应：`200 OK`，返回 `GeoJsonLayer[]`。

```json
[
  {
    "id": "result-conduits",
    "name": "管线模拟结果",
    "geometry_type": "line",
    "source": "simulation",
    "source_crs": null,
    "display_crs": "EPSG:4326",
    "geojson": {
      "type": "FeatureCollection",
      "features": []
    }
  }
]
```

地图响应同样只保留最后一个时间步。

可能错误：`422` 运行记录不存在；`503` MinIO 不可用；UUID 格式错误时返回 FastAPI `422`。

### 7.6 下载 LISFLOOD 方案三输入

方案三将 SWMM 结果拆分为两份**必须配套使用**的数据：

1. 点源输入只包含节点溢流和出水口排放，不包含汇水区地表滞蓄；
2. 虚拟降雨将 `.rpt` 中 `Runoff Quantity Continuity → Final Storage` 的面雨深，按对应研究区的“SWMM 汇水面积 / LISFLOOD 二维域面积”缩放后等效为芝加哥雨型，代表被从点源中剥离的汇水区地表滞蓄。

不要将虚拟降雨与含汇水区滞蓄的点源流量表一起使用，否则会重复计算这部分水量。当前 API 不生成 `rate_*_with_sub.json`。

#### 7.6.1 下载点源输入

精确指定一次运行：

`GET /api/runs/{run_id}/lisflood-input`

按工程版本自动选取最近一次成功运行：

`GET /api/model-versions/{version_id}/latest-result/lisflood-input`

两个接口的响应内容相同，区别仅在于定位运行的方式。响应示例：

```text
Content-Type: application/json
Content-Disposition: attachment; filename="rate_JJ_MANUAL_7_without_sub.json"
```

JSON 结构：

```json
{
  "rate": [
    {
      "node": "J181",
      "rate": 3.550278,
      "coordinate": [
        396826.8302363448,
        2184008.14446223
      ]
    }
  ]
}
```

`rate` 单位为 **m³/s**，计算方式为节点累计溢流体积与排放口累计出流体积之和，除以模拟总时长。RPT 体积列使用 `10^6 ltr`，后端先乘以 `1000` 转为 m³，再除以 `sim_hours × 3600`。

#### 7.6.2 下载虚拟降雨

精确指定一次运行：

`GET /api/runs/{run_id}/lisflood-virtual-rainfall`

按工程版本自动选取最近一次成功运行：

`GET /api/model-versions/{version_id}/latest-result/lisflood-virtual-rainfall`

响应示例：

```text
Content-Type: text/plain; charset=utf-8
Content-Disposition: attachment; filename="chi_JJ_MANUAL_7.txt"
```

文件为可直接使用的 SWMM `[TIMESERIES]` 文本。例如：

```text
[TIMESERIES]
;;Name           Date       Time       Value
TS1H29_CHI       07/15/2025 00:00:00  21.4659
TS1H29_CHI       07/15/2025 00:05:00  24.1768
...
TS1H29_CHI       07/15/2025 01:00:00  0.0000
```

规则：

- 总雨量：RPT 的 `Final Storage` 的 `mm` 列乘研究区面积系数。LC 为 `118,270,207.3 / 150,174,375 = 0.7875525189`，JJ 为 `34,281,610.5 / 63,401,875 = 0.5407034177`；
- 降雨历时：INP `[OPTIONS]` 的模拟起止时间之差；
- 日期：INP 的 `START_DATE`；
- 雨强单位：`mm/h`；步长为 5 分钟，峰值比例 `r=0.4`；
- 时序名：`TS<历时小时>H<雨量整数部分>_CHI`。

如果 RPT 中缺少 `Final Storage`，或其值小于等于零，SWMM 运行仍会成功，点源输入仍可下载；虚拟降雨 artifact 不会生成，对应虚拟降雨下载接口返回 `422`。历史运行在此功能上线前没有该 artifact，也需要重新运行后才能下载。

真实降雨方案仍使用上述 LISFLOOD 文件结构与生成规则。虚拟降雨表示 RPT 中的地表滞蓄水量，并非原始实测降雨序列；原始实测数据可通过对应版本的 INP 下载接口取得。

可能错误：`422` 运行/版本不存在、没有成功运行或该运行没有可用虚拟降雨；`503` MinIO 不可用。

### 7.7 获取结果时间轴

`GET /api/model-versions/{version_id}/latest-result/timeline`

路径参数：`version_id`，UUID；无查询参数、无请求体。返回指定版本最新成功结果的完整时间轴、数值字段范围与单位，响应模型为 `ResultTimeline`。

以下示例仅展示首尾两项，实际 `steps` 返回全部输出时间步：

```json
{
  "version_id": "20000000-0000-0000-0000-000000000102",
  "version": 2,
  "effective_run_id": "c8b121e0-264f-4b2f-8179-8b230c4a00ae",
  "steps": [
    {"time_index": 0, "timestamp": "2026-09-13T00:05:00"},
    {"time_index": 575, "timestamp": "2026-09-15T00:00:00"}
  ],
  "result_ranges": {
    "result-nodes": {
      "depth": {"minimum": 0.0, "maximum": 1.2}
    }
  },
  "result_metadata": {
    "result-nodes": {
      "depth": {"unit": "m"}
    }
  }
}
```

`version` 和数值范围仅作示意，实际值取决于部署历史与运行结果。`time_index` 从 0 开始；`timestamp` 为模型时间，旧产物可能为 `null`。`result_ranges` 按图层 ID、数值字段名索引，跨全部时间步统计；`result_metadata` 包含字段单位，量纲为比例或无单位时为 `null`。两天模拟采用 300 秒输出步长时有 576 项，首项是第 5 分钟，末项是第 48 小时。

可能错误：`422` 版本不存在、没有成功结果或缺少结果产物；`503` MinIO 不可用。

### 7.8 获取指定时间步结果

`GET /api/model-versions/{version_id}/latest-result/steps/{time_index}`

路径参数：`version_id`（UUID）、`time_index`（integer）；无请求体。应使用时间轴接口返回的索引。

响应：`200 OK`，返回与最新结果地图接口相同的 `VersionResultLayers` 结构，但 `layers` 仅包含所选时间步的 Feature。返回的 `effective_run_id` 标识该次查询实际使用的最新成功运行；若在交互期间完成了新运行，应重新加载时间轴。

```http
GET /api/model-versions/20000000-0000-0000-0000-000000000102/latest-result/steps/575
```

不存在的时间步索引当前返回 `200`，各图层的 `features` 为空；不是 `404`。非整数索引返回 FastAPI `422`。其他可能错误：`422` 版本不存在或没有成功结果；`503` MinIO 不可用。

## 8. 推荐前端调用流程

### 8.1 初始化

1. 调用 `GET /api/models`，选择研究区及其 `rainfall_inputs` 中的降雨方案。
2. 调用 `GET /api/models/{model_id}/versions`，按 `rainfall_mode` 筛选版本。首次进入方案时使用其 `baseline_version_id`，后续可恢复该方案已选择的版本。
3. 调用所选版本的 `/layers` 和 `/editable-parameters`，加载对应完整 INP 的地图与参数。
4. 调用 `GET /api/model-results?model_id={model_id}`，与当前方案版本 ID 集合关联后展示历史结果。
5. 按研究区及降雨方案分别保存所选版本、活动结果。切换时清理旧参数和图层，并忽略已失效的异步响应，防止混用。

### 8.2 调参和运行

1. 未修改参数时，直接调用 `POST /api/model-versions/{selected_version_id}/runs`；切换方案本身不调用创建版本接口。
2. 修改参数后，根据当前参数目录构造 `changes`、`simulation_options` 和/或 `rainfall_options`，再调用 `POST /api/model-versions/{parent_version_id}/versions`。
3. 真实降雨模式锁定模拟时长和三项降雨数值；工程参数修改可照常保存，降雨序列保持不变。新版本继承父版本方案。
4. 运行新版本，使用响应中的最后时间步 `layers` 更新地图，并重新加载当前方案的结果列表。

### 8.3 历史结果和弹窗

1. 按当前研究区及方案筛选历史结果，展示每个版本的最新成功运行。
2. 用户选择版本后调用 `GET /api/model-versions/{version_id}/latest-result/layers`。
3. 用户点击结果对象后，使用图层 ID、对象 `properties.name` 和版本 ID 调用时间序列接口。
4. 图表使用 `properties.timestamp` 展示模型时间，`properties.time_index ?? properties.time` 作为索引，字段单位读取 `field_metadata`。
5. 动画和时间步选择先加载 `/latest-result/timeline`，再按索引调用 `/latest-result/steps/{time_index}`。

## 9. cURL 示例

获取模型列表：

```bash
curl http://localhost:8000/api/models
```

按降雨方案查询最新版本（实测查询仅返回金江）：

```bash
curl http://localhost:8000/api/study-areas/latest-model-versions
curl "http://localhost:8000/api/study-areas/latest-model-versions?rainfall_mode=real"
```

以下调参示例使用老城基线。运行和下载示例中的版本 ID 应替换为本次实际选择或新建的版本 ID，`target`、`feature_name` 应以该版本返回的对象名称为准。

创建调参版本：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/versions \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "调整 S1 不透水率和设计降雨",
    "created_by": "demo-user",
    "changes": [
      {
        "section": "SUBCATCHMENTS",
        "target": "S1",
        "field": "imperv",
        "new_value": "42"
      }
    ],
    "simulation_options": {
      "duration_seconds": 7200,
      "report_step_seconds": 300
    },
    "rainfall_options": {
      "start_seconds": 600,
      "duration_seconds": 4800,
      "total_rainfall_mm": 120.0
    }
  }'
```

运行版本：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/runs
```

直接运行内置实测基线（无需先保存参数）：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/20000000-0000-0000-0000-000000000102/runs
```

查询时间序列：

```bash
curl "http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/latest-result/timeseries?layer_id=result-subcatchments&feature_name=S1"
```

下载 INP：

```bash
curl -OJ \
  http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/download
```

下载当前版本最新成功运行的 LISFLOOD 方案三输入：

```bash
curl -OJ \
  http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/latest-result/lisflood-input

curl -OJ \
  http://localhost:8000/api/model-versions/10000000-0000-0000-0000-000000000101/latest-result/lisflood-virtual-rainfall
```
