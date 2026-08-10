import os
import traceback
import uuid
import geopandas as gpd
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import create_engine, Column, String, Double, Float, select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import sessionmaker
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString

# 注释掉重复的模型定义（避免冲突）
# from Tools.PGTools.model import Pipe_Subcatchment
from Tools.PGTools.shp2json import to_geojson

DB_URL = os.getenv('DB_URL')
SRID = 4549

# 解决SQLAlchemy 2.0兼容性问题
try:
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()


class Pipe_Subcatchment(Base):
    __tablename__ = 'pipes_subcatchments'

    id = Column(String(50), primary_key=True)
    dataset_id = Column(String(50))
    name = Column(String(50), unique=True)
    outid = Column(String(50))
    area = Column(Double)
    imperv = Column(Float)
    width = Column(Float)
    slope = Column(Float)
    n_imperv = Column(Float, nullable=True)
    n_perv = Column(Float, nullable=True)
    maxrate = Column(Float)
    minrate = Column(Float)
    decay = Column(Float)
    drytime = Column(Float, nullable=True)
    maxinf = Column(Float, nullable=True)
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=SRID))


class SubcatchmentProcess:
    def __init__(self, dataset_id, db_url):
        self.dataset_id = dataset_id
        self.db_url = db_url
        # 初始化数据库连接
        self.engine = create_engine(self.db_url, connect_args={"connect_timeout": 10})
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        # 自动创建表（如果不存在）
        Base.metadata.create_all(self.engine)

    def _remove_geometry_z_dimension(self, geom):
        """移除几何数据的Z维度，适配2D表结构"""
        if geom.has_z:
            if isinstance(geom, (LineString, MultiLineString)):
                # 处理线要素的Z维度
                if isinstance(geom, LineString):
                    return LineString([(x, y) for x, y, z in geom.coords])
                elif isinstance(geom, MultiLineString):
                    lines = [LineString([(x, y) for x, y, z in line.coords]) for line in geom.geoms]
                    return MultiLineString(lines)
            # 处理面要素
            elif isinstance(geom, Polygon):
                exterior = [(x, y) for x, y, z in geom.exterior.coords]
                interiors = [[(x, y) for x, y, z in ring.coords] for ring in geom.interiors]
                return Polygon(exterior, interiors)
            elif isinstance(geom, MultiPolygon):
                polygons = [self._remove_geometry_z_dimension(p) for p in geom.geoms]
                return MultiPolygon(polygons)
        return geom

    def _get_outid_value(self, row):
        """
        从OutName_Ju和OutName_La中选择非空值作为outid
        """
        if 'OutName_Ju' in row and row['OutName_Ju'] not in [None, '', ' ']:
            return str(row['OutName_Ju']).strip()
        elif 'OutName_La' in row and row['OutName_La'] not in [None, '', ' ']:
            return str(row['OutName_La']).strip()
        else:
            return ''

    def _check_duplicate_names(self, names):
        """检查数据库中已存在的name，返回重复的name列表"""
        db_session = self.Session()
        try:
            # 查询数据库中已存在的name
            existing_names = db_session.execute(
                select(Pipe_Subcatchment.name).where(Pipe_Subcatchment.name.in_(names))
            ).scalars().all()
            existing_names = [name.strip() for name in existing_names]
            return existing_names
        finally:
            db_session.close()

    def _shp_to_db(self, shp_filepath):
        """读取subcatchment.shp并写入数据库（修复唯一键冲突捕获）"""
        # 读取SHP文件
        gdf = gpd.read_file(shp_filepath, encoding="utf-8")

        # 检查必需字段
        required_fields = ["Id", "Imperv_Per", "Slope", "width"]
        missing_fields = [f for f in required_fields if f not in gdf.columns]
        if missing_fields:
            raise ValueError(f"subcatchment.shp缺少必需字段：{', '.join(missing_fields)}")

        # 移除Z维度，确保与表结构一致
        gdf["geometry"] = gdf["geometry"].apply(self._remove_geometry_z_dimension)

        # ========== 核心修复1：提前检查重复name ==========
        # 提取所有待插入的name并去重
        shp_names = [str(row["Id"]).strip() for _, row in gdf.iterrows()]
        # 检查数据库中已存在的name
        duplicate_names = self._check_duplicate_names(shp_names)

        if duplicate_names:
            print(f"⚠️ 检测到 {len(duplicate_names)} 个重复的name字段，将跳过这些记录")
            # 过滤掉重复的行
            gdf = gdf[~gdf["Id"].astype(str).str.strip().isin(duplicate_names)]
            if len(gdf) == 0:
                print("❌ 所有数据均为重复，无需写入")
                return

        # 写入数据库
        db_session = self.Session()
        inserted_count = 0
        failed_records = []

        try:
            for _, row in gdf.iterrows():
                try:
                    outid_value = self._get_outid_value(row)
                    sub_name = str(row["Id"]).strip()

                    subcatchment = Pipe_Subcatchment(
                        id=str(uuid.uuid4()),
                        dataset_id=self.dataset_id,
                        name=sub_name,
                        outid=outid_value,
                        area=row["Area"],
                        imperv=row["Imperv_Per"],
                        width=row["width"],
                        slope=row["Slope"],
                        n_imperv=None,
                        n_perv=None,
                        maxrate=0.5,
                        minrate=0.2,
                        decay=2.0,
                        drytime=None,
                        maxinf=None,
                        geometry=WKTElement(row["geometry"].wkt, srid=SRID)
                    )
                    db_session.add(subcatchment)
                    inserted_count += 1

                    # 每100条提交一次（避免缓存过大，也便于捕获单批次异常）
                    if inserted_count % 100 == 0:
                        db_session.commit()
                        print(f"✅ 已批量写入 {inserted_count} 条数据")

                except Exception as e:
                    failed_name = str(row["Id"]).strip()
                    failed_records.append(failed_name)
                    print(f"❌ 单条记录写入失败（name={failed_name}）：{str(e)}")
                    db_session.rollback()
                    continue

            # 提交剩余数据
            db_session.commit()
            print(f"✅ 成功将 {inserted_count} 条子汇水区数据写入数据库（表：pipes_subcatchments）")

            if failed_records:
                print(f"⚠️ 总计 {len(failed_records)} 条记录写入失败，失败name：{failed_records}")

        # ========== 核心修复2：精准捕获唯一键冲突 ==========
        except IntegrityError as e:
            db_session.rollback()
            if "unique constraint" in str(e).lower() and "name" in str(e).lower():
                print(f"❌ 写入失败：提交时检测到唯一键冲突（name字段重复），已回滚")
            else:
                print(f"❌ 数据完整性错误：{str(e)}")
            traceback.print_exc()
            raise
        except SQLAlchemyError as e:
            db_session.rollback()
            print(f"❌ 数据库写入失败：{str(e)}")
            traceback.print_exc()
            raise
        except Exception as e:
            db_session.rollback()
            print(f"❌ 数据写入异常：{str(e)}")
            traceback.print_exc()
            raise
        finally:
            db_session.close()

    def process_subcatchment_data(self, shp_filepath, geojson_outpath):
        """完整处理流程：入库+生成GeoJSON"""
        os.makedirs(os.path.dirname(geojson_outpath), exist_ok=True)
        self._shp_to_db(shp_filepath)
        to_geojson(shp_filepath, geojson_outpath)
        print(f"成功生成GeoJSON文件：{geojson_outpath}")


def shp2pg_sub(dataset_id, subcatchments_path, db_url):
    processor = SubcatchmentProcess(dataset_id, db_url)
    geojson_outpath = "E:/SWMM_LLM/data/json/subcatchment.json"
    processor.process_subcatchment_data(subcatchments_path, geojson_outpath)

# # -------------------------- 使用示例 --------------------------
# if __name__ == "__main__":
#     DATASET_ID = "20250301"
#     SHP_FILE_PATH = "E:/SWMM_LLM/data/newshp/subcatchment.shp"
#     GEOJSON_OUT_PATH = "E:/SWMM_LLM/data/json/subcatchment.json"
#
#     try:
#         processor = SubcatchmentProcess(dataset_id=DATASET_ID, db_url=DB_URL)
#         processor.process_subcatchment_data(
#             shp_filepath=SHP_FILE_PATH,
#             geojson_outpath=GEOJSON_OUT_PATH
#         )
#     except Exception as e:
#         print(f"处理失败：{str(e)}")