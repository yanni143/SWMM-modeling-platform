# SWMM 后端 API 使用指南

本文档整理当前后端实际注册的全部 HTTP 接口，包括接口用途、请求格式、响应格式和常见错误。接口实现以 `Controller/model_routes.py`、`Controller/run_routes.py` 和 `Controller/controller.py` 为准。

## 1. 系统约束

- 系统是固定研究区演示系统，后端启动时会初始化一个内置 SWMM 模型。
- 不提供用户上传 INP 文件的接口。
- 参数调整不会覆盖原版本，而是以指定版本为父版本创建一个新版本。
- 同一版本允许执行多次模拟。数据库和 MinIO 保留每次运行，但面向用户的历史结果列表只展示每个版本最新一次成功运行。
- 地图结果接口只返回最后一个模拟时间步，避免同一几何重复压盖。
- 时间序列接口返回指定对象的全部时间步，供结果弹窗和图表使用。
- 当前接口没有鉴权机制。

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
- ID：标准 UUID 字符串，例如 `00000000-0000-0000-0000-000000000101`
- 时间：ISO 8601 字符串，例如 `2026-08-11T05:59:30.123456Z`
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
      "loc": ["path", "version_id"],
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
| `GET` | `/api/runs/{run_id}/layers` | 按具体运行 ID 获取地图结果图层 |

## 4. 通用数据结构

### 4.1 工程版本 `ModelVersionRead`

```json
{
  "id": "00000000-0000-0000-0000-000000000101",
  "model_id": "00000000-0000-0000-0000-000000000001",
  "parent_version_id": null,
  "version": 1,
  "checksum": "7d8f...",
  "size_bytes": 872653,
  "change_summary": null,
  "created_by": "system",
  "created_at": "2026-08-11T05:30:00Z"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 版本 ID |
| `model_id` | UUID | 所属模型 ID |
| `parent_version_id` | UUID \| null | 父版本；初始版本为 `null` |
| `version` | integer | 用户可见版本号，如 `1`、`2` |
| `checksum` | string \| null | MinIO 对象校验值 |
| `size_bytes` | integer \| null | INP 文件大小 |
| `change_summary` | object \| null | 本版本的修改摘要 |
| `created_by` | string \| null | 创建者 |
| `created_at` | datetime | 创建时间 |

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
  "time": 11
}
```

其中 `time` 是从 `0` 开始的模拟时间步索引，不是 ISO 时间。不同结果图层还包含：

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

### 6.1 获取模型列表

`GET /api/models`

用途：获取系统内置模型列表。当前演示系统通常只有一个固定研究区模型。

请求：无参数、无请求体。

响应：`200 OK`，返回 `ModelListItem[]`。

```json
[
  {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "汾湖演示研究区",
    "description": "系统内置的固定 SWMM 演示研究区",
    "status": "active",
    "created_at": "2026-08-11T05:30:00Z",
    "updated_at": "2026-08-11T05:30:00Z",
    "version_count": 3,
    "latest_version": 3
  }
]
```

`latest_version` 在没有版本时可能为 `null`。

### 6.2 获取模型详情

`GET /api/models/{model_id}`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | UUID | 模型 ID |

响应：`200 OK`。

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "name": "汾湖演示研究区",
  "description": "系统内置的固定 SWMM 演示研究区",
  "status": "active",
  "created_at": "2026-08-11T05:30:00Z",
  "updated_at": "2026-08-11T05:30:00Z"
}
```

可能错误：`404` 模型不存在；`422` UUID 格式错误；`503` MinIO 不可用；`500` 工程服务异常。

### 6.3 获取模型版本列表

`GET /api/models/{model_id}/versions`

路径参数：`model_id`，UUID。

响应：`200 OK`，返回 `ModelVersionRead[]`。通常按服务定义的版本顺序返回。

```json
[
  {
    "id": "00000000-0000-0000-0000-000000000101",
    "model_id": "00000000-0000-0000-0000-000000000001",
    "parent_version_id": null,
    "version": 1,
    "checksum": "7d8f...",
    "size_bytes": 872653,
    "change_summary": null,
    "created_by": "system",
    "created_at": "2026-08-11T05:30:00Z"
  }
]
```

可能错误：`404` 模型不存在；`422` UUID 格式错误；`503` MinIO 不可用；`500` 工程服务异常。

### 6.4 获取版本 INP section 摘要

`GET /api/model-versions/{version_id}/sections`

用途：列出 INP 文件中的全部 section，以及每个 section 的记录数、可编辑状态和字段定义。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "00000000-0000-0000-0000-000000000101",
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

### 6.5 获取单个 INP section

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
  "version_id": "00000000-0000-0000-0000-000000000101",
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

### 6.6 获取原始 INP 地图图层

`GET /api/model-versions/{version_id}/layers`

用途：把 `[POLYGONS]`、`[COORDINATES]`、`[VERTICES]` 等空间 section 转成地图可直接使用的 GeoJSON。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "00000000-0000-0000-0000-000000000101",
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
              "coordinates": [[[120.84, 31.03], [120.85, 31.03], [120.84, 31.03]]]
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

### 6.7 获取可调参数目录

`GET /api/model-versions/{version_id}/editable-parameters`

用途：为前端调参面板返回安全、受限的对象和字段目录。

路径参数：`version_id`，UUID。

响应：`200 OK`。

```json
{
  "version_id": "00000000-0000-0000-0000-000000000101",
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
              "key": "SUBCATCHMENTS.area",
              "section": "SUBCATCHMENTS",
              "field": "area",
              "label": "Area",
              "unit": "ha",
              "value": "1.2",
              "minimum": 0.0001,
              "maximum": 100000,
              "step": 0.1
            }
          ]
        }
      ]
    }
  ]
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

### 6.8 创建调参版本

`POST /api/model-versions/{version_id}/versions`

用途：基于路径中的父版本应用一组参数修改，并创建新的不可变版本。

请求头：

```text
Content-Type: application/json
```

路径参数：`version_id`，父版本 UUID。

请求体 `CreateAdjustedVersionRequest`：

```json
{
  "summary": "调整子汇水区不透水率与管道粗糙系数",
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
  ]
}
```

请求约束：

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| `summary` | 否 | string 或 `null`，最长 500 字符 |
| `created_by` | 否 | string 或 `null`，最长 100 字符 |
| `changes` | 是 | 1 到 5000 项 |
| `changes[].section` | 是 | string，最长 64 字符 |
| `changes[].target` | 是 | string，1 到 200 字符 |
| `changes[].field` | 是 | string，1 到 100 字符 |
| `changes[].new_value` | 是 | string，1 到 100 字符 |

响应：`201 Created`。

```json
{
  "version": {
    "id": "da2e27c4-7dfa-4b0b-a1a4-77bce5710ff0",
    "model_id": "00000000-0000-0000-0000-000000000001",
    "parent_version_id": "00000000-0000-0000-0000-000000000101",
    "version": 2,
    "checksum": "9a31...",
    "size_bytes": 872701,
    "change_summary": {
      "summary": "调整子汇水区不透水率与管道粗糙系数"
    },
    "created_by": "demo-user",
    "created_at": "2026-08-11T06:00:00Z"
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
- `422`：字段不可编辑、对象不存在、数值越界、请求体不符合约束或生成的 INP 无效。
- `503`：MinIO 不可用。

### 6.9 下载版本 INP

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

用途：下载版本 INP、调用 SWMM、解析 OUT 文件、保存输入/输出/报告/可视化产物并返回地图结果。

路径参数：`version_id`，UUID。无请求体。

当前接口是同步接口：HTTP 请求会等待模拟和结果解析完成。

响应：`200 OK`。

```json
{
  "run_id": "c8b121e0-264f-4b2f-8179-8b230c4a00ae",
  "model_version_id": "00000000-0000-0000-0000-000000000101",
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
              "time": 11,
              "rain": 0.0,
              "runoff": 0.0021,
              "infilt": 0.0,
              "evap": 0.0,
              "snow": 0.0,
              "gw_flow": null,
              "soil_moist": null
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

可能错误：`422` 版本不存在、运行失败或 OUT 未生成；`503` MinIO 不可用；`500` 未分类运行服务错误。

### 7.2 获取历史结果摘要

`GET /api/model-results`

用途：按工程版本聚合成功运行。每个版本只返回最新一次成功运行，用于历史结果下拉框。

请求：无参数、无请求体。

响应：`200 OK`。

```json
[
  {
    "version_id": "00000000-0000-0000-0000-000000000101",
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
  "version_id": "00000000-0000-0000-0000-000000000101",
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

响应中的每个对象只保留最后一个 `time`。完整时序应通过下一接口查询。

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
GET /api/model-versions/00000000-0000-0000-0000-000000000101/latest-result/timeseries?layer_id=result-subcatchments&feature_name=S1
```

允许的 `layer_id`：

- `result-subcatchments`
- `result-conduits`
- `result-nodes`

响应：`200 OK`，返回 GeoJSON FeatureCollection。Feature 按 `properties.time` 升序排列。

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
        "time": 0,
        "rain": 0.0,
        "runoff": 0.0,
        "infilt": 0.0,
        "evap": 0.0,
        "snow": 0.0,
        "gw_flow": null,
        "soil_moist": null
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
        "time": 1,
        "rain": 1.3,
        "runoff": 0.12,
        "infilt": 0.4,
        "evap": 0.0,
        "snow": 0.0,
        "gw_flow": null,
        "soil_moist": null
      }
    }
  ]
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

## 8. 推荐前端调用流程

### 8.1 初始化

1. 调用 `GET /api/models` 获取固定模型。
2. 调用 `GET /api/models/{model_id}/versions` 获取版本列表。
3. 调用 `GET /api/model-versions/{version_id}/layers` 加载原始 INP 地图。
4. 调用 `GET /api/model-versions/{version_id}/editable-parameters` 初始化调参面板。
5. 调用 `GET /api/model-results` 恢复有成功结果的版本列表。

### 8.2 调参和运行

1. 根据可调参数目录构造 `changes`。
2. 调用 `POST /api/model-versions/{parent_version_id}/versions` 创建新版本。
3. 调用 `POST /api/model-versions/{new_version_id}/runs` 运行新版本。
4. 使用响应中的最后时间步 `layers` 更新地图。

### 8.3 历史结果和弹窗

1. 使用 `GET /api/model-results` 展示每个版本的最新成功结果。
2. 用户选择版本后调用 `GET /api/model-versions/{version_id}/latest-result/layers`。
3. 用户点击结果对象后，使用图层 ID、对象 `properties.name` 和版本 ID 调用时间序列接口。
4. 参数图表使用返回 Feature 的 `properties.time` 作为横轴索引，对应结果字段作为纵轴。

## 9. cURL 示例

获取模型列表：

```bash
curl http://localhost:8000/api/models
```

创建调参版本：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/00000000-0000-0000-0000-000000000101/versions \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "调整 S1 不透水率",
    "created_by": "demo-user",
    "changes": [
      {
        "section": "SUBCATCHMENTS",
        "target": "S1",
        "field": "imperv",
        "new_value": "42"
      }
    ]
  }'
```

运行版本：

```bash
curl -X POST \
  http://localhost:8000/api/model-versions/00000000-0000-0000-0000-000000000101/runs
```

查询时间序列：

```bash
curl "http://localhost:8000/api/model-versions/00000000-0000-0000-0000-000000000101/latest-result/timeseries?layer_id=result-subcatchments&feature_name=S1"
```

下载 INP：

```bash
curl -OJ \
  http://localhost:8000/api/model-versions/00000000-0000-0000-0000-000000000101/download
```
