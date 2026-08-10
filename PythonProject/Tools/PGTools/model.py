from sqlalchemy import Column, Integer, String, Float, BigInteger, Double
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, REAL
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape, to_shape
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from marshmallow import fields, pre_load, post_dump
import json


Base = declarative_base()
srid = 4549

# 基础地理数据（6）
class Build(Base):
    __tablename__ = 'builds'

    id = Column(String(50), primary_key=True)  # 主键（UUID）
    dataset_id = Column(String(50), nullable=False)
    name = Column(String(50))
    height = Column(Float)
    area = Column(Double)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


class Lake(Base):
    __tablename__ = 'lakes'

    id = Column(String(50), primary_key=True)  # 主键（UUID）
    dataset_id = Column(String(50), nullable=False)
    name = Column(String(50))
    surface_height = Column(Float)
    area = Column(Double)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


class Road(Base):
    __tablename__ = 'roads'

    id = Column(String(50), primary_key=True)  # 主键（UUID）
    dataset_id = Column(String(50), nullable=False)
    name = Column(String(50))
    height = Column(Float)
    width = Column(Float)
    area = Column(Double)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


class River(Base):
    __tablename__ = 'rivers'

    id = Column(String(50), primary_key=True)
    dataset_id = Column(String(50))
    name = Column(String(50))
    bed_height = Column(Float)
    width = Column(Float)
    length = Column(Float)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


class Land(Base):
    __tablename__ = 'lands'

    id = Column(String(50), primary_key=True)
    dataset_id = Column(String(50))
    landuse = Column(String(50))
    area = Column(Double)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


class Dam(Base):
    __tablename__ = 'dams'

    id = Column(String(50), primary_key=True)
    dataset_id = Column(String(50))
    height = Column(Float)
    width = Column(Float)
    orient = Column(String(50))
    c = Column(Float)
    moduluslimit = Column(Float)
    length = Column(Float)
    manning = Column(Float)
    geometry_type = Column(String(50))
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=srid))


# 管网及汇水区数据（4）
class Pipe_Junction(Base):
    # __tablename__属性指定了数据库中对应的表名
    __tablename__ = 'pipes_junctions'

    id = Column(Integer, primary_key=True, autoincrement=True, comment="节点主键ID（自增）")
    dataset_id = Column(String(50), nullable=False, comment="数据集标识")
    name = Column(String(50), nullable=False, unique=True, comment="节点名称")
    elev = Column(Double, nullable=False, comment="节点内底标高")
    ymax = Column(Double, nullable=False, comment="节点最大深度")
    y0 = Column(Double, nullable=False, comment="节点初始水深")
    ysur = Column(Double, nullable=False, comment="节点超载水深")
    apond = Column(Double, nullable=True, comment="积水面积")
    geometry = Column(Geometry(geometry_type='POINT', srid=srid), nullable=False, comment="节点地理坐标")


class Pipe_Outfall(Base):
    # __tablename__属性指定了数据库中对应的表名
    __tablename__ = 'pipes_outfalls'

    id = Column(Integer, primary_key=True, autoincrement=True, comment="出水口主键ID（自增）")
    dataset_id = Column(String(50), nullable=False, comment="数据集标识")
    name = Column(String(50), nullable=False, unique=True, comment="出水口名称")
    elev = Column(Float, nullable=False, comment="出水口内底标高")
    type = Column(String(50), nullable=False, comment="出水口类型")
    stage = Column(Float, nullable=True, comment="水位")
    gated = Column(String(50), nullable=True, comment="闸门状态")
    routeto = Column(String(50), nullable=True, comment="排放去向")
    geometry = Column(Geometry(geometry_type='POINT', srid=srid), nullable=False, comment="出水口地理坐标")


class Pipe_Conduit(Base):
    # __tablename__属性指定了数据库中对应的表名
    __tablename__ = 'pipes_conduits'

    id = Column(Integer, primary_key=True, autoincrement=True, comment="管段主键ID（自增）")
    dataset_id = Column(String(50), nullable=False, comment="数据集标识")
    name = Column(String(50), nullable=False, unique=True, comment="管段名称")
    node1 = Column(String(50), nullable=False, comment="上游节点")
    node2 = Column(String(50), nullable=False, comment="下游节点")
    length = Column(Double, nullable=False, comment="管段长度")
    n = Column(Double, nullable=False, comment="粗糙系数")
    z1 = Column(Double, nullable=False, comment="上游偏移标高")
    z2 = Column(Double, nullable=False, comment="下游偏移标高")
    q0 = Column(Double, nullable=False, comment="初始流量")
    qmax = Column(Double, nullable=True, comment="最大允许流量")
    shape = Column(String(50), nullable=False, comment="横截面形状")
    geom1 = Column(Double, nullable=False, comment="管段管径")
    geometry = Column(Geometry(geometry_type='LINESTRING', srid=srid), nullable=False, comment="管段地理坐标")


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
    geometry = Column(Geometry(geometry_type='GEOMETRY',srid=srid))


# 结果表ORM模型（4）
class Out_Nodes(Base):
    """out_nodes表：存储SWMM节点模拟结果"""
    __tablename__ = "out_nodes"  # 表名（需与代码中DAO对应的表名一致）
    # 基础关联字段
    node_id = Column(String(64), primary_key=True, comment="节点结果唯一标识（UUID）")
    id = Column(BigInteger, nullable=False, comment="关联基础表（Pipes_Junctions/Pipes_Outfalls）的主键ID")
    out_id = Column(String(64), nullable=False, comment="模拟结果批次ID（与Out_process的out_id一致）")
    time = Column(Integer, nullable=False, comment="模拟时间步（如第0步、第1步）")
    name = Column(String(64), nullable=False, comment="节点名称（与基础表一致）")
    # SWMM节点核心模拟指标
    invert_depth = Column(Float, comment="节点积水深度（单位：m）")
    hydraulic_head = Column(Float, comment="节点水力水头（单位：m）")
    ponded_volume = Column(Float, comment="节点淹没体积（单位：m³）")
    lateral_inflow = Column(Float, comment="节点侧向入流（单位：m³/s）")
    total_inflow = Column(Float, comment="节点总入流（单位：m³/s）")
    flooding_losses = Column(Float, comment="节点溢流量（单位：m³）")
    pollut_conc_0 = Column(Float, comment="节点污染物浓度（未模拟污染物则为NULL）")
    # 空间字段（POINT类型：节点坐标，坐标系EPSG:4326（WGS84））
    geometry = Column(Geometry("POINT", srid=srid), comment="节点空间坐标（WGS84坐标系）")


class Out_Links(Base):
    """out_links表：存储SWMM管段模拟结果"""
    __tablename__ = "out_links"  # 表名（需与代码中DAO对应的表名一致）
    # 基础关联字段
    link_id = Column(String(64), primary_key=True, comment="管段结果唯一标识（UUID）")
    id = Column(BigInteger, nullable=False, comment="关联基础表（Pipes_Conduits）的主键ID")
    out_id = Column(String(64), nullable=False, comment="模拟结果批次ID（与Out_process的out_id一致）")
    time = Column(Integer, nullable=False, comment="模拟时间步（如第0步、第1步）")
    name = Column(String(64), nullable=False, comment="管段名称（与基础表一致）")
    # SWMM管段核心模拟指标
    flow_rate = Column(Float, comment="管段流量（单位：m³/s）")
    flow_depth = Column(Float, comment="管段水流深度（单位：m）")
    flow_velocity = Column(Float, comment="管段水流速度（单位：m/s）")
    flow_volume = Column(Float, comment="管段过流体积（单位：m³）")
    capacity = Column(Float, comment="管段过流能力（单位：m³/s）")
    pollut_conc_0 = Column(Float, comment="管段污染物浓度（未模拟污染物则为NULL）")
    # 空间字段（LINESTRING类型：管段起止坐标，坐标系EPSG:4326（WGS84））
    geometry = Column(Geometry("LINESTRING", srid=srid), comment="管段空间坐标（WGS84坐标系）")


class Out_Systems(Base):
    """out_systems表：存储SWMM系统级模拟结果"""
    __tablename__ = "out_systems"  # 表名（需与代码中DAO对应的表名一致）
    # 基础关联字段
    id = Column(String(64), primary_key=True, comment="系统结果唯一标识（UUID）")
    out_id = Column(String(64), nullable=False, comment="模拟结果批次ID（与Out_process的out_id一致）")
    time = Column(Integer, nullable=False, comment="模拟时间步（如第0步、第1步）")
    # SWMM系统级核心模拟指标
    air_temp = Column(Float, comment="空气温度（单位：℃）")
    rainfall = Column(Float, comment="降雨量（单位：m/s，可后续转换为mm/h）")
    snow_depth = Column(Float, comment="积雪深度（单位：m，未模拟积雪则为NULL）")
    evap_infil_loss = Column(Float, comment="蒸发下渗损失（单位：m³/s）")
    runoff_flow = Column(Float, comment="径流量（单位：m³/s）")
    dry_weather_inflow = Column(Float, comment="旱季入流（单位：m³/s）")
    gw_inflow = Column(Float, comment="地下水入流（单位：m³/s，未模拟则为NULL）")
    rdii_inflow = Column(Float, comment="降雨径流入流（单位：m³/s，未模拟则为NULL）")
    direct_inflow = Column(Float, comment="直接入流（单位：m³/s）")
    total_lateral_inflow = Column(Float, comment="总侧向入流（单位：m³/s）")
    flood_losses = Column(Float, comment="系统总溢流量（单位：m³）")
    outfall_flows = Column(Float, comment="出水口总流量（单位：m³/s）")
    volume_stored = Column(Float, comment="系统总存储体积（单位：m³）")
    evap_rate = Column(Float, comment="实际蒸发率（单位：m/s）")
    ptnl_evap_rate = Column(Float, comment="潜在蒸发率（单位：m/s）")


class Out_Subcatchments(Base):
    """out_subcatchments表：存储SWMM子汇水区模拟结果"""
    __tablename__ = "out_subcatchments"

    subcatchment_id = Column(String(50), primary_key=True, comment="子汇水区结果唯一标识（UUID）")
    name = Column(String(50), nullable=False, comment="子汇水区名")
    out_id = Column(String(50), nullable=False, comment="模拟结果批次ID（与Out_process的out_id一致）")
    time = Column(Integer, nullable=False, comment="模拟时间步")
    rainfall = Column(Float, nullable=False, comment="降雨量")
    snow_depth = Column(Float, nullable=False, comment="积雪深度")
    evaporation = Column(Float, nullable=False, comment="蒸发量")
    infiltration = Column(Float, nullable=False, comment="下渗量")
    runoff = Column(Float, nullable=False, comment="径流量")
    groundwater_outflow = Column(Float, nullable=False, comment="进入管网的地下水流量")
    soil_moisture = Column(Float, nullable=False, comment="土壤湿度")
    pollutant_load_0 = Column(Float, nullable=False, comment="污染物负荷")
    geometry = Column(Geometry("GEOMETRY", srid=srid), comment="子汇水区空间坐标（WGS84坐标系）")


class BuildSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Build
        load_instance = True  # 表示在反序列化时直接生成对应实例

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        # print("get")
        # print(obj) <element.model.River object at 0x00000201D14311D0>
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        # schema.load
        # # 插入一条记录
        # location = Location(name="My Location", geom=from_shape(Point(12.34, 56.78), srid=4326))
        # session.add(location)
        # session.commit()
        return from_shape(obj, srid=srid)


class LakeSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Lake
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class RiverSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = River
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class DamSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Dam
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class LandSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Land
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class RoadSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Road
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Pipe_JunctionSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Pipe_Junction
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Pipe_OutfallSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Pipe_Outfall
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Pipe_ConduitSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Pipe_Conduit
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Pipe_SubcatchSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Pipe_Subcatchment
        load_instance = True
    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None
    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Out_SystemsSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Out_Systems
        load_instance = True


class Out_NodesSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Out_Nodes
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Out_LinksSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Out_Links
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)


class Out_SubcatchmentsSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Out_Subcatchments
        load_instance = True

    # 自定义 geometry 字段的序列化和反序列化
    geometry = fields.Method("get_geometry", "set_geometry")

    def get_geometry(self, obj):
        return to_shape(obj.geometry) if obj.geometry else None

    def set_geometry(self, obj):
        return from_shape(obj, srid=srid)