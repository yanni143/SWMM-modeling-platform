# SWMM 后端 API 使用指南

本文档整理当前后端实际注册的全部 HTTP 接口，包括接口用途、请求格式、响应格式和常见错误。接口实现以 `Controller/model_routes.py`、`Controller/run_routes.py` 和 `Controller/controller.py` 为准。

## 1. 系统约束

- 系统是固定研究区系统：LC 为老城，JJ 为金江；接口继续使用 `LC`、`JJ` 编码。
- 后端启动时幂等初始化每个研究区唯一的模拟降雨基线 V1；不再登记第二个真实降雨基线。
- 两区都支持 `design`（芝加哥雨型）和 `custom`（自定义固定间隔序列）；金江另外支持 `real`（内置真实降雨事件）。
- 降雨是当前工程版本的可编辑条件。修改降雨来源或序列时，通过创建派生版本接口保存，继承当前版本的工程参数；不通过切换另一个基线应用降雨。
- 默认模拟时长范围为 60～172800 秒（48 小时），实际限制以参数目录返回值为准。模拟时长必须覆盖完整降雨序列，不会自动延长、截断或重新生成降雨。
- 金江实测事件资料日期为 2026-09-13 00:00 至 2026-09-15 00:00，包含 576 个五分钟分段雨量，总雨量 226.2 mm。事件按相对时间应用，原始日期仅作资料说明，不修改模型开始日期。完整事件需要显式配置足够的模拟时长和满足输出点数限制的输出步长。
- 不提供用户上传 INP 文件的接口。CSV 导入由前端解析为 `values_mm` 数组，通过 JSON 请求提交；没有单独的 CSV 上传 API。
- 参数调整不会覆盖原版本，而是以指定版本为父版本创建一个新版本。省略 `rainfall_options` 时完整继承父版本降雨；仅修改工程参数或输出步长不会重新生成降雨。
- 同一版本允许执行多次模拟。数据库和 MinIO 保留每次运行，但面向用户的历史结果列表只展示每个版本最新一次成功运行。
- 地图结果接口只返回最后一个模拟时间步，避免同一几何重复压盖。
- 时间序列接口返回指定对象的全部时间步，供结果弹窗和图表使用。
- 当前接口没有鉴权机制。

内置实测事件读取 `resources/rainfall/jj/JJ_real_20260913_2d.json`，使用分段雨量（mm），覆盖时长包含无雨时段。原始累计记录已差分转换，不能将分段值再当作累计值差分，也不能将其当作 mm/h 雨强。

通过模型列表顶层的 `baseline_version_id` 定位唯一基线；版本号在同一研究区内统一递增。已有真实降雨旧根及其派生版本、运行记录和归档文件保持可访问，但不再作为初始基线，也不再自动补建。序列格式与升级说明见 [降雨序列与单基线版本](rainfall-sequences.md)。

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
| `GET` | `/api/study-areas/latest-model-versions` | 按降雨来源或全部来源获取研究区最新版本 ID，默认 `design` |
| `GET` | `/api/rainfall-events` | 查询研究区内置真实降雨事件及完整序列 |
| `POST` | `/api/rainfall/preview` | 校验并预览三种来源的降雨序列，不创建版本 |
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
| `parent_version_id` | UUID \| null | 父版本；唯一 V1 为 `null`，历史旧根也可能为 `null`，不能仅据此判断基线或降雨来源 |
| `version` | integer | 用户可见版本号，如 `1`、`2` |
| `checksum` | string \| null | MinIO 对象校验值 |
| `size_bytes` | integer \| null | INP 文件大小 |
| `change_summary` | object \| null | 本版本的修改摘要 |
| `created_by` | string \| null | 创建者 |
| `created_at` | datetime | 创建时间 |
| `rainfall_mode` | string | `design`、`real` 或 `custom`；没有降雨类型摘要的历史版本按 `design` 返回 |

省略降雨修改时，派生版本继承父版本降雨；提交 `rainfall_options` 可在同一版本链上切换来源。新派生版本的 `change_summary` 记录 `rainfall_mode`、`rainfall_event_id` 和 `rainfall_series_checksum`，实测事件标识为 `jj_real_20260913_2d`。完整序列保存在版本 INP 中，也由参数目录返回。旧记录中的 `source=system_rainfall_input` 仅用于历史追溯，不再产生此类新基线。

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

用途：供 LISFLOOD 获取内置研究区当前最新的模型版本。默认在 `design` 来源内按最大版本号（`version`）确定；指定 `real`、`custom` 时在对应来源内取最大值，指定 `all` 时跨来源取最大值。只返回存在匹配版本的研究区，并按 `LC`、`JJ` 顺序排列；当前真实事件来源仅支持金江，自定义来源在创建对应版本之前可能返回空数组。取得 `version_id` 后，可调用对应的 `latest-result/lisflood-input` 和 `latest-result/lisflood-virtual-rainfall` 下载接口。

查询参数（无请求体）：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `rainfall_mode` | string | 否 | `design` | `design` 为芝加哥雨型，`real` 为真实降雨，`custom` 为自定义序列，`all` 为全部来源；其他值返回 `422` |

```http
GET /api/study-areas/latest-model-versions
GET /api/study-areas/latest-model-versions?rainfall_mode=real
GET /api/study-areas/latest-model-versions?rainfall_mode=custom
GET /api/study-areas/latest-model-versions?rainfall_mode=all
```

不传参数继续查询模拟降雨来源；需要不区分来源的最新版本时指定 `rainfall_mode=all`。最新模型版本可能尚未运行成功，此时其 `latest-result/*` 接口返回 `422`，本接口不会回退到上一个有结果的版本。

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
| `version` | integer | 该研究区筛选范围内的最大版本号 |

### 6.2 获取模型列表

`GET /api/models`

用途：获取系统内置研究区模型列表。

请求：无参数、无请求体。

响应：`200 OK`，返回 `ModelListItem[]`。

```json[
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
    ],
    "baseline_version_id": "10000000-0000-0000-0000-000000000101"
  },
  {
    "id": "20000000-0000-0000-0000-000000000001",
    "name": "JJ",
    "description": "JJ_MANUAL_7 SWMM 研究区",
    "status": "active",
    "created_at": "2026-08-11T05:30:00Z",
    "updated_at": "2026-08-11T05:30:00Z",
    "version_count": 1,
    "latest_version": 1,
    "rainfall_inputs": [
      {
        "mode": "design",
        "label": "模拟降雨",
        "baseline_version_id": "20000000-0000-0000-0000-000000000101",
        "filename": "model.inp"
      }
    ],
    "baseline_version_id": "20000000-0000-0000-0000-000000000101"
  }
]
```

以上为全新部署的示意数据，升级已有系统时版本数与编号可能不同。`latest_version` 在没有版本时可能为 `null`。`version_count` 和 `latest_version` 是整个研究区的统计，包含所有降雨来源及历史版本。

`baseline_version_id` 是模型列表顶层的 UUID 字段，指向该研究区唯一 V1。`rainfall_inputs` 保留用于兼容旧客户端，当前只包含一个 `design` 基线元素，不再表示可切换的降雨来源：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | string | 当前基线元素为 `design` |
| `label` | string | 基线显示名称 |
| `baseline_version_id` | UUID | 与模型顶层字段一致的唯一基线 ID |
| `filename` | string | 内置基线 INP 的文件名 |

模型列表顺序不作保证。前端应将 `LC` 显示为“老城”、`JJ` 显示为“金江”，统一展示版本列表；真实事件通过 `/api/rainfall-events?study_area=JJ` 查询，自定义降雨通过序列编辑提供。模型详情接口不包含列表专有的统计字段、`baseline_version_id` 和 `rainfall_inputs`。

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

响应：`200 OK`，返回 `ModelVersionRead[]`，按版本号降序排列。该列表包含研究区全部降雨来源及历史版本；本接口没有 `rainfall_mode` 筛选参数。前端统一展示列表，并以 `rainfall_mode` 显示来源标签；首次进入选择模型唯一 `baseline_version_id`，后续恢复该研究区已选择的版本。

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

用途：为前端调参面板返回安全、受限的对象字段目录、模拟设置，以及当前版本的完整降雨序列、统计、来源和内置事件信息。以下响应为自定义降雨派生版本的结构示例，工程对象和参数以具体版本为准。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json{
  "version_id": "da2e27c4-7dfa-4b0b-a1a4-77bce5710ff0",
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
    "duration_seconds": 900,
    "end_seconds": 900,
    "time_step_seconds": 300,
    "values_mm": [
      0.0,
      1.5,
      0.0
    ],
    "total_rainfall_mm": 1.5,
    "peak_rainfall_mm_h": 18.0,
    "series_checksum": "eacecff87b399735529094b475b777e2388f662c5641acf90a60806561876f60",
    "mode": "custom",
    "event_id": null,
    "gage_name": "RG1",
    "series_name": "Rainfall01",
    "peak_ratio": 0.4,
    "formula": "custom_series",
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
| `rainfall_options.start_seconds` | integer | 相对模拟开始的降雨偏移秒数 |
| `rainfall_options.duration_seconds` | integer | 完整序列覆盖时长，含无雨间隔；等于记录数乘记录间隔 |
| `rainfall_options.end_seconds` | integer | 序列覆盖结束，等于开始偏移加覆盖时长，不能超过模拟时长 |
| `rainfall_options.total_rainfall_mm` | number | 分段雨量合计，单位 mm |
| `rainfall_options.peak_rainfall_mm_h` | number | 分段雨量最大值乘 `3600 / time_step_seconds`，单位 mm/h |
| `rainfall_options.gage_name` | string | `[RAINGAGES]` 中使用该时间序列的雨量计名称 |
| `rainfall_options.series_name` | string | 被替换的 `[TIMESERIES]` 时间序列名称 |
| `rainfall_options.time_step_seconds` | integer | 固定记录间隔；芝加哥雨型和当前实测事件为 300 秒，自定义序列可指定正整数秒 |
| `rainfall_options.values_mm` | number[] | 完整分段雨量数组，单位 mm；每项对应一个时间间隔，包含零雨量 |
| `rainfall_options.series_checksum` | string | 序列内容、开始偏移和记录间隔共同生成的 SHA-256 校验和；与版本整个 INP 的 `checksum` 不同 |
| `rainfall_options.peak_ratio` | number | 芝加哥雨型峰现系数 0.4，其他来源不使用 |
| `rainfall_options.formula` | string | `design` 为 `runswmm_chicago`，`real` 为 `observed`，`custom` 为 `custom_series` |
| `rainfall_options.mode` | string | 当前版本降雨来源：`design`、`real` 或 `custom` |
| `rainfall_options.event_id` | string \| null | 真实降雨为 `jj_real_20260913_2d`，其他来源为 `null` |
| `rainfall_options.read_only` | boolean | `real` 时为 `true`，表示事件序列本身不可编辑或缩放；不锁定模拟参数或开始偏移，也不禁止切换来源。需要修改事件数值时应复制到 `custom` |
| `rainfall_options.real_event` | object \| null | 金江返回内置事件资料与完整序列，不论当前降雨来源；老城为 `null`。也可独立查询第 6.11 节事件接口 |

新写入序列使用 `;@RAINFALL schema=1` 注释记录来源、开始偏移、间隔、条数和事件标识。读取时兼容旧的 `;@DESIGN_RAIN schema=2`、`INTENSITY`、`VOLUME` 和历史实测 `CUMULATIVE` 格式；累计记录按相邻值差分读取。仅修改工程参数或输出步长时，不转换、不重写原有序列。

`real_event` 的 `start_datetime`、`end_datetime` 是资料原始日期；`simulation_duration_seconds=172800` 表示事件完整覆盖所需时长，`report_step_seconds=300` 是建议输出步长，均不会自动写入模型模拟参数。完整事件结构及示例见第 6.11 节。

### 6.9 创建调参版本

`POST /api/model-versions/{version_id}/versions`

用途：基于路径中的父版本应用普通对象参数、模拟设置和/或降雨条件，并创建新的不可变版本。同一次保存可在 `design`、`real`、`custom` 间切换；工程参数修改仍走原白名单流程。

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
| `simulation_options.duration_seconds` | 是 | 严格整数，默认范围 60～172800 秒；不因降雨来源而锁定，须覆盖完整降雨 |
| `simulation_options.report_step_seconds` | 是 | 严格整数，不小于路由步长、不大于模拟时长，并满足最大输出点约束 |
| `rainfall_options` | 条件必填 | 对象或 `null`；省略或为 `null` 时继承父版本序列，提供时按下表构造，未知字段被拒绝 |
| `rainfall_options.mode` | 否 | 默认 `design`，支持 `design`、`real`、`custom`，可以与父版本来源不同 |
| `rainfall_options.event_id` | `real` 必填 | 当前仅金江支持 `jj_real_20260913_2d`；其他来源省略或为 `null` |
| `rainfall_options.start_seconds` | `design`、`custom` 必填 | 非负严格整数秒；`design` 必须为 300 秒整数倍；`real` 可省略，默认为 0 |
| `rainfall_options.duration_seconds` | `design` 必填 | 严格正整数且为 300 秒整数倍；`real`、`custom` 省略或为 `null`，由序列计算 |
| `rainfall_options.total_rainfall_mm` | `design` 必填 | 严格正数且为有限值，单位 mm；`real`、`custom` 省略或为 `null`，由序列合计 |
| `rainfall_options.time_step_seconds` | `custom` 必填 | 正的严格整数秒；其他来源省略或为 `null` |
| `rainfall_options.values_mm` | `custom` 必填 | 1～10000 项分段雨量，每项为非负有限 number，允许全零；不接受布尔值或数字字符串；其他来源省略或为 `null` |

原有省略 `mode`、仅提交开始/时长/总雨量三个数值的芝加哥雨型请求仍受支持。`real` 通过事件 ID 读取受控序列，不能提交时长、总雨量、记录间隔或序列值来覆盖事件。需要编辑实测数值时改用 `custom`。

真实降雨版本只修改工程参数时省略 `rainfall_options`；修改模拟参数时仍提交完整的 `simulation_options`。后端不会替用户延长模拟时长或调整输出步长；缩短模拟到不足以覆盖继承序列时返回 `422`，可在同一次保存中显式提交更短的新降雨序列。两天模拟使用 300 秒输出步长为 576 点，满足默认 1000 点限制。

仅替换自定义降雨的完整请求示例（可用于任一研究区的当前版本）：

```json
{
  "summary": "替换为自定义降雨过程",
  "rainfall_options": {
    "mode": "custom",
    "start_seconds": 0,
    "time_step_seconds": 300,
    "values_mm": [0, 1.5, 0]
  }
}
```

在当前金江版本上应用完整真实事件，同时显式配置模拟参数：

```json
{
  "summary": "应用金江真实降雨事件",
  "simulation_options": {"duration_seconds": 172800, "report_step_seconds": 300},
  "rainfall_options": {"mode": "real", "event_id": "jj_real_20260913_2d", "start_seconds": 0}
}
```

以上请求均以路径中的当前版本为父版本，不会重置其管径、粗糙度等工程参数。请求中的 `values_mm` 只包含分段雨量；偏移和间隔通过独立字段提供。CSV/表格解析约定见 [降雨序列说明](rainfall-sequences.md)。

例如，基于已有金江真实降雨版本调整管道粗糙度，无需提交任何降雨字段（路径 UUID 为示意，需替换为当前版本 ID；对象名称以参数目录为准）：

```http
POST /api/model-versions/b4ac7257-6500-4d2b-8a65-ddf2b675d21f/versions
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

降雨生成和写入规则：

- 芝加哥雨型继续使用 `Tools/InpTools/ChicagoRainfall.py` 的样例算法：权重 `20 / (abs(t - 0.4 * T) + 8)^0.7`，`t`、`T` 以分钟计，离散缩放至总雨量，间隔 300 秒，峰现系数 0.4；不接收重现期参数。
- 芝加哥生成结果、内置实测事件和自定义数据统一转换为分段雨量（mm），由同一替换器写入 INP；雨量计使用 `VOLUME`，间隔与序列一致，英制模型写入时转换为英寸。
- 每个值覆盖 `[start_seconds + i * time_step_seconds, start_seconds + (i + 1) * time_step_seconds)`，序列外按无雨处理。覆盖结束不代表最后一个非零时刻，尾部零雨量同样计入覆盖时长。
- 根据雨量计的 `TIMESERIES` 引用替换目标名称的记录，保留其他时间序列；当前要求所有内嵌降雨雨量计引用同一个序列，否则返回 `422`。
- 序列以 12 位有效数字规范化。变化识别比较完整序列、开始偏移、间隔及来源信息；同总量、同时长但不同过程仍会创建新版本。已规范化的同一配置重复提交且没有其他修改时返回 `422`（没有发生变化）。
- 降雨替换不修改模型开始日期。模拟时长、输出步长只有在显式提交 `simulation_options` 时才改变，并沿用原有校验。

响应：`201 Created`。下面以工程参数变更展示响应结构；实际 `changes` 返回本次应用的全部变更，`change_summary` 包含来源、事件 ID 和序列校验和等版本摘要。

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

降雨替换在 `changes` 中以 `section=TIMESERIES`、`field=rainfall_series` 记录，`target` 是引用的序列名，`old_value`、`new_value` 是规范化序列的校验和字符串。客户端不要将它们转换为数值或当成逐时段雨量；完整新序列由新版本参数目录或 INP 下载获取。

可能错误：

- `404`：父版本不存在。
- `422`：字段不可编辑、对象不存在、数值越界、降雨范围超过模拟时长、试图覆盖真实事件序列、不支持的事件、非有限或负雨量、序列条数超限、存在多个不同降雨时间序列、提交内容未变化、请求体不符合约束或生成的 INP 无效。
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

### 6.11 查询内置真实降雨事件

`GET /api/rainfall-events`

用途：按研究区查询内置事件的资料信息和完整分段雨量，与模型基线和工程版本无关。此查询不会创建版本。

| 查询参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `study_area` | string | 是 | `LC` 或 `JJ`，区分大小写；其他值或缺失返回 `422` |

响应：`200 OK`，返回 `RealRainfallEvent[]`；当前 `LC` 返回 `[]`，`JJ` 返回一个事件。以下 `values_mm` 仅展示前 6 项，实际返回全部 576 项，其余汇总字段对应完整事件：

```json
[
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
    "time_step_seconds": 300,
    "values_mm": [0.2, 0.2, 0.2, 0.0, 0.2, 0.0]
  }
]
```

`start_datetime`、`end_datetime` 为原始资料日期，不用来替换模型日期。`start_seconds=0` 是事件默认开始偏移，保存时可显式设置偏移，但仍需满足完整覆盖校验。`simulation_duration_seconds` 和 `report_step_seconds` 提供完整事件所需时长和建议输出步长，不会自动改变模型参数。`values_mm` 是每个间隔的雨量（mm），不是累计值；不得把示例中截取的数组当成完整事件。

### 6.12 校验与预览降雨序列

`POST /api/rainfall/preview`

用途：根据来源配置生成或校验完整降雨序列，返回过程预览所需数据。不会创建工程版本、写入数据库/MinIO 或运行 SWMM；保存仍使用第 6.9 节的派生版本接口。

请求头：`Content-Type: application/json`。请求体 `RainfallPreviewRequest`：

```json
{
  "study_area": "JJ",
  "simulation_duration_seconds": 3600,
  "rainfall_options": {
    "mode": "custom",
    "start_seconds": 0,
    "time_step_seconds": 300,
    "values_mm": [0, 1.5, 0]
  }
}
```

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| `study_area` | 是 | `LC` 或 `JJ`，区分大小写 |
| `simulation_duration_seconds` | 是 | 正的严格整数秒，且在部署配置允许范围内，默认 60～172800；用于覆盖校验，不修改已有版本 |
| `rainfall_options` | 是 | 使用第 6.9 节完全相同的 `design`、`real`、`custom` 输入约束 |

响应：`200 OK`，返回 `RainfallPreview`。以下为上面请求的完整响应结构，校验和值以实际响应为准：

```json
{
  "mode": "custom",
  "event_id": null,
  "start_seconds": 0,
  "duration_seconds": 900,
  "end_seconds": 900,
  "time_step_seconds": 300,
  "values_mm": [0, 1.5, 0],
  "total_rainfall_mm": 1.5,
  "peak_rainfall_mm_h": 18.0,
  "series_checksum": "eacecff87b399735529094b475b777e2388f662c5641acf90a60806561876f60"
}
```

这些序列和统计字段与参数目录中的降雨字段含义相同；预览不返回雨量计名称、版本 ID 或模拟运行 ID。`design` 使用后端原有芝加哥算法，`real` 按事件 ID 读取，`custom` 使用提交的分段值。

可能错误：`422` 来源或字段不合法、老城请求金江事件、事件不存在、雨量/间隔/条数无效、模拟时长超出配置范围或不足以覆盖序列。结构校验错误的 `detail` 为数组，业务校验错误的 `detail` 为字符串，遵循第 2.4 节。

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

此接口没有 `rainfall_mode` 参数，结果可能同时包含 `design`、`real`、`custom` 及旧历史版本。前端按研究区统一展示，可通过 `version_id` 关联版本列表显示来源标签；响应本身不包含降雨类型字段。

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

三种降雨来源均使用上述 LISFLOOD 文件结构与生成规则。虚拟降雨表示 RPT 中的地表滞蓄水量，与用于驱动 SWMM 的降雨过程不同；本次降雨编辑改造未改变虚拟降雨生成算法。该版本实际应用的降雨可通过参数目录的 `values_mm` 或版本 INP 下载接口取得；内置事件原始日期和序列也可由事件查询接口获取。

可能错误：`422` 运行/版本不存在、没有成功运行或该运行没有可用虚拟降雨；`503` MinIO 不可用。

### 7.7 获取结果时间轴

`GET /api/model-versions/{version_id}/latest-result/timeline`

路径参数：`version_id`，UUID；无查询参数、无请求体。返回指定版本最新成功结果的完整时间轴、数值字段范围与单位，响应模型为 `ResultTimeline`。

以下示例仅展示首尾两项，实际 `steps` 返回全部输出时间步：

```json
{
  "version_id": "b4ac7257-6500-4d2b-8a65-ddf2b675d21f",
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
GET /api/model-versions/b4ac7257-6500-4d2b-8a65-ddf2b675d21f/latest-result/steps/575
```

不存在的时间步索引当前返回 `200`，各图层的 `features` 为空；不是 `404`。非整数索引返回 FastAPI `422`。其他可能错误：`422` 版本不存在或没有成功结果；`503` MinIO 不可用。

## 8. 推荐前端调用流程

### 8.1 初始化

1. 调用 `GET /api/models` 选择研究区，读取顶层唯一 `baseline_version_id`。
2. 调用 `GET /api/models/{model_id}/versions` 统一展示所有版本；首次进入选 V1，后续恢复该研究区已选择的版本。`rainfall_mode` 作为来源标签，不再决定独立版本根。
3. 调用所选版本的 `/layers` 和 `/editable-parameters`，读取地图、工程参数和实际降雨完整序列。
4. 按需调用 `GET /api/rainfall-events?study_area={LC或JJ}`，提供内置事件选择；自定义序列通过粘贴或前端解析 CSV 提供。
5. 调用 `GET /api/model-results?model_id={model_id}` 展示该研究区历史结果；按研究区保存当前版本和活动结果。旧版按来源分组的缓存应迁移，地图顺序和显隐可保留。

### 8.2 调参和运行

1. 未修改参数时直接运行当前版本。修改降雨来源只产生草稿，不能通过选另一个基线替代参数保存；工程参数草稿保留。
2. 使用 `POST /api/rainfall/preview` 校验并预览降雨。CSV 应先解析成固定间隔的 `values_mm`；预览成功不会创建版本，也不会修改当前模型。
3. 依据参数目录构造 `changes`、`simulation_options` 和/或 `rainfall_options`，提交到当前父版本的 `/versions`。真实事件不锁定模拟参数，需用户显式设置足以覆盖序列的模拟时长及合适的输出步长；只改工程参数时省略降雨字段。
4. 保存成功后选择响应中的新版本 ID，再调用 `/runs`。界面有未保存草稿时应阻止运行已保存版本；运行 API 本身没有草稿概念，只执行所指定版本。
5. 使用响应中的 `layers` 更新地图并重新加载该研究区的结果列表。忽略切换版本/研究区后失效的异步响应。

### 8.3 历史结果和弹窗

1. 按当前研究区展示历史结果，每个版本只展示最新成功运行；可关联版本列表标注降雨来源。
2. 用户选择版本后调用 `GET /api/model-versions/{version_id}/latest-result/layers`。
3. 用户点击结果对象后，使用图层 ID、对象 `properties.name` 和版本 ID 调用时间序列接口。
4. 图表使用 `properties.timestamp` 展示模型时间，`properties.time_index ?? properties.time` 作为索引，字段单位读取 `field_metadata`。
5. 动画和时间步选择先加载 `/latest-result/timeline`，再按索引调用 `/latest-result/steps/{time_index}`。

## 9. cURL 示例

获取模型列表：

```bash
curl http://localhost:8000/api/models
```

按来源查询最新版本（`all` 为跨来源，`custom` 可能为空，实测查询当前仅返回金江）：

```bash
curl http://localhost:8000/api/study-areas/latest-model-versions
curl "http://localhost:8000/api/study-areas/latest-model-versions?rainfall_mode=real"
curl "http://localhost:8000/api/study-areas/latest-model-versions?rainfall_mode=custom"
curl "http://localhost:8000/api/study-areas/latest-model-versions?rainfall_mode=all"
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

在当前金江版本上应用实测事件（示例使用唯一 V1 作为父版本）：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/20000000-0000-0000-0000-000000000101/versions \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "应用真实降雨",
    "simulation_options": {"duration_seconds": 172800, "report_step_seconds": 300},
    "rainfall_options": {"mode": "real", "event_id": "jj_real_20260913_2d", "start_seconds": 0}
  }'
```

随后使用响应的 `version.id` 调用运行接口，不使用固定的第二基线 ID。

查询事件及预览自定义序列（预览不保存版本）：

```bash
curl "http://localhost:8000/api/rainfall-events?study_area=JJ"
curl -X POST http://localhost:8000/api/rainfall/preview \
  -H "Content-Type: application/json" \
  -d '{
    "study_area": "JJ",
    "simulation_duration_seconds": 3600,
    "rainfall_options": {"mode": "custom", "start_seconds": 0, "time_step_seconds": 300, "values_mm": [0, 1.5, 0]}
  }'
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
