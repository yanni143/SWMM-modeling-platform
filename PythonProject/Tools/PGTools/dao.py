from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from database.session import get_engine

# from dao.model import Build, Lake, Road, River, River_Component, Land, Dam, Pipe_Junction, Pipe_Outfall, Pipe_Conduit, \
#     Pipe_Coordinate, Pipe_Subcatchment, Pipe_Inflows_Direct, Dataset, Project, History_Chat, Edge_Topology, Rain
# from dao.model import BuildSchema, LakeSchema, RoadSchema, RiverSchema, RiverComponentsSchema, LandSchema, DamSchema
# from dao.model import Pipe_JunctionSchema, Pipe_OutfallSchema, Pipe_ConduitSchema, Pipe_CoordinateSchema, Pipe_Inflows_DirectSchema, Pipe_SubcatchSchema
# from dao.model import Out_Systems, Out_Nodes, Out_Links, Out_SystemsSchema, Out_NodesSchema, Out_LinksSchema, Edge_TopologySchema
# from dao.model import ProjectSchema, DatasetSchema, HistoryChatSchema, RainSchema

from Tools.PGTools.model import Out_Nodes, Out_Links, Out_Systems, Out_NodesSchema, Out_LinksSchema, Out_SystemsSchema, \
    Pipe_JunctionSchema, Pipe_OutfallSchema, Pipe_ConduitSchema, Pipe_Junction, Pipe_Outfall, Pipe_Conduit, Lake, Road, \
    River, Land, Dam, Build, LakeSchema, RoadSchema, RiverSchema, LandSchema, DamSchema, BuildSchema, Pipe_Subcatchment, \
    Out_Subcatchments, Pipe_SubcatchSchema, Out_SubcatchmentsSchema

class Dao:
    def __init__(self, table):
        # 创建数据库连接
        # engine = create_engine("postgresql+psycopg2://postgres:520143@localhost/postgis_35_sample")
        engine = get_engine()
        '''
        autocommit=False: 默认情况下，不自动提交事务。这意味着你需要显式地调用 commit() 方法来提交事务。
        autoflush=False: 默认情况下，不自动刷新待插入/更新的数据。这意味着在执行查询之前，不会自动将未提交的变更写入数据库。这有助于提高性能，但也意味着你需要手动调用 flush() 方法来刷新待插入/更新的数据。
        bind=engine: 将这个 Session 工厂绑定到前面定义的 engine 实例上。这意味着从这个工厂创建的任何 Session 实例都将使用同一个数据库引擎连接到数据库。
        '''
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        self.db = SessionLocal()
        # 动态获取模型类
        self.model_class = self._get_model_class(table)
        # 动态获取schema类
        self.schema_class = self._get_schema_class(table)

    def _get_model_class(self, table_name):
        keys_value = {
            "Builds": Build,
            "Lakes": Lake,
            "Roads": Road,
            "Rivers": River,
            # "Rivers_Components": River_Component,
            "Lands": Land,
            "Dams": Dam,
            "Pipes_Junctions": Pipe_Junction,
            "Pipes_Outfalls": Pipe_Outfall,
            "Pipes_Conduits": Pipe_Conduit,
            "Pipes_Subcatchments": Pipe_Subcatchment,
            # "Pipes_Coordinates": Pipe_Coordinate,
            # "Pipes_Inflows_Direct": Pipe_Inflows_Direct,
            "Out_Systems": Out_Systems,
            "Out_Nodes": Out_Nodes,
            "Out_Links": Out_Links,
            "Out_Subcatchments": Out_Subcatchments,
            # "Datasets": Dataset,
            # "Projects": Project,
            # "History_Chat": History_Chat,
            # "Edge_Topology": Edge_Topology,
            # "Rains": Rain,
        }
        if table_name in keys_value.keys():
            return keys_value[table_name]
        else:
            raise ValueError(f"Unsupported table name: {table_name}")

    def _get_schema_class(self, table_name):
        keys_value = {
            "Builds": BuildSchema,
            "Lakes": LakeSchema,
            "Roads": RoadSchema,
            "Rivers": RiverSchema,
            # "Rivers_Components": RiverComponentsSchema,
            "Lands": LandSchema,
            "Dams": DamSchema,
            "Pipes_Junctions": Pipe_JunctionSchema,
            "Pipes_Outfalls": Pipe_OutfallSchema,
            "Pipes_Conduits": Pipe_ConduitSchema,
            "Pipes_Subcatchments": Pipe_SubcatchSchema,
            # "Pipes_Coordinates": Pipe_CoordinateSchema,
            # "Pipes_Inflows_Direct": Pipe_Inflows_DirectSchema,
            "Out_Systems": Out_SystemsSchema,
            "Out_Nodes": Out_NodesSchema,
            "Out_Links": Out_LinksSchema,
            "Out_Subcatchments": Out_SubcatchmentsSchema,
            # "Datasets": DatasetSchema,
            # "Projects": ProjectSchema,
            # "History_Chat": HistoryChatSchema,
            # "Edge_Topology": Edge_TopologySchema,
            # "Rains": RainSchema
        }
        if table_name in keys_value.keys():
            return keys_value[table_name]
        else:
            raise ValueError(f"Unsupported table name: {table_name}")

    def create(self, data):
        try:
            schema = self.schema_class()
            new_item = schema.load(data, session=self.db)
            # new_item = self.model_class(**data)
            self.db.add(new_item)
            self.db.commit()
            self.db.refresh(new_item)
            return True
        except IntegrityError as e:
            self.db.rollback()
            print(f"Integrity Error: {e}")
            return False
        except Exception as e:
            self.db.rollback()
            print(f"An error occurred: {e}")
            return False
        finally:
            self.db.close()

    def create_many(self, records):
        try:
            schema = self.schema_class()
            # 将 JSON 对象转换为字符串
            prepared_data = []
            for data in records:
                prepared_data.append(schema.load(data, session=self.db))
            # 使用 bulk_insert_mappings 方法批量插入记录
            self.db.bulk_insert_mappings(self.model_class, [r.__dict__ for r in prepared_data])
            self.db.commit()
            return True
        except IntegrityError as e:
            self.db.rollback()
            print(f"Integrity Error: {e}")
            return False
        except Exception as e:
            self.db.rollback()
            print(f"An error occurred: {e}")
            return False
        finally:
            self.db.close()

    def read(self, conditions={}, order_by=None, desc=False, limit=None, offset=None, exclude_fields=[]):
        """
        多条件查询

        :param conditions: 字典形式的条件，如 {'name': 'Record1', 'value': 1.1}
        :param order_by: 字段名称，用于排序
        :param desc: 是否降序排列，默认为升序
        :param limit: 查询结果的数量限制
        :param offset: 分页偏移量
        :param exclude_fields: 需要排除的字段列表
        """
        try:
            query = self.db.query(self.model_class)
            for key, value in conditions.items():
                if (isinstance(value, list)):
                    # where in
                    query = query.filter(getattr(self.model_class, key).in_(value))
                else:
                    query = query.filter(getattr(self.model_class, key) == value)

            if order_by:
                if desc:
                    query = query.order_by(getattr(self.model_class, order_by).desc())
                else:
                    query = query.order_by(getattr(self.model_class, order_by))

            if limit is not None:
                query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)

            schema = self.schema_class(many=True)
            results = query.all()
            if exclude_fields != []:
                # 创建一个自定义的Schema类，排除指定的字段
                class CustomSchema(self.schema_class):
                    class Meta(self.schema_class.Meta):
                        exclude = tuple(exclude_fields)

                schema = CustomSchema(many=True)
                serialized_results = schema.dump(results)
                return serialized_results
            else:
                return schema.dump(results)

        except Exception as e:
            print(f"Failed to query with multiple conditions due to error: {e}")
            return False
        finally:
            self.db.close()

    def update(self, conditions=None, new_values=None):
        """根据条件更新记录"""
        try:
            schema = self.schema_class()
            # 使用 Schema 处理更新数据
            prepared_update_data = schema.load(new_values, partial=True, session=self.db)
            prepared_update_data = prepared_update_data.__dict__
            del prepared_update_data['_sa_instance_state']
            # print(prepared_update_data)
            # 构造查询条件
            query = self.db.query(self.model_class)
            for key, value in conditions.items():
                query = query.filter(getattr(self.model_class, key) == value)
            # 执行更新操作
            # 必需参数，一个字典，表示要更新的字段及其新值。
            # 示例：{'name': 'NewName', 'age': 30} 表示将 name 字段更新为 'NewName'，age 字段更新为 30。
            query.update(prepared_update_data, synchronize_session='fetch')
            self.db.commit()
            print("Records updated successfully based on the condition.")
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Failed to update records based on the condition due to error: {e}")
            return False
        finally:
            self.db.close()

    def count(self, conditions={}):
        """根据条件统计记录数量"""
        try:
            query = self.db.query(self.model_class)
            for key, value in conditions.items():
                query = query.filter(getattr(self.model_class, key) == value)

            count = query.count()
            return count
        except Exception as e:
            print(f"Failed to countrecords based on the condition due to error: {e}")
            return False

    def delete(self, conditions={}):
        """根据条件删除记录"""
        try:
            # 构造查询条件
            query = self.db.query(self.model_class)
            for key, value in conditions.items():
                query = query.filter(getattr(self.model_class, key) == value)

            # 执行删除操作
            query.delete(synchronize_session=False)
            self.db.commit()
            print("Records deleted successfully based on the condition.")
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Failed to delete records based on the condition due to error: {e}")
            return False
        finally:
            self.db.close()


# a = Dao("Dams")
# print(a.read())
