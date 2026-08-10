import os
import geopandas as gpd
import pyproj
from pyproj import Transformer
from shapely.ops import transform


def to_geojson(filepath,outfile_path):
    filename = os.path.basename(outfile_path)
    gdf = gpd.read_file(filepath)
    # 确定原始坐标系统
    original_crs = pyproj.CRS("EPSG:4549")  # CGCS2000 3-degree Gauss-Kruger CM 120E
    target_crs = pyproj.CRS('EPSG:4326')  # WGS 84

    # 创建坐标转换器
    transformer = Transformer.from_crs(original_crs, target_crs, always_xy=True)

    # print(transformer.transform(579963.5235000001,3435177.4617))

    # 转换坐标
    # 使用 transform 函数来转换整个几何对象
    gdf['geometry'] = gdf['geometry'].apply(lambda geom: transform(transformer.transform, geom))

    # 设置新的坐标参考系统
    gdf.crs = target_crs
    # 将 GeoDataFrame 转换为 GeoJSON
    gdf.to_file(outfile_path, driver='GeoJSON',encoding='utf-8')

    print(f"{filename} to geojson")