from app.swmm.runner import run_pyswmm


class SwmmService:
    """
    SWMM 业务层
    """

    @staticmethod
    def run_model(inp_file: str) -> dict:
        """
        根据 inp_file 运行模型
        """
        if not inp_file:
            return {
                "success": False,
                "message": "inp_file 不能为空"
            }

        try:
            result = run_pyswmm(inp_file)
            return result
        except FileNotFoundError as e:
            return {
                "success": False,
                "message": str(e)
            }
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "message": f"模型运行失败: {e}"
            }
