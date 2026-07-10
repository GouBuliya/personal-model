"""Pydantic models for the Persome HTTP REST API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ─── Generic envelope ──────────────────────────────────────────────────────


class ApiResponse(BaseModel):
    """Common response envelope for the local runtime API."""

    success: bool = Field(default=True, description="请求是否成功")
    data: dict | list | str | None = Field(default=None, description="响应数据")


class ErrorResponse(BaseModel):
    success: bool = Field(default=False, description="请求是否成功")
    error: str = Field(description="错误信息")
    detail: str | None = Field(default=None, description="详细错误信息")


# ─── Status ────────────────────────────────────────────────────────────────


class ModelPing(BaseModel):
    stage: str = Field(description="LLM 阶段名称，如 timeline/reducer/classifier/compact")
    model: str = Field(description="使用的模型名称")
    ok: bool = Field(description="该阶段模型是否可连通")
    latency_ms: int | None = Field(default=None, description="ping 延迟（毫秒）")
    error: str | None = Field(default=None, description="ping 失败时的错误信息")


class StatusResponse(BaseModel):
    version: str = Field(description="Persome 版本号")
    root: str = Field(description="数据根目录路径")
    daemon: str = Field(description="守护进程状态，如 'running pid 12345' 或 'stopped'")
    uptime: str = Field(description="运行时长，如 '2h 30m' 或 'stopped'")
    health: str = Field(description="健康标签：healthy/stale/running/stopped")
    capture: str = Field(description="捕获状态：active/paused")
    last_capture: str | None = Field(default=None, description="最近一次捕获时间描述")
    buffer: str | None = Field(default=None, description="缓冲区文件统计")
    sessions: str | None = Field(default=None, description="会话统计")
    memory: str | None = Field(default=None, description="记忆文件统计")
    timeline: str | None = Field(default=None, description="时间线块统计")
    models: dict[str, ModelPing] | None = Field(
        default=None, description="各阶段 LLM 连通性探测结果"
    )


# ─── Memory ────────────────────────────────────────────────────────────────


class MemoryFile(BaseModel):
    path: str = Field(description="记忆文件路径")
    description: str = Field(description="文件描述")
    tags: list[str] = Field(description="标签列表")
    status: str = Field(description="文件状态，如 active/dormant/archived")
    entry_count: int = Field(description="条目数量")
    created: str = Field(description="创建时间 ISO8601")
    updated: str = Field(description="更新时间 ISO8601")


class MemoryEntry(BaseModel):
    id: str = Field(description="条目 ID")
    timestamp: str = Field(description="条目时间戳 ISO8601")
    tags: list[str] = Field(description="标签列表")
    body: str = Field(description="条目正文内容")
    superseded_by: str | None = Field(default=None, description="被哪个条目替代")
    confidence: str | None = Field(
        default=None, description="记忆可靠度：high/medium/low（元认知层，缺省为未标注）"
    )
    conflicted: bool = Field(default=False, description="是否与其他记忆冲突且未裁决")
    occurred_at: str | None = Field(
        default=None, description="事件实际发生时间 ISO8601（区别于写入时间 timestamp）"
    )


class MemoryReadResponse(BaseModel):
    path: str = Field(description="文件路径")
    description: str = Field(description="文件描述")
    tags: list[str] = Field(description="标签列表")
    status: str = Field(description="文件状态")
    updated: str = Field(description="更新时间")
    entry_count: int = Field(description="条目数量")
    entries: list[MemoryEntry] = Field(description="条目列表")


# ─── Search ────────────────────────────────────────────────────────────────


class SearchHit(BaseModel):
    id: str = Field(description="条目 ID")
    path: str = Field(description="所属文件路径")
    timestamp: str = Field(description="时间戳 ISO8601")
    content: str = Field(description="匹配内容片段")
    rank: float = Field(description="BM25 相关性得分")


class CaptureHit(BaseModel):
    timestamp: str = Field(description="捕获时间戳 ISO8601")
    app_name: str = Field(description="应用名称")
    bundle_id: str = Field(description="应用 bundle ID")
    window_title: str = Field(description="窗口标题")
    url: str = Field(description="URL（如果有）")
    snippet: str = Field(description="匹配文本片段")
    rank: float = Field(description="BM25 相关性得分")
    file_stem: str = Field(description="捕获文件名（不含扩展名）")
    focused_role: str = Field(description="焦点元素角色")
    focused_value_preview: str = Field(description="焦点元素值预览（前 200 字符）")


# ─── Captures ──────────────────────────────────────────────────────────────


class CaptureHeadline(BaseModel):
    time: str = Field(description="捕获时间 HH:MM")
    app_name: str = Field(description="应用名称")
    window_title: str = Field(description="窗口标题")
    focused_role: str = Field(description="焦点元素角色")
    file_stem: str = Field(description="捕获文件名")


class CaptureFulltext(BaseModel):
    timestamp: str = Field(description="捕获时间戳 ISO8601")
    app_name: str = Field(description="应用名称")
    window_title: str = Field(description="窗口标题")
    url: str = Field(description="URL（如果有）")
    focused_role: str = Field(description="焦点元素角色")
    focused_value: str | None = Field(description="焦点元素值")
    visible_text: str = Field(description="可见文本内容")
    file_stem: str = Field(description="捕获文件名")


class TimelineBlock(BaseModel):
    start_time: str = Field(description="块起始时间 ISO8601")
    end_time: str = Field(description="块结束时间 ISO8601")
    entries: list[str] = Field(description="时间线条目列表（LLM 归一化后的结构化内容）")
    apps_used: list[str] = Field(description="该时段使用的应用列表")
    capture_count: int = Field(description="该时段捕获次数")


class CurrentContextResponse(BaseModel):
    recent_captures_headline: list[CaptureHeadline] = Field(description="最近捕获摘要列表")
    recent_captures_fulltext: list[CaptureFulltext] = Field(description="最近捕获全文列表")
    recent_timeline_blocks: list[TimelineBlock] = Field(description="最近时间线块列表")


class RecentCaptureResponse(BaseModel):
    timestamp: str | None = Field(default=None, description="捕获时间戳 ISO8601")
    file: str = Field(description="捕获文件名")
    app_name: str | None = Field(default=None, description="应用名称")
    bundle_id: str | None = Field(default=None, description="应用 bundle ID")
    window_title: str | None = Field(default=None, description="窗口标题")
    url: str | None = Field(default=None, description="URL")
    focused_element: dict = Field(description="焦点元素信息")
    visible_text: str = Field(description="可见文本内容")
    screenshot_stripped: bool = Field(description="截图是否已剥离")
    screenshot_b64: str | None = Field(default=None, description="截图 base64")
    screenshot_mime: str | None = Field(default=None, description="截图 MIME 类型")


class CaptureIngestBody(BaseModel):
    """Swift "Persome" 主程序推送的一帧 capture（``capture.source = "ingest"`` 模式）。

    采集层（AX 树 + 焦点窗口截图）已搬进持有 Accessibility / Screen-Recording 的 Swift
    进程；daemon 收到后只跑富化与落库，自身不再需要任何系统权限。字段与
    daemon 自采路径 ``_build_capture`` 的产物对齐，缺省宽松（缺字段降级，不崩）。
    """

    timestamp: str | None = Field(default=None, description="ISO8601 采集时间；缺省则服务端补")
    trigger: dict[str, Any] | None = Field(
        default=None, description="触发元数据 {event_type, bundle_id, window_title, details?}"
    )
    window_meta: dict[str, Any] = Field(
        default_factory=dict, description="{app_name, title, bundle_id}"
    )
    ax_tree: dict[str, Any] | None = Field(
        default=None, description="AX 树 raw_json（apps→windows→elements），缺省视为 AX 不可用"
    )
    ax_metadata: dict[str, Any] | None = Field(default=None, description="AX 采集元数据")
    screenshot: dict[str, Any] | None = Field(
        default=None,
        description="{image_base64, mime_type, width, height}（明文，由服务端按配置加密落盘）",
    )
    ocr_jpeg_b64: str | None = Field(
        default=None, description="AX 贫瘠窗口的焦点窗口截图 JPEG（base64），供本地 OCR 兜底"
    )
    ocr_tier: str | None = Field(default=None, description="OCR 档位覆盖；缺省用配置值")
