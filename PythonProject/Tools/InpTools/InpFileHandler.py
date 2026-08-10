import os
from typing import Tuple


class INPFileHandler:
    @staticmethod
    def read_file(file_path: str) -> Tuple[str, str]:
        """读取本地INP文件内容，尝试多种编码格式"""
        # 常见的编码格式列表，按可能性排序
        encodings = ['utf-8', 'gbk', 'gb2312', 'ansi', 'latin-1']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    content = file.read()
                return content, f"文件读取成功，使用编码: {encoding}"
            except UnicodeDecodeError:
                continue  # 尝试下一种编码
            except FileNotFoundError:
                return "", f"错误: 文件未找到 - {file_path}"
            except PermissionError:
                return "", f"错误: 没有权限读取文件 - {file_path}"
            except Exception as e:
                return "", f"读取文件时出错 ({encoding}): {str(e)}"

        # 如果所有编码都尝试失败，返回二进制读取的内容（作为最后的尝试）
        try:
            with open(file_path, 'rb') as file:
                content = file.read()
            # 替换无法解码的字符
            content_str = content.decode('utf-8', errors='replace')
            return content_str, "警告: 文件编码未知，已替换无法解码的字符"
        except Exception as e:
            return "", f"所有编码尝试失败，无法读取文件: {str(e)}"

    @staticmethod
    def write_file(file_path: str, content: str) -> str:
        """将修改后的内容写入文件，使用UTF-8 编码"""
        try:
            # 确保目录存在
            directory = os.path.dirname(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            return f"文件已成功写入 (UTF-8编码): {file_path}"
        except PermissionError:
            return f"错误: 没有权限写入文件 - {file_path}"
        except Exception as e:
            return f"写入文件时出错: {str(e)}"

