import re
from typing import Dict, List, Tuple, Optional


# 修改执行器
class INPModifier:
    # 预定义各节的标准参数信息（作为默认值）
    _SECTION_PARAMS = {
        "JUNCTIONS": ["name", "elev", "ymax", "y0", "ysur", "apond"],
        "CONDUITS": ["name", "node1", "node2", "length", "n", "z1", "z2", "q0", "qmax"],
        "OUTFALLS": ["name", "elev", "type", "gated", "touteto"],
        "SUBCATCHMENTS": ["name", "rgage", "outid", "area", "%imperv", "width", "slope", "curb_length", "snowpack"],
        "XSECTIONS": ["link", "shape", "geom1", "geom2", "geom3", "geom4", "barrels", "culvert"],
        "STORAGE": ["name", "el", "ymax", "y0", "type", "acurve"]
    }

    @staticmethod
    def modify(sections: Dict[str, List[str]], parsed_instructions: List[Dict]) -> Tuple[Dict[str, List[str]], List[str]]:
        """执行修改操作"""
        new_sections = {k: v.copy() for k, v in sections.items()}
        results = []

        for instr in parsed_instructions:
            try:
                action = instr["action"]
                section = instr["section"].upper()
                target = instr["target"]
                properties = instr.get("properties", {})

                if section not in new_sections:
                    results.append(f"错误: 节 {section} 不存在")
                    continue

                # 获取当前节的参数映射
                param_map = INPModifier._get_section_param_map(section, new_sections[section])
                print(f"参数映射：{param_map}")

                if action == "modify":
                    modified = INPModifier._modify_section(new_sections[section], target, properties, param_map)
                    results.append(f"已修改 {section} 中的 {target}: {modified} 条记录")

                elif action == "add":
                    added = INPModifier._add_to_section(new_sections[section], target, properties, param_map)
                    results.append(f"已向 {section} 添加 {target}: {added}")

                elif action == "delete":
                    deleted = INPModifier._delete_from_section(new_sections[section], target)
                    results.append(f"已从 {section} 删除 {target}: {deleted} 条记录")

                else:
                    results.append(f"错误: 不支持的操作 {action}")

            except Exception as e:
                results.append(f"执行修改时出错: {str(e)}")

        return new_sections, results

    @staticmethod
    def _get_section_param_map(section: str, section_lines: List[str]) -> Dict[str, int]:
        """
        获取节的参数名到索引的映射
        优先从节的注释行提取，失败则使用预定义的标准参数
        """
        # 尝试从注释行提取参数信息
        for line in section_lines[:5]:  # 检查前5行，通常注释在开头
            stripped_line = line.strip()
            if stripped_line.startswith((';;', ';')):  # 注释行
                # 提取注释中的参数名
                param_line = stripped_line.lstrip(';').strip()
                params = re.split(r'\s+', param_line)
                if params and len(params) > 1:  # 确保提取到有效参数
                    return {param.lower(): idx for idx, param in enumerate(params)}

        # 如果没有找到注释行，使用预定义的标准参数
        section_lower = section.lower()
        for std_section, params in INPModifier._SECTION_PARAMS.items():
            if std_section.lower() == section_lower:
                return {param.lower(): idx for idx, param in enumerate(params)}

        # 如果是未知节，返回默认映射（假设第一个参数是ID/名称）
        return {"name": 0}


    @staticmethod
    def _find_target_lines(section_lines: List[str], target: str, param_map: Dict[str, int]) -> List[int]:
        """找到目标ID/名称所在行的索引"""
        target_str = str(target).strip()
        # 确定名称参数的索引（默认为0）
        name_index = param_map.get("name", 0)
        target_indices = []

        for i, line in enumerate(section_lines):
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith((';;', ';')):  # 跳过注释和空行
                continue

            parts = line.split()
            if len(parts) > name_index and parts[name_index] == target_str:
                target_indices.append(i)

        return target_indices


    @staticmethod
    def _modify_section(section_lines: List[str], target: [str, int], properties: Dict, param_map: Dict[str, int]) -> int:
        """修改节中的记录 - 基于动态参数映射"""
        target_indices = INPModifier._find_target_lines(section_lines, target, param_map)
        print(f"目标行索引：{target_indices}" )
        modified_count = 0

        for i in target_indices:
            print(f"目标行(修改前)：{section_lines[i]}")
            modified_line = INPModifier._update_line(section_lines[i], properties, param_map)
            section_lines[i] = modified_line
            print(f"目标行(修改后)：{modified_line}")
            modified_count += 1

        return modified_count


    @staticmethod
    def _update_line(line: str, properties: Dict, param_map: Dict[str, int]) -> str:
        """更新行内容 - 基于动态参数映射"""
        parts = line.split()  # 分割后得到的是字符串列表

        for key, value in properties.items():
            key_lower = key.lower()
            if key_lower not in param_map:
                continue

            param_index = param_map[key_lower]
            value_str = str(value).strip()

            if param_index >= len(parts):
                # 计算需要补充的空字符串数量
                add_count = param_index - len(parts) + 1
                parts.extend([""] * add_count)

            parts[param_index] = value_str

        return '       '.join(parts)


    @staticmethod
    def _add_to_section(section_lines: List[str], target: str, properties: Dict, param_map: Dict[str, int]) -> str:
        """向节中添加新记录 - 基于动态参数映射"""
        new_line = INPModifier._build_line(target, properties, param_map)

        # 尝试找到数据开始的位置（跳过注释行）
        insert_pos = len(section_lines)  # 默认添加到末尾
        for i, line in enumerate(section_lines):
            stripped_line = line.strip()
            if stripped_line and not stripped_line.startswith((';;', ';')):
                insert_pos = i
                break

        section_lines.insert(insert_pos, new_line)
        return new_line

    @staticmethod
    def _delete_from_section(section_lines: List[str], target: str) -> int:
        """从节中删除记录"""
        target_str = str(target).strip()
        original_count = len(section_lines)

        # 构建新的行列表，排除匹配目标的行
        section_lines[:] = [
            line for line in section_lines
            if not (line.strip() and not line.strip().startswith((';;', ';')) and
                    line.split()[0] == target_str)
        ]

        return original_count - len(section_lines)





    @staticmethod
    def _build_line(id: str, properties: Dict, param_map: Dict[str, int]) -> str:
        """构建新行 - 基于动态参数映射"""
        # 确定需要多少个参数位置
        max_index = max(param_map.values()) if param_map else 0
        parts = ["0"] * (max_index + 1)

        # 设置ID/名称
        name_index = param_map.get("name", 0)
        if name_index < len(parts):
            parts[name_index] = id
        else:
            parts.append(id)

        # 设置属性值
        for key, value in properties.items():
            key_lower = key.lower()
            if key_lower in param_map:
                param_index = param_map[key_lower]
                if param_index < len(parts):
                    parts[param_index] = str(value)
                else:
                    parts.append(str(value))

        return '         '.join(parts)

    @staticmethod
    def query_section(section_lines: List[str], target: [str, int], param_map: Optional[Dict[str, int]] = None) -> List[Dict]:
        """查询节中的记录 - 基于动态参数映射"""
        if not param_map:
            # 如果没有提供参数映射，自动生成
            # 这里需要知道节名才能生成准确映射，实际使用时应传入正确的节名
            # 简化处理：假设是JUNCTIONS节
            param_map = INPModifier._get_section_param_map("JUNCTIONS", section_lines)

        target_indices = INPModifier._find_target_lines(section_lines, target, param_map)
        results = []

        # 创建反向映射：索引 -> 参数名
        index_to_param = {v: k for k, v in param_map.items()}

        for i in target_indices:
            line = section_lines[i]
            parts = line.split()
            record = {}

            for idx, value in enumerate(parts):
                # 找到参数名，如果没有则使用"paramX"的形式
                param_name = index_to_param.get(idx, f"param{idx}")
                record[param_name] = value

            results.append(record)

        return results