import re
from typing import Dict, List

# INP文件解析器
class INPParser:
    @staticmethod
    def parse(inp_content: str) -> Dict[str, List[str]]:
        """解析INP文件为节字典"""
        sections = {}
        current_section = None
        lines = inp_content.split('\n')

        for line in lines:
            # 匹配节标题，如[JUNCTIONS]
            section_match = re.match(r'^\[(.*?)\]$', line.strip())
            if section_match:
                current_section = section_match.group(1).upper()
                sections[current_section] = []
                continue

            if current_section and line.strip():
                sections[current_section].append(line.strip())

        return sections

    @staticmethod
    def to_string(sections: Dict[str, List[str]]) -> str:
        """将节字典转换回INP文本"""
        inp_lines = []
        for section, lines in sections.items():
            inp_lines.append(f"[{section}]")
            inp_lines.extend(lines)
            inp_lines.append("")  # 节之间空一行
        return '\n'.join(inp_lines).rstrip('\n')
