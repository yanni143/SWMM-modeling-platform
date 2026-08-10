import os
import uuid
import geopandas as gpd
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from shapely.geometry import Polygon, MultiPolygon

from Tools.PGTools.model import Road
from Tools.PGTools.shp2json import to_geojson


DB_URL = os.getenv('DB_URL')
SRID = 4549  # 与SHP原始坐标一致（EPSG:4549）

Base = declarative_base()


# SHP入库与GeoJSON转换
class RoadProcess:
    def __init__(self, dataset_id, db_url=DB_URL):
        self.dataset_id = dataset_id
        self.db_url = db_url
        # 初始化数据库连接
        self.engine = create_engine(self.db_url, connect_args={"connect_timeout": 10})
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        # 自动创建/更新表（若表已存在，需先删除旧表或手动添加Z维度）
        Base.metadata.create_all(self.engine)

    def _remove_geometry_z_dimension(self, geom):
        """
        辅助函数：移除几何数据的Z维度
        """
        if geom.has_z:
            # 遍历几何坐标，保留X、Y，丢弃Z值
            if isinstance(geom, Polygon):
                exterior = [(x, y) for x, y, z in geom.exterior.coords]
                interiors = [[(x, y) for x, y, z in ring.coords] for ring in geom.interiors]
                return Polygon(exterior, interiors)
            elif isinstance(geom, MultiPolygon):
                polygons = [self._remove_geometry_z_dimension(p) for p in geom.geoms]
                return MultiPolygon(polygons)
        return geom

    def _shp_to_db(self, shp_filepath):
        """
        读取road.shp（含Z维度），写入PostgreSQL
        """
        # 读取SHP文件（指定编码，避免中文乱码）
        gdf = gpd.read_file(shp_filepath, encoding="utf-8")

        # 检查SHP必需字段（name/height/width）
        required_fields = ["name", "height", "width"]
        missing_fields = [f for f in required_fields if f not in gdf.columns]
        if missing_fields:
            raise ValueError(f"road.shp缺少必需字段：{', '.join(missing_fields)}")

        # 移除Z维度
        gdf["geometry"] = gdf["geometry"].apply(self._remove_geometry_z_dimension)

        # 写入数据库
        db_session = self.Session()
        try:
            for _, row in gdf.iterrows():
                road = Road(
                    id=str(uuid.uuid4()),  # 生成唯一UUID（避免与SHP的id冲突）
                    dataset_id=self.dataset_id,
                    name=row["name"],
                    height=row["height"],
                    width=row["width"],
                    area=row["area"],
                    manning=0.012,
                    geometry_type=row["geometry"].geom_type,
                    geometry=WKTElement(row["geometry"].wkt, srid=SRID)
                )
                db_session.add(road)

            db_session.commit()
            print(f"成功将 {len(gdf)} 条道路数据写入数据库（表：roads）")
        except Exception as e:
            db_session.rollback()  # 出错回滚，避免脏数据
            raise Exception(f"SHP写入数据库失败：{str(e)}")
        finally:
            db_session.close()  # 确保会话关闭

    def process_road_data(self, shp_filepath, geojson_outpath):
        """
        统一入口：SHP入库 + 转换为GeoJSON（完整流程）
        :param shp_filepath: road.shp路径
        :param geojson_outpath: 生成GeoJSON的路径
        """
        # 确保GeoJSON输出目录存在
        os.makedirs(os.path.dirname(geojson_outpath), exist_ok=True)

        # SHP数据写入数据库
        self._shp_to_db(shp_filepath)
        # SHP转换为GeoJSON
        to_geojson(shp_filepath, geojson_outpath)
        print(f"成功生成GeoJSON文件：{geojson_outpath}")


# -------------------------- 3. 使用示例 --------------------------
if __name__ == "__main__":
    # 配置参数（根据实际路径修改）
    DATASET_ID = "20250301"  # 数据集ID（自定义，区分不同批次）
    SHP_FILE_PATH = "E:/SWMM_LLM/data/newshp/myroad_clip.shp"  # SHP文件路径
    GEOJSON_OUT_PATH = "E:/SWMM_LLM/data/json/road.json"  # GeoJSON输出路径

    # 执行完整流程
    try:
        processor = RoadProcess(dataset_id=DATASET_ID)
        processor.process_road_data(
            shp_filepath=SHP_FILE_PATH,
            geojson_outpath=GEOJSON_OUT_PATH
        )
    except Exception as e:
        print(f"处理失败：{str(e)}")