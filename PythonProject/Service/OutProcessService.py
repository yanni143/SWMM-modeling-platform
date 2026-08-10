import os
import datetime
from typing import Dict, Any, Optional
import traceback
from swmm_core.output_processor import OutProcess


class OutProcessService:
    """SWMM输出文件处理服务层"""

    def __init__(self):
        self.processor = None

    def process_swmm_output(self, dataset_id: str, project_id: str, out_id: str, out_file: str) -> Dict[str, Any]:
        """
        处理SWMM输出文件的完整流程
        Args:dataset_id: 数据集ID
            project_id: 项目ID（与INP生成时一致）
            out_id: 输出批次ID
        Returns:处理结果字典
        """
        try:
            # 参数验证
            if not all([dataset_id, project_id, out_id]):
                return {
                    "success": False,
                    "error": "缺少必要参数：dataset_id, project_id, out_id"
                }

            # 1. 创建处理实例
            print(f"开始处理SWMM输出文件: dataset_id={dataset_id}, project_id={project_id}, out_id={out_id}, out_file={out_file}")
            self.processor = OutProcess(dataset_id, project_id, out_id, out_file)

            # 2. 创建数据库表
            print("步骤1: 创建数据库表...")
            self.processor.create_all_tables()

            # 3. 解析OUT文件数据并入库
            print("步骤2: 解析OUT文件数据...")
            self.processor.dataload_all()

            # 4. 生成可视化文件
            print("步骤3: 生成可视化文件...")
            self.processor.visualize_all()

            result = {
                "success": True,
                "message": "SWMM输出文件处理完成",
                "dataset_id": dataset_id,
                "project_id": project_id,
                "out_id": out_id,
                "visual_dir": self.processor.visual_dir
            }

            print(f"✅ SWMM输出文件处理完成")
            return result

        except Exception as e:
            error_msg = f"SWMM输出文件处理失败：{str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()

            return {
                "success": False,
                "error": error_msg,
                "dataset_id": dataset_id,
                "project_id": project_id,
                "out_id": out_id
            }

    def check_out_file_exists(self, project_id: str) -> Dict[str, Any]:
        """
        检查OUT文件是否存在
        Args:project_id: 项目ID
        Returns:检查结果
        """
        try:
            out_file_path = os.path.join(os.getenv("PROCESS_OUTPUT_DIR"), project_id, "model.out")

            exists = os.path.exists(out_file_path)
            file_size = os.path.getsize(out_file_path) if exists else 0

            return {
                "exists": exists,
                "file_path": out_file_path,
                "file_size_bytes": file_size
            }

        except Exception as e:
            return {
                "exists": False,
                "error": f"检查文件失败: {str(e)}"
            }


# 创建全局服务实例
out_process_service = OutProcessService()
