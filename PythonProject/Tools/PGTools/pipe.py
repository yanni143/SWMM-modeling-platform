import os
import traceback
from dotenv import load_dotenv
import geopandas as gpd
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Double, text
from sqlalchemy.exc import SQLAlchemyError
from geoalchemy2 import Geometry

from Tools.PGTools.shp2json import to_geojson


# 1. 环境配置与数据库连接
def load_environment():
    """加载环境变量, 读取数据库配置"""
    load_dotenv()
    return {
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_PORT": os.getenv("DB_PORT"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASS": os.getenv("DB_PASS"),
        "DB_NAME": os.getenv("DB_NAME"),
        "SRID": int(os.getenv("SRID", 4549))  # 坐标系SRID（CGCS2000 3-degree Gauss-Kruger CM 120E，WGS84为4326）
    }


def create_db_connection(db_url):
    """创建PostgreSQL数据库连接, 支持PostGIS"""
    try:
        engine = create_engine(db_url)
        # 测试连接并验证PostGIS是否启用
        with engine.connect() as conn:
            postgis_check = conn.execute(text("SELECT PostGIS_version();")).scalar()
            if not postgis_check:
                raise Exception("PostGIS扩展未启用，请先在PostgreSQL中安装PostGIS")
        print(f"✅ 数据库连接成功（PostGIS版本：{postgis_check[:20]}...）")
        return engine
    except SQLAlchemyError as e:
        print(f"❌ 数据库连接失败：{str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"❌ 初始化数据库连接异常：{str(e)}")
        traceback.print_exc()
        raise


# 2. 数据库表结构初始化
def init_pipe_tables(engine, env_config):
    """创建管网相关表结构（节点表、出水口表、管段表）"""
    metadata = MetaData()
    srid = env_config["SRID"]

    # 1. 节点表（Pipes_Junctions：普通节点）
    Table(
        "pipes_junctions", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True, comment="节点主键ID（自增）"),
        Column("dataset_id", String(50), nullable=False, comment="数据集标识"),
        Column("name", String(50), nullable=False, unique=True, comment="节点名称"),
        Column("elev", Double, nullable=False, comment="节点内底标高"),
        Column("ymax", Double, nullable=False, comment="节点最大深度"),
        Column("y0", Double, nullable=False, comment="节点初始水深"),
        Column("ysur", Double, nullable=False, comment="节点超载水深"),
        Column("apond", Double, nullable=True, comment="积水面积"),
        Column("geometry", Geometry("POINT", srid=srid), nullable=False, comment="节点地理坐标"),
        comment="管网基础数据-普通节点表"
    )

    # 2. 出水口表（Pipes_Outfalls：特殊节点）
    Table(
        "pipes_outfalls", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True, comment="出水口主键ID（自增）"),
        Column("dataset_id", String(50), nullable=False, comment="数据集标识"),
        Column("name", String(50), nullable=False, unique=True, comment="出水口名称"),
        Column("elev", Double, nullable=False, comment="出水口内底标高"),
        Column("type", String(50), nullable=False, comment="出水口类型"),
        Column("stage", Double, nullable=True),
        Column("gated", String(50), nullable=True),
        Column("routeto", String(50), nullable=True),
        Column("geometry", Geometry("POINT", srid=srid), nullable=False, comment="出水口地理坐标"),
        comment="管网基础数据-出水口表"
    )

    # 3. 管段表（Pipes_Conduits：线要素）
    Table(
        "pipes_conduits", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True, comment="管段主键ID（自增）"),
        Column("dataset_id", String(50), nullable=False, comment="数据集标识"),
        Column("name", String(50), nullable=False, unique=True, comment="管段名称"),
        Column("node1", String(50), nullable=False, comment="上游节点"),
        Column("node2", String(50), nullable=False, comment="下游节点"),
        Column("length", Double, nullable=False, comment="管段长度"),
        Column("n", Double, nullable=False, comment="粗糙系数"),
        Column("z1", Double, nullable=False, comment="上游节点内底标高超过管渠内底的上游端偏移"),
        Column("z2", Double, nullable=False, comment="下游节点内底标高超过管渠内底的下游端偏移"),
        Column("q0", Double, nullable=False, comment="管段初始流量"),
        Column("qmax", Double, nullable=True, comment="管段最大允许流量"),
        Column("shape", String(50), nullable=False, comment="管段横截面形状"),
        Column("geom1", Double, nullable=False, comment="管段管径（直径）"),
        Column("geometry", Geometry("LINESTRING", srid=srid), nullable=False, comment="管段地理坐标"),
        comment="管网基础数据-管段表"
    )

    # 创建表（若表已存在则跳过）
    try:
        metadata.create_all(engine)
        print("✅ 基础管网表（Pipes_Junctions/Pipes_Outfalls/Pipes_Conduits）初始化完成")
    except SQLAlchemyError as e:
        print(f"❌ 创建表失败：{str(e)}")
        traceback.print_exc()
        raise


# 3. Shapefile读取、字段映射与清洗
def read_shapefile(shp_path, target_table, env_config):
    """读取Shapefile并进行数据清洗和字段映射"""
    # 定义字段映射关系，格式：{"数据库字段名": "Shapefile字段名"}
    field_mapping = {
        "Pipes_Junctions": {
            "name": "Name",  # 节点名称
            "elev": "InvertEL",  # 内底标高
            "ymax": "MaxDepth",  # 最大深度
            "y0": "InitDepth",  # 初始水深
            "ysur": "SurChargeD",  # 超载水深
            "apond": "PondedArea"  # 积水面积
        },
        "Pipes_Outfalls": {
            "name": "Name",  # 出水口名称
            "elev": "InvertEL",  # 内底标高
            "type": "Type",  # 类型
            "stage": "FixedStage",
        },
        "Pipes_Conduits": {
            "name": "Name",  # 管段名称
            "node1": "InletNode",
            "node2": "OutletNode",
            "length": "Length",
            "n": "Roughness",
            "z1": "InOffset",
            "z2": "OutOffset",
            "q0": "InitFlow",
            "qmax": "MaxFlow",
            "shape": "Type",
            "geom1": "GJ",
        }
    }

    # 获取当前表对应的映射关系
    current_mapping = field_mapping[target_table]

    # 1. 读取Shapefile
    try:
        # 根据实际编码调整（GBK适用于中文Windows环境，UTF-8适用于其他环境）
        gdf = gpd.read_file(shp_path, encoding="gbk")
        print(f"\n📊 成功读取Shapefile：{shp_path}")
        print(f"   - 数据条数：{len(gdf)}")
        print(f"   - 原始字段列表：{list(gdf.columns)}")
        print(f"   - 原始坐标系：{gdf.crs}")
    except Exception as e:
        print(f"❌ 读取Shapefile失败：{str(e)}")
        traceback.print_exc()
        raise

    # 2. 检查Shapefile是否包含映射所需的所有字段
    required_shp_fields = list(current_mapping.values())
    missing_fields = [f for f in required_shp_fields if f not in gdf.columns]
    if missing_fields:
        raise Exception(
            f"Shapefile缺少必要字段！目标表{target_table}需要：{required_shp_fields}，但缺少：{missing_fields}\n"
            f"请检查字段映射是否正确，或Shapefile属性表是否有误。"
        )

    # 3. 执行字段映射：将Shapefile字段重命名为数据库字段
    gdf_mapped = gdf.copy()
    rename_mapping = {v: k for k, v in current_mapping.items()}
    gdf_mapped = gdf_mapped.rename(columns=rename_mapping)

    # 4. 坐标系转换（统一到目标SRID）
    if gdf_mapped.crs is None:
        raise Exception(f"Shapefile {shp_path} 未定义坐标系，请检查文件或手动指定")
    if gdf_mapped.crs.to_epsg() != env_config["SRID"]:
        print(f"🔄 将坐标系从 {gdf_mapped.crs.to_epsg()} 转换为 {env_config['SRID']}")
        gdf_mapped = gdf_mapped.to_crs(epsg=env_config["SRID"])

    # 5. 几何类型校验（确保与目标表匹配）
    geom_type_map = {
        "Pipes_Junctions": "Point",
        "Pipes_Outfalls": "Point",
        "Pipes_Conduits": "LineString"
    }
    required_geom_type = geom_type_map[target_table]
    if not all(gdf_mapped.geometry.type == required_geom_type):
        invalid_count = sum(gdf_mapped.geometry.type != required_geom_type)
        raise Exception(
            f"Shapefile几何类型不匹配！目标表{target_table}需{required_geom_type}类型，"
            f"但存在{invalid_count}条非{required_geom_type}数据"
        )

    # 6. 数据去重（按name字段去重，避免重复写入）
    duplicate_names = gdf_mapped[gdf_mapped.duplicated(subset=["name"], keep=False)]["name"].unique()
    if len(duplicate_names) > 0:
        print(f"⚠️ 发现重复name字段：{duplicate_names}，将保留第一条，删除其余重复数据")
        gdf_mapped = gdf_mapped.drop_duplicates(subset=["name"], keep="first")

    print(f"   - 映射后字段列表：{list(gdf_mapped.columns)}")
    return gdf_mapped


# 4. 数据批量写入数据库
def batch_write_to_db(engine, gdf, target_table, dataset_id):
    """将清洗后的GeoDataFrame批量写入数据库，缺失字段自动设为空"""
    # 1. 添加dataset_id字段（关联数据集）
    gdf["dataset_id"] = dataset_id

    # 2. 定义各表需要的数据库字段
    table_fields = {
        "Pipes_Junctions": [
            "dataset_id", "name", "elev", "ymax", "y0", "ysur", "apond", "geometry"
        ],
        "Pipes_Outfalls": [
            "dataset_id", "name", "elev", "type", "stage", "gated", "routeto", "geometry"
        ],
        "Pipes_Conduits": [
            "dataset_id", "name", "node1", "node2", "length", "n", "z1", "z2", "q0", "qmax", "shape", "geom1", "geometry"
        ]
    }
    # 获取当前表需要的字段
    required_fields = table_fields[target_table]
    print(f"   - 数据库表需包含字段：{required_fields}")

    # --------------------------
    # 核心功能：检查缺失字段并自动设空
    # --------------------------
    # 找出"数据库需要但Shapefile没有"的字段
    missing_db_fields = [field for field in required_fields if field not in gdf.columns]
    if missing_db_fields:
        print(f"   ⚠️ 发现{len(missing_db_fields)}个缺失字段：{missing_db_fields}，自动设为空值")
        # 为缺失字段填充空值（None适配PostgreSQL的NULL，兼容字符串/数值字段）
        for field in missing_db_fields:
            gdf[field] = None

    # 3. 过滤字段：只保留数据库需要的字段（排除Shapefile多余字段）
    gdf_filtered = gdf[required_fields].copy()
    print(f"   - 过滤后待写入字段：{list(gdf_filtered.columns)}")

    # 4. 批量写入数据库（核心修复：统一表名大小写，数据库表是小写）
    try:
        gdf_filtered.to_postgis(
            name=target_table.lower(),  # 统一转为小写（如Pipes_Outfalls → pipes_outfalls）
            con=engine,
            if_exists="append",  # 追加模式（覆盖用"replace"，谨慎使用）
            index=False,  # 不写入DataFrame索引
            dtype={"geometry": Geometry(
                geometry_type=gdf_filtered.geometry.type.unique()[0],
                srid=engine.srid
            )}
        )
        print(f"✅ 成功写入{target_table.lower()}表：{len(gdf_filtered)}条数据（dataset_id：{dataset_id}）")
    except SQLAlchemyError as e:
        # 捕获唯一键冲突（name字段重复）
        if "unique constraint" in str(e).lower() and "name" in str(e).lower():
            print(f"❌ 写入失败：存在重复的name字段（{target_table.lower()}表的name字段唯一），请检查数据")
        else:
            print(f"❌ 批量写入数据库失败：{str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"❌ 数据写入异常：{str(e)}")
        traceback.print_exc()
        raise


# 5. 生成可视化geojson
def shapefile_to_geojson(shp_filepath, geojson_outpath):
    """生成GeoJSON"""
    to_geojson(shp_filepath, geojson_outpath)
    print(f"成功生成GeoJSON文件：{geojson_outpath}")


# 主函数
def shp2pg_main(dataset_id, junctions_path, outfalls_path, conduits_path, db_url):
    CONFIG = {
        "dataset_id": dataset_id,  # 数据集标识（可自定义，用于区分不同批次数据）
        "shapefile_paths": {
            "Pipes_Junctions": junctions_path,  # 普通节点Shapefile路径
            "Pipes_Outfalls": outfalls_path,  # 出水口Shapefile路径
            "Pipes_Conduits": conduits_path   # 管段Shapefile路径
        }
    }

    try:
        # 步骤1：加载环境配置与创建数据库连接
        env_config = load_environment()
        engine = create_db_connection(db_url)
        # 设置引擎的SRID属性（供后续使用）
        engine.srid = env_config["SRID"]

        # 步骤2：初始化基础管网表（若表不存在则创建）
        init_pipe_tables(engine, env_config)

        # 步骤3：循环读取各类Shapefile并写入数据库
        for target_table, shp_path in CONFIG["shapefile_paths"].items():
            if not os.path.exists(shp_path):
                print(f"⚠️ Shapefile文件不存在：{shp_path}，跳过该表写入")
                continue
            # 读取并清洗Shapefile
            gdf = read_shapefile(shp_path, target_table, env_config)
            # 批量写入数据库
            batch_write_to_db(engine, gdf, target_table, CONFIG["dataset_id"])

        print("\n🎉 所有基础管网数据写入完成！")

        # 4:shp2geojson
        shapefile_to_geojson(junctions_path, "E:/SWMM_LLM/data/json/pipes_junction.json")
        shapefile_to_geojson(outfalls_path, "E:/SWMM_LLM/data/json/pipes_outfall.json")
        shapefile_to_geojson(conduits_path, "E:/SWMM_LLM/data/json/pipes_conduit.json")

    except Exception as e:
        print(f"\n❌ 程序执行失败：{str(e)}")
        traceback.print_exc()


# shp2pg_main(dataset_id, junctions_path, outfalls_path, conduits_path, db_url)
