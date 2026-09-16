"""Chat Agent 的 Pydantic 结构化输出模型（Worker LLM 的输出 schema）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑪（被 ⑥ context_processor_node 调用）：
  - WorkerContextResult           —— Worker LLM 提炼结果的 Pydantic 模型
  - WorkerContextResult.sanitize_fact —— 字段校验器：防御性清洗 background_fact
  - WorkerContextResult.to_processed_context —— 转换为注入 Main LLM 的字符串

调用关系：graph.py::context_processor_node 把 Worker LLM 输出的 JSON 解析为 dict，
用 WorkerContextResult(**data) 校验+清洗，再调 to_processed_context() 拿到
processed_context 单句。本文件是数据模型层，无独立运行入口。

============================================================================
设计说明
  Worker LLM（context_processor_node）通过 prompt 内嵌 JSON schema 返回此结构，
  API 层面约束输出格式，避免 bullet 列表或长段落泄漏到 Main LLM。
  （注：本项目不使用 with_structured_output，因为 thinking 模型两种结构化方式都报 400，
   改为 prompt 内嵌 schema + 手动解析 + 此模型做二次校验清洗。）
"""
# re：正则清洗 background_fact（去 bullet 符号、合并空白、截断长度）
import re

# BaseModel/Field/field_validator：Pydantic v2 模型与字段校验器
from pydantic import BaseModel, Field, field_validator


class WorkerContextResult(BaseModel):
    """Worker LLM 从背景信息中提炼的与当前问题相关的事实。

    【功能 / 流程定位】
      总体流程 ⑪ 的数据载体。context_processor_node 解析 Worker LLM 的 JSON
      为本模型实例，再调 to_processed_context() 得到 processed_context。
      本模型构造结束后，调用方调 to_processed_context() 拿最终字符串 → 写入 state。

    【思路】
      字段说明会作为 tool/function schema 元数据传给模型，引导其按结构输出。
      has_relevant_context：是否找到相关背景；
      background_fact：单句关键事实（≤50 汉字），无关则留空。
    """

    # has_relevant_context：是否存在相关背景（bool）
    # description 会作为 schema 元数据引导模型输出
    has_relevant_context: bool = Field(
        description="背景信息中是否存在与用户当前问题直接相关的信息。无关则为 false。"
    )
    # background_fact：与当前问题直接相关的唯一关键事实
    # default=""：无关时留空；description 强约束"单句、问什么写什么"
    background_fact: str = Field(
        default="",
        description=(
            "与【当前问题】直接相关的唯一关键事实，单句自然语言，不超过50个汉字。"
            "问年龄只写年龄，问名字只写名字，问天气只写天气。"
            "严禁包含与当前问题无关的信息。无相关信息则留空。"
        ),
    )

    @field_validator("background_fact")
    @classmethod
    def sanitize_fact(cls, v: str) -> str:
        """防御性清洗：即使模型偶尔违规，也强制变成单句。

        【功能 / 流程定位】
          Pydantic 字段校验器，在 WorkerContextResult(**data) 构造时自动触发。
          校验结束后，background_fact 字段已是清洗后的单句文本。
          无"下一个函数"——这是模型字段赋值的守卫。

        【思路 / 代码流程】
          1. 空值直接返回 ""
          2. 去换行、去首部 bullet/序号/符号
          3. 把"无/none/N/A"等无意义占位转为 ""
          4. 合并多余空白，截断 80 字

        参数:
            v: 模型原始输出的 background_fact 字符串

        返回:
            清洗后的单句字符串（最长 80 字）
        """
        # 空值直接返回空串
        if not v:
            return ""
        # strip 去首尾空白；把换行符替换为空格（强制单行）
        text = v.strip().replace("\n", " ").replace("\r", " ")
        # 去掉首部 bullet 符号 / 序号 / 标点 / 标记：
        # [\s•\-\*\d\.\、\【\】\#]+ 匹配开头的空白/•/-/*/数字./、/【】/#
        text = re.sub(r"^[\s•\-\*\d\.\、\【\】\#]+", "", text).strip()
        # 无意义占位词统一转为空串
        if text in ("无", "无相关背景", "无相关背景。", "none", "N/A"):
            return ""
        # 合并多余空白为单个空格
        text = re.sub(r"\s+", " ", text)
        # 截断到 80 字（兜底防超长）
        return text[:80]

    def to_processed_context(self) -> str:
        """转换为注入 Main LLM 的 processed_context 字符串。

        【功能 / 流程定位】
          被 context_processor_node 调用，把模型实例转为最终字符串写入 state.processed_context。
          本函数结束后，调用方 context_processor 把返回值写入 state → chat_node 使用。
          这是一次请求"背景提炼"子链路的终点。

        【思路】
          has_relevant_context 为真且 background_fact 非空 → 返回 background_fact；
          否则返回空串（不注入背景）。

        返回:
            processed_context 字符串（单句事实 或 ""）
        """
        # 无相关背景或事实为空 → 返回空串（chat_node 不注入背景）
        if not self.has_relevant_context or not self.background_fact:
            return ""
        # 有相关背景 → 返回清洗后的单句事实
        return self.background_fact
