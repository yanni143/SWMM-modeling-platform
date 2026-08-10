import os
import uuid
import geopandas as gpd
from geoalchemy2 import WKTElement
from sqlalchemy.orm import sessionmaker
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from sqlalchemy import create_engine

from Tools.PGTools.model import Dam
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


class DamProcess:
    def __init__(self, dataset_id, db_url=DB_URL):
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
            # 处理面要素（如果有）
            elif isinstance(geom, Polygon):
                exterior = [(x, y) for x, y, z in geom.exterior.coords]
                interiors = [[(x, y) for x, y, z in ring.coords] for ring in geom.interiors]
                return Polygon(exterior, interiors)
            elif isinstance(geom, MultiPolygon):
                polygons = [self._remove_geometry_z_dimension(p) for p in geom.geoms]
                return MultiPolygon(polygons)
        return geom

    def _shp_to_db(self, shp_filepath):
        """读取dam.shp并写入数据库"""
        # 读取SHP文件
        gdf = gpd.read_file(shp_filepath, encoding="utf-8")

        # 检查必需字段
        required_fields = ["height", "width", "orient", "C", "MLimit", "length"]
        missing_fields = [f for f in required_fields if f not in gdf.columns]
        if missing_fields:
            raise ValueError(f"dam.shp缺少必需字段：{', '.join(missing_fields)}")

        # 移除Z维度，确保与表结构一致
        gdf["geometry"] = gdf["geometry"].apply(self._remove_geometry_z_dimension)

        # 写入数据库
        db_session = self.Session()
        try:
            for _, row in gdf.iterrows():
                dam = Dam(
                    id=str(uuid.uuid4()),
                    dataset_id=self.dataset_id,
                    height=row["height"],
                    width=row["width"],
                    orient=row["orient"],
                    c=row["C"],
                    moduluslimit=row["MLimit"],
                    length=row["length"],
                    manning=0.012,
                    geometry_type=row["geometry"].geom_type,
                    geometry=WKTElement(row["geometry"].wkt, srid=SRID)
                )
                db_session.add(dam)

            db_session.commit()
            print(f"成功将 {len(gdf)} 条堤坝数据写入数据库（表：dams）")
        except Exception as e:
            db_session.rollback()
            raise Exception(f"SHP写入数据库失败：{str(e)}")
        finally:
            db_session.close()

    def process_dam_data(self, shp_filepath, geojson_outpath):
        """完整处理流程：入库+生成GeoJSON"""
        os.makedirs(os.path.dirname(geojson_outpath), exist_ok=True)
        self._shp_to_db(shp_filepath)
        to_geojson(shp_filepath, geojson_outpath)
        print(f"成功生成GeoJSON文件：{geojson_outpath}")


# -------------------------- 使用示例 --------------------------
if __name__ == "__main__":
    DATASET_ID = "20250301"
    SHP_FILE_PATH = "E:/SWMM_LLM/data/newshp/mydam.shp"
    GEOJSON_OUT_PATH = "E:/SWMM_LLM/data/json/dam.json"

    try:
        processor = DamProcess(dataset_id=DATASET_ID)
        processor.process_dam_data(
            shp_filepath=SHP_FILE_PATH,
            geojson_outpath=GEOJSON_OUT_PATH
        )
    except Exception as e:
        print(f"处理失败：{str(e)}")
