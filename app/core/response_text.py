from __future__ import annotations

from typing import Any


STATUS_TEXT: dict[str, str] = {
    "ok": "正常",
    "unsupported": "不支持",
    "uploaded": "已上传",
    "queued": "排队中",
    "running": "转换中",
    "success": "成功",
    "failed": "失败",
    "timeout": "超时",
    "cancelled": "已取消",
}

STAGE_TEXT: dict[str, str] = {
    "created": "已创建",
    "queued": "排队中",
    "validating": "校验文件",
    "converting": "转换中",
    "completed": "已完成",
    "failed": "失败",
    "timeout": "超时",
    "cancelled": "已取消",
    "interrupted": "已中断",
}

ERROR_MESSAGE_TEXT: dict[str, str] = {
    "empty_file": "请上传文件",
    "empty_filename": "文件名不能为空",
    "unsupported_file_format": "不支持的文件格式",
    "file_too_large": "文件超过上传大小限制",
    "upload_save_failed": "上传文件保存失败",
    "convert_failed": "文档转换失败",
    "convert_timeout": "文档转换超时",
    "converter_dependency_missing": "文档转换依赖未安装",
    "ocr_model_missing": "OCR模型未配置或不完整",
    "ppstructure_unavailable": "PP-StructureV3服务不可用",
    "ppstructure_failed": "PP-StructureV3解析失败",
    "ppstructure_timeout": "PP-StructureV3调用超时",
    "ppstructure_invalid_response": "PP-StructureV3响应结构不合法",
    "text_decode_failed": "文本文件解码失败",
    "invalid_file_id": "文件ID不合法",
    "invalid_task_id": "任务ID不合法",
    "asset_not_found": "附件不存在或名称不合法",
    "document_not_found": "文档不存在",
    "markdown_not_found": "Markdown结果不存在",
    "upload_not_found": "原始文件不存在",
    "cache_invalid": "缓存转换结果无效",
    "invalid_date_range": "日期范围不合法",
    "task_not_found": "任务不存在",
    "task_not_cancellable": "只有排队中的任务可以取消",
    "task_not_retryable": "排队中或转换中的任务不能重试",
    "task_is_running": "运行中的任务不能删除",
    "document_has_active_task": "文档存在进行中的转换任务",
    "service_restarted": "服务重启，任务已中断",
    "unauthorized": "请先登录",
    "invalid_credentials": "用户名或密码错误",
}

MESSAGE_TEXT: dict[str, str] = {
    "file is required": "请上传文件",
    "file is empty": "文件内容为空",
    "file is too large": "文件超过上传大小限制",
    "filename is required": "文件名不能为空",
    "unsupported file format": "不支持的文件格式",
    "file_id must be a md5 value": "文件ID必须是MD5值",
    "file_id is invalid": "文件ID不合法",
    "task_id is invalid": "任务ID不合法",
    "asset name is required": "附件名称不能为空",
    "invalid asset name": "附件名称不合法",
    "failed to save uploaded file": "上传文件保存失败",
    "document conversion failed": "文档转换失败",
    "document conversion timed out": "文档转换超时",
    "docling conversion failed": "Docling转换失败",
    "docx conversion failed": "DOCX转换失败",
    "docling is not installed": "Docling未安装",
    "PP-StructureV3 service is not configured": "PP-StructureV3服务未配置",
    "PP-StructureV3 service is unavailable": "PP-StructureV3服务不可用",
    "PP-StructureV3 conversion failed": "PP-StructureV3解析失败",
    "PP-StructureV3 conversion timed out": "PP-StructureV3调用超时",
    "PP-StructureV3 response is invalid": "PP-StructureV3响应结构不合法",
    "failed to decode text file": "文本文件解码失败",
    "metadata is unavailable": "元数据不可用",
    "markdown not found": "Markdown结果不存在",
    "document not found": "文档不存在",
    "asset not found": "附件不存在",
    "uploaded file not found": "原始文件不存在",
    "cached conversion result is invalid": "缓存转换结果无效",
    "document has an active conversion task": "文档存在进行中的转换任务",
    "date range is invalid": "日期范围不合法",
    "task not found": "任务不存在",
    "task is waiting for conversion": "任务等待转换",
    "retry task is waiting for conversion": "重试任务等待转换",
    "reconvert task is waiting for conversion": "重新转换任务等待转换",
    "file validation completed": "文件校验完成",
    "document conversion started": "开始转换文档",
    "document conversion completed": "文档转换完成",
    "document conversion completed from cache": "命中缓存，转换完成",
    "only queued tasks can be cancelled": "只有排队中的任务可以取消",
    "queued or running tasks cannot be retried": "排队中或转换中的任务不能重试",
    "running task cannot be deleted": "运行中的任务不能删除",
    "task was cancelled": "任务已取消",
    "task was cancelled before deletion": "任务删除前已取消",
    "task was interrupted by service restart": "服务重启，任务已中断",
    "failed to delete one output directory": "有一个输出目录删除失败",
    "login is required": "请先登录",
    "session is invalid or expired": "会话无效或已过期",
    "username or password is incorrect": "用户名或密码错误",
    "docling failed for docx; used python-docx fallback": "Docling处理DOCX失败，已使用python-docx兜底转换",
}


def status_text(status: str | None) -> str:
    if not status:
        return ""
    return STATUS_TEXT.get(status, status)


def stage_text(stage: str | None) -> str:
    if not stage:
        return ""
    return STAGE_TEXT.get(stage, stage)


def translate_message(message: Any, error_code: str | None = None) -> Any:
    if message is None:
        return None
    text = str(message)
    if text in MESSAGE_TEXT:
        return MESSAGE_TEXT[text]
    if any(ord(char) > 127 for char in text):
        return text
    if error_code and error_code in ERROR_MESSAGE_TEXT:
        return ERROR_MESSAGE_TEXT[error_code]
    return text


def translate_warnings(warnings: list[Any]) -> list[Any]:
    return [translate_message(warning) for warning in warnings]


def api_error_detail(error_code: str, message: str, response_status: str | None = None) -> dict[str, str]:
    status_value = response_status or ("unsupported" if error_code == "unsupported_file_format" else "failed")
    return {
        "status": status_value,
        "status_text": status_text(status_value),
        "error_code": error_code,
        "message": translate_message(message, error_code),
    }
