import os
import traceback
import geopandas as gpd
from dotenv import load_dotenv
from shapely.wkt import loads
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from pyswmm import Output, NodeSeries, LinkSeries, SystemSeries
from swmm.toolkit.shared_enum import SubcatchAttribute
import uuid

from Tools.PGTools.dao import Dao
from Tools.PGTools.model import Out_Nodes, Out_Links, Out_Systems, Out_Subcatchments
from Tools.PGTools.shp2json import to_geojson

load_dotenv()

# -------------------------- 数据库配置 --------------------------
DB_URL = os.getenv('DB_URL_NEW')
SRID = 4549

# 初始化SQLAlchemy
engine = create_engine(DB_URL, echo=False)
Session = sessionmaker(bind=engine)


class OutProcess:
    """
    统一的SWMM输出文件处理类
    功能：解析OUT文件中的节点、管段、系统和子汇水区数据，存储到数据库并生成可视化文件
    """

    def __init__(self, dataset_id, project_id, out_id, out_file):
        """
        初始化处理类

        Args:
            dataset_id: 数据集ID
            project_id: 项目ID
            out_id: 输出批次ID
        """
        self._dataset_id = dataset_id
        self._project_id = project_id
        self._out_id = out_id
        self._out_file = out_file

        # 创建输出目录
        self.base_output_dir = os.path.join(os.getenv("PROCESS_OUTPUT_DIR"), self._project_id, self._out_id)
        self.temp_dir = self.base_output_dir + os.getenv("TEMP_FOLDER", "/temp/")
        self.visual_dir = self.base_output_dir + os.getenv("VISUAL_FOLDER", "/visual/")

        for dir_path in [self.base_output_dir, self.temp_dir, self.visual_dir]:
            os.makedirs(dir_path, exist_ok=True)

        print(f"✅ 输出目录就绪：{self.base_output_dir}")
        print(f"  - 临时文件：{self.temp_dir}")
        print(f"  - 可视化文件：{self.visual_dir}")

        try:
            # 初始化所有DAO对象
            self.outsystem_dao = Dao("Out_Systems")
            self.outnode_dao = Dao("Out_Nodes")
            self.outlink_dao = Dao("Out_Links")
            self.outsubcatchment_dao = Dao("Out_Subcatchments")

            # 基础数据DAO
            self.junction_dao = Dao("Pipes_Junctions")
            self.conduit_dao = Dao("Pipes_Conduits")
            self.outfall_dao = Dao("Pipes_Outfalls")
            self.subcatchment_dao = Dao("Pipes_Subcatchments")

            # 测试数据库连接
            with engine.connect():
                print("✅ 数据库连接成功")

        except SQLAlchemyError as e:
            print(f"❌ 数据库初始化失败：{str(e)}")
            traceback.print_exc()
            raise

    def create_all_tables(self):
        """创建所有结果表"""
        session = Session()
        try:
            # 启用PostGIS
            print("1. 检查PostGIS扩展...")
            session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            session.commit()
            print("   ✅ PostGIS扩展就绪")

            # 创建所有结果表
            print("\n2. 创建所有结果表...")
            tables_to_create = [
                Out_Nodes.__table__,
                Out_Links.__table__,
                Out_Systems.__table__,
                Out_Subcatchments.__table__
            ]

            for table in tables_to_create:
                table.create(bind=engine, checkfirst=True)
            print("   ✅ 所有结果表创建完成")

            # 添加索引
            print("\n3. 添加索引...")
            index_sqls = [
                # out_nodes表索引
                "CREATE INDEX IF NOT EXISTS idx_out_nodes_out_id ON out_nodes (out_id);",
                "CREATE INDEX IF NOT EXISTS idx_out_nodes_out_id_time ON out_nodes (out_id, time);",
                "CREATE INDEX IF NOT EXISTS idx_out_nodes_name ON out_nodes (name);",
                "CREATE INDEX IF NOT EXISTS idx_out_nodes_geometry ON out_nodes USING GIST (geometry);",
                # out_links表索引
                "CREATE INDEX IF NOT EXISTS idx_out_links_out_id ON out_links (out_id);",
                "CREATE INDEX IF NOT EXISTS idx_out_links_out_id_time ON out_links (out_id, time);",
                "CREATE INDEX IF NOT EXISTS idx_out_links_name ON out_links (name);",
                "CREATE INDEX IF NOT EXISTS idx_out_links_geometry ON out_links USING GIST (geometry);",
                # out_systems表索引
                "CREATE INDEX IF NOT EXISTS idx_out_systems_out_id ON out_systems (out_id);",
                "CREATE INDEX IF NOT EXISTS idx_out_systems_out_id_time ON out_systems (out_id, time);",
                # out_subcatchments表索引
                "CREATE INDEX IF NOT EXISTS idx_out_subcatchments_out_id ON out_subcatchments (out_id);",
                "CREATE INDEX IF NOT EXISTS idx_out_subcatchments_out_id_time ON out_subcatchments (out_id, time);",
                "CREATE INDEX IF NOT EXISTS idx_out_subcatchments_geometry ON out_subcatchments USING GIST (geometry);"
            ]

            for sql in index_sqls:
                session.execute(text(sql))
            session.commit()
            print("   ✅ 所有索引添加完成")

            print("\n🎉 所有数据库表结构就绪！")

        except Exception as e:
            session.rollback()
            print(f"\n❌ 创建表失败：{str(e)}")
            traceback.print_exc()
            raise
        finally:
            session.close()

    def dataload_all(self):
        """
        解析OUT文件的所有数据并入库
        包括：节点、管段、系统、子汇水区数据
        """
        print("=" * 60)
        print("开始解析SWMM OUT文件所有数据")
        print("=" * 60)

        try:
            # 1. 处理节点、管段、系统数据
            self._dataload_nodes_links_systems()

            # 2. 处理子汇水区数据
            self._dataload_subcatchments()

            print("\n🎉 所有数据解析完成！")

        except Exception as e:
            print(f"❌ 数据解析失败：{str(e)}")
            traceback.print_exc()
            raise

    def _dataload_nodes_links_systems(self):
        """处理节点、管段、系统数据"""
        print("\n----- 开始处理节点、管段、系统数据 -----")

        try:
            # 读取基础管网数据
            nodes_info1 = self.junction_dao.read(conditions={'dataset_id': self._dataset_id})
            nodes_info2 = self.outfall_dao.read(conditions={'dataset_id': self._dataset_id})
            nodes_info = nodes_info1 + nodes_info2
            lines_info = self.conduit_dao.read(conditions={'dataset_id': self._dataset_id})

            if not nodes_info and not lines_info:
                print("⚠️ 警告：未读取到任何节点或管段数据")

            # 读取SWMM的.out文件
            pipe_out_file = self._out_file
            with Output(pipe_out_file) as out:
                print(f"SWMM文件包含节点数：{len(out.nodes)}，管段数：{len(out.links)}")
                print(f"模拟时间步数量：{len(out.times)}")

                times = out.times
                nodeseries = NodeSeries(out)
                linkseries = LinkSeries(out)
                systemseries = SystemSeries(out)

                # 处理节点数据
                nodes_list = []
                for node in nodes_info:
                    name = node["name"]
                    if name not in out.nodes:
                        print(f"⚠️ 节点 {name} 在SWMM输出中不存在，跳过")
                        continue
                    for i, time in enumerate(times):
                        try:
                            temp = {
                                'id': node["id"],
                                'node_id': str(uuid.uuid4()),
                                'out_id': self._out_id,
                                'time': i,
                                'invert_depth': nodeseries[name].invert_depth[time],
                                'hydraulic_head': nodeseries[name].hydraulic_head[time],
                                'ponded_volume': nodeseries[name].ponded_volume[time],
                                'lateral_inflow': nodeseries[name].lateral_inflow[time],
                                'total_inflow': nodeseries[name].total_inflow[time],
                                'flooding_losses': nodeseries[name].flooding_losses[time],
                                'pollut_conc_0': nodeseries[name].pollut_conc_0[time],
                                'name': name,
                                'geometry': node["geometry"]
                            }
                            nodes_list.append(temp)
                        except Exception as e:
                            print(f"⚠️ 处理节点 {name} 时间步 {i} 出错：{str(e)}")

                # 处理管段数据
                links_list = []
                for line in lines_info:
                    name = line["name"]
                    if name not in out.links:
                        print(f"⚠️ 管段 {name} 在SWMM输出中不存在，跳过")
                        continue
                    for i, time in enumerate(times):
                        try:
                            temp = {
                                'id': line["id"],
                                'link_id': str(uuid.uuid4()),
                                'out_id': self._out_id,
                                'time': i,
                                'flow_rate': linkseries[name].flow_rate[time],
                                'flow_depth': linkseries[name].flow_depth[time],
                                'flow_velocity': linkseries[name].flow_velocity[time],
                                'flow_volume': linkseries[name].flow_volume[time],
                                'capacity': linkseries[name].capacity[time],
                                'pollut_conc_0': linkseries[name].pollut_conc_0[time],
                                'name': name,
                                'geometry': line["geometry"]
                            }
                            links_list.append(temp)
                        except Exception as e:
                            print(f"⚠️ 处理管段 {name} 时间步 {i} 出错：{str(e)}")

                # 处理系统数据
                system_list = []
                for i, time in enumerate(times):
                    try:
                        temp = {
                            'id': str(uuid.uuid4()),
                            'out_id': self._out_id,
                            'time': i,
                            'air_temp': systemseries.air_temp[time],
                            'rainfall': systemseries.rainfall[time],
                            'snow_depth': systemseries.snow_depth[time],
                            'evap_infil_loss': systemseries.evap_infil_loss[time],
                            'runoff_flow': systemseries.runoff_flow[time],
                            'dry_weather_inflow': systemseries.dry_weather_inflow[time],
                            'gw_inflow': systemseries.gw_inflow[time],
                            'rdii_inflow': systemseries.rdii_inflow[time],
                            'direct_inflow': systemseries.direct_inflow[time],
                            'total_lateral_inflow': systemseries.total_lateral_inflow[time],
                            'flood_losses': systemseries.flood_losses[time],
                            'outfall_flows': systemseries.outfall_flows[time],
                            'volume_stored': systemseries.volume_stored[time],
                            'evap_rate': systemseries.evap_rate[time],
                            'ptnl_evap_rate': systemseries.ptnl_evap_rate[time]
                        }
                        system_list.append(temp)
                    except Exception as e:
                        print(f"⚠️ 处理系统数据时间步 {i} 出错：{str(e)}")

                # 批量写入数据库
                print(f"\n待写入数据：节点{len(nodes_list)}条，管段{len(links_list)}条，系统{len(system_list)}条")

                if nodes_list:
                    self.outnode_dao.create_many(nodes_list)
                    print(f"✅ 节点数据写入成功（{len(nodes_list)}条）")

                if links_list:
                    self.outlink_dao.create_many(links_list)
                    print(f"✅ 管段数据写入成功（{len(links_list)}条）")

                if system_list:
                    self.outsystem_dao.create_many(system_list)
                    print(f"✅ 系统数据写入成功（{len(system_list)}条）")

        except FileNotFoundError:
            print(f"❌ SWMM输出文件不存在：{pipe_out_file}")
            raise
        except Exception as e:
            print(f"❌ 节点管段系统数据处理失败：{str(e)}")
            raise

    def _dataload_subcatchments(self):
        """处理子汇水区数据"""
        print("\n----- 开始处理子汇水区数据 -----")

        try:
            # 读取基础子汇水区数据
            subcatchments_info = self.subcatchment_dao.read(conditions={'dataset_id': self._dataset_id})

            if not subcatchments_info:
                raise Exception(f"基础子汇水区数据为空！dataset_id={self._dataset_id}")

            # 处理有效数据
            valid_subs = []
            for sub in subcatchments_info:
                if not all(key in sub for key in ["name", "geometry"]):
                    continue
                if sub["geometry"] is None or not sub["name"]:
                    continue
                try:
                    sub["geometry"] = loads(str(sub["geometry"]))
                    valid_subs.append(sub)
                except Exception as e:
                    print(f"⚠️ 转换子汇水区几何数据失败：{str(e)}，跳过")
                    continue

            print(f"✅ 有效基础数据：{len(valid_subs)} 个")
            if not valid_subs:
                raise Exception("无有效基础数据")

            # 读取SWMM OUT文件
            out_file = self._out_file

            with Output(out_file) as out:
                swmm_sub_names = list(out.subcatchments.keys())
                time_count = len(out.times)
                print(f"✅ SWMM包含 {len(swmm_sub_names)} 个子汇水区，时间步：{time_count}")

                # 属性映射
                attribute_mapping = {
                    SubcatchAttribute.RAINFALL: "rainfall",
                    SubcatchAttribute.SNOW_DEPTH: "snow_depth",
                    SubcatchAttribute.EVAP_LOSS: "evaporation",
                    SubcatchAttribute.INFIL_LOSS: "infiltration",
                    SubcatchAttribute.RUNOFF_RATE: "runoff",
                    SubcatchAttribute.GW_OUTFLOW_RATE: "groundwater_outflow",
                    SubcatchAttribute.SOIL_MOISTURE: "soil_moisture",
                    SubcatchAttribute.POLLUT_CONC_0: "pollutant_load_0"
                }

                result_list = []
                processed_count = 0

                for sub in valid_subs:
                    sub_name = sub["name"].strip()

                    # 匹配SWMM中的子汇水区
                    matched_name = None
                    for swmm_name in swmm_sub_names:
                        if sub_name.lower() == swmm_name.lower():
                            matched_name = swmm_name
                            break

                    if not matched_name:
                        print(f"基础子汇水区「{sub_name}」在SWMM中无匹配，跳过")
                        continue

                    try:
                        # 提取属性数据
                        attribute_data = {}
                        for swmm_attr, db_field in attribute_mapping.items():
                            try:
                                ts = out.subcatch_series(matched_name, swmm_attr)
                                values = [float(value) if value is not None else 0.0 for timestamp, value in ts.items()]
                                attribute_data[db_field] = values
                            except Exception as e:
                                print(f"提取 {db_field} 失败: {str(e)}")
                                attribute_data[db_field] = [0.0] * time_count

                        # 为每个时间步创建记录
                        for time_idx in range(time_count):
                            temp = {
                                "subcatchment_id": str(uuid.uuid4()),
                                "name": sub_name,
                                "out_id": self._out_id,
                                "time": time_idx,
                                "geometry": sub["geometry"]
                            }

                            for db_field in attribute_mapping.values():
                                if (db_field in attribute_data and
                                        len(attribute_data[db_field]) > time_idx):
                                    temp[db_field] = attribute_data[db_field][time_idx]
                                else:
                                    temp[db_field] = 0.0

                            result_list.append(temp)

                        processed_count += 1

                    except Exception as e:
                        print(f"❌ 处理子汇水区 {sub_name} 失败: {str(e)}")
                        continue

                # 写入数据库
                print(f"待写入子汇水区数据：{len(result_list)} 条")

                if result_list:
                    batch_size = 1000
                    for i in range(0, len(result_list), batch_size):
                        batch = result_list[i:i + batch_size]
                        self.outsubcatchment_dao.create_many(batch)
                    print(f"✅ 子汇水区数据写入成功（{len(result_list)}条）")
                else:
                    print("⚠️ 无子汇水区数据可写入")

        except Exception as e:
            print(f"❌ 子汇水区数据处理失败：{str(e)}")
            raise

    def visualize_all(self):
        """
        生成所有数据的可视化文件（GeoJSON）
        包括：节点、管段、子汇水区
        """
        print("=" * 60)
        print("开始生成所有可视化文件")
        print("=" * 60)

        try:
            # 1. 生成节点可视化
            self._visualize_nodes()

            # 2. 生成管段可视化
            self._visualize_links()

            # 3. 生成子汇水区可视化
            self._visualize_subcatchments()

            print("\n🎉 所有可视化文件生成完成！")

        except Exception as e:
            print(f"❌ 可视化文件生成失败：{str(e)}")
            traceback.print_exc()
            raise

    def _visualize_nodes(self):
        """生成节点可视化文件"""
        print("\n----- 生成节点GeoJSON -----")

        try:
            cursors = self.outnode_dao.read({"out_id": self._out_id}, exclude_fields=["id", "out_id"])

            new_column_names = {
                'time': 'time',
                'invert_depth': 'depth',
                'hydraulic_head': 'head',
                'ponded_volume': 'ponded_v',
                'lateral_inflow': 'lateral_i',
                'total_inflow': 'total_i',
                'flooding_losses': 'flooding',
                'pollut_conc_0': 'pollut',
                'name': 'name',
                'geometry': 'geometry'
            }

            gdf = gpd.GeoDataFrame(cursors, crs='CGCS2000 / 3-degree Gauss-Kruger CM 120E')
            gdf.rename(columns=new_column_names, inplace=True)
            gdf.to_file(self.temp_dir + "/out_nodes.shp", driver='ESRI Shapefile', encoding='utf-8')

            to_geojson(self.temp_dir + "/out_nodes.shp", self.visual_dir + "/out_nodes.json")
            print("✅ 节点GeoJSON生成完成")

        except Exception as e:
            print(f"❌ 节点可视化失败：{str(e)}")
            raise

    def _visualize_links(self):
        """生成管段可视化文件"""
        print("\n----- 生成管段GeoJSON -----")

        try:
            cursors = self.outlink_dao.read({"out_id": self._out_id}, exclude_fields=["id", "out_id"])

            new_column_names = {
                'time': 'time',
                'flow_rate': 'rate',
                'flow_depth': 'depth',
                'flow_velocity': 'velocity',
                'flow_volume': 'volume',
                'capacity': 'capacity',
                'pollut_conc_0': 'pollut',
                'name': 'name',
                'geometry': 'geometry'
            }

            gdf = gpd.GeoDataFrame(cursors, crs='CGCS2000 / 3-degree Gauss-Kruger CM 120E')
            gdf.rename(columns=new_column_names, inplace=True)
            gdf.to_file(self.temp_dir + "/out_links.shp", driver='ESRI Shapefile', encoding='utf-8')

            to_geojson(self.temp_dir + "/out_links.shp", self.visual_dir + "/out_links.json")
            print("✅ 管段GeoJSON生成完成")

        except Exception as e:
            print(f"❌ 管段可视化失败：{str(e)}")
            raise

    def _visualize_subcatchments(self):
        """生成子汇水区可视化文件"""
        print("\n----- 生成子汇水区GeoJSON -----")

        try:
            cursors = self.outsubcatchment_dao.read(
                conditions={"out_id": self._out_id},
                exclude_fields=["subcatchment_id", "out_id"]
            )

            valid_data = []
            for data in cursors:
                if "geometry" not in data or data["geometry"] is None:
                    continue
                try:
                    data["geometry"] = loads(str(data["geometry"]))
                    valid_data.append(data)
                except Exception as e:
                    print(f"转换几何数据失败：{str(e)}，跳过")
                    continue

            if not valid_data:
                raise Exception("无有效可视化数据")

            gdf = gpd.GeoDataFrame(valid_data, geometry="geometry", crs=f"EPSG:{SRID}")

            new_column_names = {
                'time': 'time',
                'rainfall': 'rain',
                'snow_depth': 'snow',
                'evaporation': 'evap',
                'infiltration': 'infilt',
                'runoff': 'runoff',
                'groundwater_outflow': 'gw_flow',
                'soil_moisture': 'soil_moist',
                'pollutant_load_0': 'pollut',
                'name': 'name'
            }

            gdf = gdf.rename(columns=new_column_names)[list(new_column_names.values()) + ["geometry"]]

            shp_path = os.path.join(self.temp_dir, "out_subcatchments.shp")
            gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")

            json_path = os.path.join(self.visual_dir, "out_subcatchments.json")
            to_geojson(shp_path, json_path)
            print("✅ 子汇水区GeoJSON生成完成")

        except Exception as e:
            print(f"❌ 子汇水区可视化失败：{str(e)}")
            raise


# 调用示例
if __name__ == "__main__":
    # 参数设置
    dataset_id = "20250301"  # 你的数据集ID
    project_id = "20251024_104217"  # 项目ID（与INP生成时一致）
    out_id = "m0"  # 输出批次ID

    try:
        # 1. 创建处理实例
        processor = OutProcess(dataset_id, project_id, out_id)

        # 2. 创建数据库表（首次运行需要）
        print("步骤1: 创建数据库表...")
        processor.create_all_tables()

        # 3. 解析OUT文件数据并入库
        print("\n步骤2: 解析OUT文件数据...")
        processor.dataload_all()

        # 4. 生成可视化文件
        print("\n步骤3: 生成可视化文件...")
        processor.visualize_all()

        print(f"\n🎉 所有处理完成！")
        print(f"数据已存储到数据库，可视化文件在：{processor.visual_dir}")

    except Exception as e:
        print(f"❌ 处理失败：{str(e)}")
        import traceback

        traceback.print_exc()
