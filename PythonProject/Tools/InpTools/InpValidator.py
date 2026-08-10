from dataclasses import dataclass
from pathlib import Path

from Tools.InpTools.InpFileHandler import INPFileHandler
from Tools.InpTools.InpParser import INPParser


class InvalidInpFile(ValueError):
    pass


@dataclass(frozen=True)
class InpValidationResult:
    sections: dict[str, list[str]]
    encoding_message: str


def validate_inp_file(path: str | Path) -> InpValidationResult:
    file_path = Path(path)
    if file_path.suffix.lower() != ".inp":
        raise InvalidInpFile("仅支持 .inp 文件")

    content, message = INPFileHandler.read_file(str(file_path))
    if not content.strip():
        raise InvalidInpFile("INP 文件为空或无法读取")

    sections = INPParser.parse(content)
    if "OPTIONS" not in sections:
        raise InvalidInpFile("INP 文件缺少 [OPTIONS] 节")
    if len(sections) < 2:
        raise InvalidInpFile("INP 文件没有可用的模型数据节")

    return InpValidationResult(sections=sections, encoding_message=message)
