---
title: "GPT Image 2 轻量 Windows GUI 批处理应用项目实施计划书"
subtitle: "面向开发 Agent 的需求、架构、任务与验收规范"
author: "ChatGPT"
date: "2026-05-18"
lang: zh-CN
---

# 文档使用说明

本文档是给开发 Agent / 编码 Agent 阅读和执行的项目实施计划书。目标不是只描述概念，而是把需求、架构、任务拆分、验收标准、接口约束、异常处理和可扩展能力写到可以直接进入实现的程度。

开发 Agent 执行时应遵守以下原则：

1. 先实现可运行闭环，再扩充体验功能。
2. 以 OpenAI Image API 为主，不把 Responses API 作为 MVP 依赖。
3. GUI 必须能够生成可复制、可保存、可独立执行的命令，并且 GUI 本身也能执行该命令。
4. 命令中不得明文携带 API Key；使用环境变量或 Windows 凭据存储。
5. 所有批处理任务必须可暂停、可取消、可恢复、可重试，并且有 manifest 记录。
6. 所有模型能力、参数取值与限制必须集中在 `api_capabilities.json` 或同等配置中，不要散落硬编码。
7. 若官方文档和本计划出现差异，以官方文档为准，并在代码中用能力配置隔离差异。

# 1. 项目摘要

## 1.1 产品目标

实现一个轻量 Windows GUI 应用，用于批量调用 `gpt-image-2` 进行图像生成和图像编辑。用户可以在界面中选择输入图片文件夹、输出文件夹、模型参数、提示词、输出格式和并发度；应用会根据配置自动生成可用命令，展示给用户审核，并在用户点击执行后运行该命令，实时显示进度、日志、预览图、最终图和失败原因。

应用最终应满足以下一句话价值主张：

> 非技术用户可以通过点选文件夹和配置参数，批量生成或编辑图片；技术用户可以复制同一套命令在 PowerShell、CI 或其他自动化脚本中复现相同任务。

## 1.2 推荐产品形态

建议采用“双模式单可执行文件”结构：

```text
GptImageBatch.exe gui
GptImageBatch.exe run --config "C:\jobs\job.config.json" --input-dir "D:\input" --output-dir "D:\output" --concurrency 3
```

其中：

- `gui` 模式启动 Windows 桌面界面。
- `run` 模式作为命令行批处理执行器。
- GUI 负责生成配置 JSON 与命令。
- 执行器负责扫描文件、调用 API、处理并发、保存图片、输出 JSONL 进度事件。
- GUI 执行命令时以子进程方式运行自身的 `run` 模式，并解析 JSONL 事件更新界面。

这样可以同时满足“轻量 GUI”和“命令可复制、可审计、可独立运行”的需求，也能减少 GUI 与核心执行逻辑耦合。

## 1.3 API 选择

MVP 默认使用 OpenAI Image API，而不是 Responses API。原因是本项目的核心是文件夹批处理、参数配置、命令生成与执行，属于“单 prompt 生成或编辑单批图片”的执行型场景。官方图像生成指南说明，Image API 提供 generations 与 edits 两类端点；如果只需要从一个 prompt 生成或编辑单张图，Image API 是最佳选择；如果要构建对话式、可持续编辑的体验，再使用 Responses API。

后续可以作为增强能力增加 Responses API 多轮编辑模式，但不要在 MVP 中引入。

# 2. 官方文档依据与设计推导

本计划主要参考以下官方文档：

- OpenAI Image Generation Guide：`https://developers.openai.com/api/docs/guides/image-generation?multi-turn=imageid&api=image`
- OpenAI Images API Reference：`https://developers.openai.com/api/reference/resources/images`
- OpenAI API Pricing：`https://developers.openai.com/api/docs/pricing`

## 2.1 文档要点到产品需求的映射

| 官方文档要点 | 对产品的设计影响 | 需要落地的功能 |
|---|---|---|
| Image API 提供 generations 与 edits 两类能力 | 应用必须区分“文本生成”和“基于输入图编辑/参考生成”模式 | 模式选择：Text-to-Image、Edit/Reference、Mask/Inpaint |
| Image API 适合单 prompt 生成或编辑；Responses API 适合对话式、多轮体验 | MVP 应走 Image API，Responses API 作为未来扩展 | API 层接口先抽象，预留 `responses_adapter.py` |
| generations 可通过 `n` 一次返回多张图 | 同一 prompt 可批量生成多张候选 | 支持“每个任务生成张数/variants”参数 |
| edits 可使用一张或多张参考图，也可配合 mask | 输入文件夹中的图片可以作为参考或待编辑图 | 支持输入图列表、参考图分组、mask 文件夹匹配 |
| `gpt-image-2` 的输入图会自动高保真处理，`input_fidelity` 不应暴露为可调参数 | GUI 不提供 `input_fidelity` 设置 | 文档说明该参数被刻意隐藏 |
| 支持 `size`、`quality`、`output_format`、`output_compression`、`background` 等输出设置 | 参数面板必须覆盖所有常用输出参数 | 参数校验器、默认值、说明 tooltip |
| `gpt-image-2` 不支持透明背景 | 对该模型禁止 `background=transparent` | UI 中只允许 `auto`、`opaque` |
| Image API 返回 base64 图片数据 | 本地必须解码保存文件 | `OutputWriter` 负责 base64 解码、命名、写入 |
| 流式生成可接收 0 到 3 张 partial images | GUI 可实现过程预览并可选保存中间图 | `stream`、`partial_images`、`save_partials` |
| 每张 partial image 会额外产生 image output tokens | 成本估算要单独显示 partial image 成本 | 成本预估、运行后 usage 汇总 |
| 复杂 prompt 可能有较高延迟，模型在文字、构图、长期一致性上仍有局限 | UI 要有超时、重试、失败说明和用户提示 | 任务级超时、友好错误、提示词建议 |

# 3. 目标用户与核心场景

## 3.1 用户画像

| 用户 | 需求 | 关键体验 |
|---|---|---|
| 电商运营 | 批量把商品图改成统一风格、背景或海报图 | 选择商品图文件夹，配置 prompt，一键输出 |
| 设计师 | 对同一组图片做风格化实验 | 快速改参数、保存配置、对比结果 |
| 内容创作者 | 批量生成封面图、插图或社媒图 | 无需写代码，能保留命令复现 |
| 开发者 | 将图片生成流程纳入脚本或流水线 | GUI 生成命令，复制到 PowerShell 或 CI |
| 提示词调试人员 | 反复测试 size、quality、format、prompt 组合 | 支持 dry-run、局部重跑、日志和 usage 记录 |

## 3.2 核心用户故事

### 场景 A：文件夹图片批量编辑

用户选择 `D:\source_images` 作为输入文件夹，选择 `D:\outputs` 作为输出文件夹，输入 prompt：“保持商品主体不变，将背景替换为纯白摄影棚背景，柔和阴影，电商主图风格。”用户设置并发度为 3，输出格式为 `webp`，质量为 `medium`。点击“生成命令”，GUI 展示命令；点击“执行”，应用开始批处理，每张图保存一个输出文件，并写入 manifest。

### 场景 B：文本批量生图

用户不选择输入文件夹，只输入 prompt 模板与生成数量，例如“生成 20 张儿童绘本风格的森林动物插画”。应用自动创建 20 个任务，并按照 `n` 或任务拆分策略执行。

### 场景 C：输入图作为参考生成新图

用户选择一组图片，应用把每张图片作为参考图，使用 prompt 生成同主题新图，例如“以这张图片中的产品为参考，生成一张节日促销海报”。输出保存在按源文件名命名的子目录中。

### 场景 D：mask 局部重绘

用户选择原图文件夹和 mask 文件夹，mask 文件名与原图文件名同名或使用 `_mask` 后缀。应用在执行前验证 mask 与原图格式、尺寸和 alpha 通道，并提示不合格文件。

### 场景 E：流式预览和保存中间图

用户开启 `stream=true` 与 `partial_images=2`，应用在每个任务生成过程中展示中间预览，并根据 `save_partials=true` 把中间图保存到 `partials` 子目录。

### 场景 F：任务中断后恢复

用户执行到一半关闭应用。下次打开同一 job，应用读取 `manifest.jsonl`，自动识别已成功、失败和未执行的任务，允许“仅重跑失败项”或“跳过已有输出继续执行”。

# 4. 项目范围

## 4.1 MVP 必须实现

1. Windows GUI 启动与基本布局。
2. 输入文件夹选择、输出文件夹选择。
3. 图片扫描、过滤、预览、任务队列生成。
4. Prompt 编辑器，支持全局 prompt 与文件变量。
5. 参数配置：模型、尺寸、质量、格式、压缩、背景、审核强度、流式、中间图数量、生成张数、并发度、超时、重试次数。
6. 命令生成、复制、保存为 `.ps1` 或 `.json`。
7. GUI 执行生成命令，并实时显示任务进度。
8. Image API generations 和 edits 调用。
9. base64 解码保存最终图。
10. 可选保存 partial images。
11. JSONL manifest、运行日志、错误日志、配置快照。
12. 暂停、取消、重试失败项、恢复任务。
13. API Key 安全读取，不在命令或日志中明文出现。
14. Windows 打包为单文件或便携目录。

## 4.2 增强版应实现

1. 拖拽文件夹到 GUI。
2. 配置 profile 保存、导入、导出。
3. prompt 模板变量：`{filename}`、`{stem}`、`{index}`、`{width}`、`{height}`、`{exif_date}`。
4. CSV per-file prompt 映射。
5. 结果图库、前后图对比、缩略图缓存。
6. 运行前成本估算，运行后 token 与成本汇总。
7. 自动预检：API key、网络、文件大小、mask、参数合法性、输出目录权限。
8. 输出命名模板。
9. 动态并发降级：遇到限流或高失败率自动降低并发。
10. 失败原因聚合报表。
11. 单图测试按钮：先对选中的 1 张图跑一遍，再批量执行。
12. PowerShell/curl/Python SDK 单任务样例导出。
13. 任务完成后打开输出文件夹。
14. 自动保存最近项目。
15. 可选删除中间临时文件。
16. 批量重命名与覆盖策略。
17. 主题：浅色/深色。
18. Windows 通知提示。

## 4.3 暂不纳入 MVP

1. 云端账号体系或多人协作。
2. 内置复杂图像编辑器。
3. 完整 DAM 资产管理系统。
4. 非 Windows 平台适配。
5. Responses API 多轮上下文编辑。
6. 视频生成。
7. 自动购买/管理 API 额度。

# 5. 技术选型建议

## 5.1 推荐栈

| 层 | 推荐技术 | 理由 |
|---|---|---|
| GUI | Python + PySide6 | 轻量、跨平台能力强、打包成熟、适合快速实现 |
| CLI 执行器 | Python + Typer 或 argparse | 易于与 GUI 共享核心逻辑 |
| API | OpenAI Python SDK + `AsyncOpenAI` | 支持异步并发、流式事件、对象模型 |
| 配置模型 | Pydantic | 参数校验、默认值、JSON Schema |
| 图片处理 | Pillow | 读取尺寸、格式转换、mask alpha 验证、缩略图 |
| 安全存储 | keyring | Windows Credential Manager 支持 |
| 重试 | tenacity 或自写指数退避 | 处理 429/5xx/超时 |
| 日志 | loguru 或标准 logging | JSONL 事件与调试日志 |
| 打包 | PyInstaller | 输出 Windows 可执行文件 |
| 测试 | pytest + pytest-qt | 核心逻辑和 GUI 基本测试 |
| 文档 | Markdown + 内置帮助页面 | 方便 Agent 和用户阅读 |

## 5.2 为什么不推荐一开始使用 WPF/WinUI

.NET WPF/WinUI 也适合 Windows 原生 GUI，但本项目的核心复杂度在 API 编排、批处理、文件与图片处理、命令生成、流式事件和 Python SDK 使用。Python + PySide6 能最大化复用 OpenAI SDK 与 Pillow，缩短 MVP 时间。如果后续需要更强 Windows 原生体验，可以保留核心 runner，用 WPF 重写 GUI 壳层。

# 6. 产品界面设计

## 6.1 主窗口布局

建议主窗口分为五个区域：

```text
┌────────────────────────────────────────────────────────────────────┐
│ 顶部栏：API 状态 | 当前 Profile | 官方文档链接 | 设置              │
├───────────────┬───────────────────────────────┬────────────────────┤
│ 左侧：输入输出 │ 中部：参数与 prompt            │ 右侧：预览/图库     │
│ - 输入文件夹   │ - 模式选择                    │ - 当前输入图         │
│ - mask 文件夹  │ - prompt 编辑器               │ - partial 预览       │
│ - 输出文件夹   │ - 模型与输出参数              │ - 最终图预览         │
│ - 文件过滤     │ - 并发/重试/超时              │ - 前后对比           │
├───────────────┴───────────────────────────────┴────────────────────┤
│ 队列表格：文件 | 状态 | 输出 | 尝试 | 耗时 | tokens | 错误         │
├────────────────────────────────────────────────────────────────────┤
│ 底部栏：预检 | 生成命令 | 复制命令 | 保存命令 | 执行 | 暂停 | 停止 │
└────────────────────────────────────────────────────────────────────┘
```

## 6.2 页面与组件

### 6.2.1 输入输出面板

必须包含：

- 输入模式：
  - 无输入图：Text-to-Image。
  - 输入文件夹：每张图片作为编辑目标或参考图。
  - 参考图组：多张图片合成一个任务。
  - mask 模式：原图 + mask。
- 输入文件夹选择按钮。
- 输出文件夹选择按钮。
- 可选 mask 文件夹选择按钮。
- 是否递归扫描。
- 文件扩展名过滤：`.png`、`.jpg`、`.jpeg`、`.webp`。
- 跳过隐藏文件。
- 跳过已成功输出文件。
- 文件数量统计。
- 预检结果摘要。

### 6.2.2 Prompt 编辑器

必须支持：

- 多行 prompt。
- 变量插入按钮。
- Prompt 模板预览。
- 单图测试时显示渲染后的 prompt。
- 常用 prompt 片段收藏。
- 禁止空 prompt 执行。
- 支持从 `.txt` 或 `.csv` 导入 prompt。

变量建议：

| 变量 | 含义 |
|---|---|
| `{filename}` | 原始文件名含扩展名 |
| `{stem}` | 原始文件名不含扩展名 |
| `{index}` | 批处理序号 |
| `{width}` | 输入图宽度 |
| `{height}` | 输入图高度 |
| `{input_dir}` | 输入文件夹名 |
| `{date}` | 当前日期 |
| `{profile}` | 当前配置名 |

### 6.2.3 参数面板

应按分组展示：

**模型与 API**

- API 类型：Image API。
- 模型：默认 `gpt-image-2`。
- 端点模式：Generate / Edit / Inpaint。
- 审核强度：`auto` / `low`。
- API Key 来源状态：环境变量 / Windows 凭据 / 本次会话。

**输出图像**

- 尺寸：`auto`、常用尺寸、自定义宽高。
- 质量：`auto`、`low`、`medium`、`high`。
- 输出格式：`png`、`jpeg`、`webp`。
- 压缩：0 到 100，仅 JPEG/WebP 启用。
- 背景：`auto`、`opaque`；对 `gpt-image-2` 禁止 `transparent`。
- 每任务生成张数：`n`。
- 输出命名模板。

**执行策略**

- 并发度：默认 2，范围建议 1 到 8。
- 重试次数：默认 2。
- 超时秒数：默认 240。
- 流式：开/关。
- 中间图数量：0 到 3。
- 保存中间图：开/关。
- 失败策略：继续 / 停止 / 达到失败率停止。
- 覆盖策略：跳过 / 覆盖 / 自动加后缀。

### 6.2.4 命令预览面板

显示三类内容：

1. 本地 runner 命令：用于实际执行。
2. 单个任务的 curl 或 PowerShell 示例：用于开发者理解 API 调用。
3. 配置 JSON：用于长期保存和复现。

命令预览必须支持：

- 复制到剪贴板。
- 保存为 `.ps1`。
- 保存配置为 `.json`。
- 显示“此命令不包含 API Key”的提示。
- 显示 dry-run 命令。

### 6.2.5 队列与日志

队列表格字段：

| 字段 | 描述 |
|---|---|
| index | 任务序号 |
| source | 输入文件或生成任务名 |
| status | pending/running/succeeded/failed/skipped/canceled |
| output | 输出文件路径 |
| attempt | 当前尝试次数 |
| duration | 耗时 |
| input_tokens | 输入 tokens |
| output_tokens | 输出 tokens |
| total_tokens | 总 tokens |
| request_id | API 请求 ID，如 SDK 可获取 |
| error | 错误摘要 |

日志面板：

- 普通日志。
- 错误日志。
- JSONL 事件。
- API usage 汇总。
- 可按任务过滤。
- 可一键打开日志目录。

# 7. API 参数设计

## 7.1 参数表

| GUI 字段 | 内部配置字段 | OpenAI 参数 | 默认值 | 校验规则 | 说明 |
|---|---|---|---|---|---|
| 模型 | `model` | `model` | `gpt-image-2` | 必须在 capabilities 中 | 初期只暴露 `gpt-image-2` |
| Prompt | `prompt_template` | `prompt` | 空 | 非空，渲染后长度合理 | 支持变量 |
| 任务模式 | `mode` | endpoint | `edit` | `generate/edit/inpaint` | 决定调用 generations 或 edits |
| 输入图 | `input_images` | `image` / `image[]` | 空 | 存在、可读、格式支持 | edit/reference/inpaint 使用 |
| Mask | `mask_path` | `mask` | 空 | 尺寸与原图一致，含 alpha | 仅 inpaint |
| 尺寸 | `size` | `size` | `auto` | auto 或合法 WxH | 自定义尺寸按 gpt-image-2 约束校验 |
| 质量 | `quality` | `quality` | `auto` | auto/low/medium/high | low 用于草稿 |
| 输出格式 | `output_format` | `output_format` | `png` | png/jpeg/webp | JPEG 延迟通常更低 |
| 压缩 | `output_compression` | `output_compression` | 90 | 0-100 | 仅 JPEG/WebP 可用 |
| 背景 | `background` | `background` | `auto` | auto/opaque | gpt-image-2 不允许 transparent |
| 审核强度 | `moderation` | `moderation` | `auto` | auto/low | 由用户选择 |
| 每任务生成张数 | `n` | `n` | 1 | 1-10，按 API 能力配置 | 输出命名需带序号 |
| 流式 | `stream` | `stream` | false | bool | 开启后解析事件 |
| 中间图数量 | `partial_images` | `partial_images` | 0 | 0-3 | 只在 stream=true 时生效 |
| 保存中间图 | `save_partials` | 无 | false | bool | 应用层功能 |
| 并发度 | `concurrency` | 无 | 2 | 1-8 | 应用层信号量 |
| 重试次数 | `max_retries` | 无 | 2 | 0-5 | 应用层 |
| 超时 | `timeout_seconds` | 无 | 240 | 30-600 | 应用层 |
| 输出命名 | `filename_template` | 无 | `{stem}_{index}` | 不含非法字符 | 应用层 |

## 7.2 尺寸校验

对 `gpt-image-2`，应用应支持：

- `auto`。
- 常用尺寸：`1024x1024`、`1536x1024`、`1024x1536`、`2048x2048`、`2048x1152`、`3840x2160`、`2160x3840`。
- 自定义尺寸，但必须满足：
  - 最大边不超过 3840 px。
  - 宽和高均为 16 的倍数。
  - 长边与短边比例不超过 3:1。
  - 总像素在 655,360 到 8,294,400 之间。

如果输入不合法，GUI 应在参数区直接显示错误，不允许生成命令执行。

## 7.3 格式与压缩规则

- `png`：默认格式，适合无损保存；禁用 `output_compression` 控件或标记为“不适用”。
- `jpeg`：适合预览、低延迟、体积控制；启用压缩。
- `webp`：适合网页素材；启用压缩。
- 所有返回图片均从 base64 解码保存，不依赖 URL。

# 8. 输入、输出与文件结构

## 8.1 输入文件发现

扫描策略：

1. 用户选择输入文件夹。
2. 根据扩展名过滤图片。
3. 根据递归选项遍历子目录。
4. 跳过隐藏文件和临时文件。
5. 用 Pillow 读取基本元数据：宽、高、格式。
6. 生成任务列表。
7. 若启用 mask 模式，按文件名匹配 mask。

文件匹配规则：

```text
原图: product_001.png
可接受 mask:
- product_001.png
- product_001_mask.png
- product_001.mask.png
```

如果有多个候选 mask，按上面优先级选择；若仍冲突，任务标为 validation_failed，并在预检报告中要求用户处理。

## 8.2 输出目录结构

每次执行创建一个 job 目录：

```text
output_root/
  job-20260518-153012/
    config.snapshot.json
    command.ps1
    manifest.jsonl
    summary.json
    logs/
      app.log
      events.jsonl
      errors.jsonl
    final/
      image001_v1.png
      image002_v1.png
    partials/
      image001/
        partial_0.png
        partial_1.png
    failed/
      image003.error.json
    thumbnails/
      image001.jpg
```

如果用户选择“输出到根目录”，也必须保存 `manifest.jsonl` 和 `config.snapshot.json`，以便恢复与审计。

## 8.3 Manifest 字段

`manifest.jsonl` 每行记录一个任务的最终或阶段状态。建议字段：

```json
{
  "job_id": "job-20260518-153012",
  "task_id": "000001",
  "source_path": "D:/input/image001.png",
  "mask_path": null,
  "prompt": "rendered prompt text",
  "mode": "edit",
  "status": "succeeded",
  "attempt": 1,
  "output_files": ["D:/output/job/final/image001_v1.png"],
  "partial_files": ["D:/output/job/partials/image001/partial_0.png"],
  "params": {
    "model": "gpt-image-2",
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png"
  },
  "usage": {
    "input_tokens": 0,
    "image_tokens": 0,
    "text_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0
  },
  "started_at": "2026-05-18T15:30:12-05:00",
  "finished_at": "2026-05-18T15:31:20-05:00",
  "duration_ms": 68000,
  "request_id": null,
  "error": null
}
```

# 9. 命令生成与执行

## 9.1 默认命令格式

GUI 点击“生成命令”后应产生以下格式：

```powershell
$env:OPENAI_API_KEY = "<请在本机环境变量或凭据管理器中配置，不要写入脚本>"
.\GptImageBatch.exe run `
  --config "D:\output\job-20260518-153012\config.snapshot.json" `
  --input-dir "D:\source_images" `
  --output-dir "D:\outputs" `
  --concurrency 3 `
  --events-jsonl
```

实际保存的 `command.ps1` 不应写入 API Key。可以写注释提示：

```powershell
# 请先设置 OPENAI_API_KEY，或在 GUI 设置页保存到 Windows Credential Manager。
```

## 9.2 Dry-run 命令

```powershell
.\GptImageBatch.exe run `
  --config "D:\jobs\config.json" `
  --input-dir "D:\source_images" `
  --output-dir "D:\outputs" `
  --dry-run
```

dry-run 必须输出：

- 将要执行的任务数量。
- 输入文件数量。
- 被跳过的文件和原因。
- 参数校验结果。
- mask 匹配结果。
- 估算输出文件名。
- 估算成本范围。
- 是否可执行。

## 9.3 GUI 执行策略

1. GUI 生成配置快照。
2. GUI 生成命令。
3. 用户点击执行。
4. GUI 通过 `QProcess` 启动命令，不使用 `shell=True`。
5. runner 以 JSONL 输出事件到 stdout。
6. GUI 解析事件，更新任务队列与预览。
7. runner 日志写入 job 目录。
8. GUI 可发送 cancel/pause 信号，或通过 job control 文件实现暂停。

## 9.4 JSONL 事件协议

runner 输出事件示例：

```json
{"event":"job_started","job_id":"job-20260518-153012","total_tasks":52}
{"event":"task_started","task_id":"000001","source_path":"D:/input/a.png"}
{"event":"partial_saved","task_id":"000001","partial_index":0,"path":"D:/output/partials/a/partial_0.png"}
{"event":"task_succeeded","task_id":"000001","output_files":["D:/output/final/a_v1.png"],"usage":{"total_tokens":1256}}
{"event":"task_failed","task_id":"000002","error_code":"rate_limit","message":"retry scheduled","attempt":1}
{"event":"job_completed","succeeded":50,"failed":2,"skipped":0}
```

事件协议一旦发布，后续版本必须保持向后兼容。

# 10. 系统架构

## 10.1 模块分层

```text
presentation/
  gui_app.py
  widgets/
    folder_picker.py
    prompt_editor.py
    parameter_panel.py
    command_preview.py
    queue_table.py
    result_gallery.py

cli/
  main.py

core/
  config.py
  api_capabilities.py
  command_builder.py
  file_scanner.py
  image_validator.py
  prompt_renderer.py
  task_planner.py
  batch_engine.py
  openai_image_client.py
  output_writer.py
  manifest_store.py
  cost_estimator.py
  event_protocol.py
  security.py
  logging_setup.py

tests/
  test_config_validation.py
  test_size_validation.py
  test_command_builder.py
  test_file_scanner.py
  test_prompt_renderer.py
  test_manifest_resume.py
  test_output_writer.py
```

## 10.2 核心数据流

```text
用户配置 GUI
  -> AppConfig
  -> TaskPlanner 扫描文件并生成 TaskPlan[]
  -> CommandBuilder 生成命令
  -> GUI 执行 runner 子进程
  -> BatchEngine 按 concurrency 调度任务
  -> OpenAIImageClient 调用 Image API
  -> OutputWriter 保存 final/partials
  -> ManifestStore 写入 manifest
  -> EventProtocol 输出 JSONL
  -> GUI 更新进度与预览
```

## 10.3 关键类

```python
class AppConfig(BaseModel):
    api: ApiConfig
    input: InputConfig
    output: OutputConfig
    image: ImageParams
    execution: ExecutionConfig
    prompt: PromptConfig

class TaskPlan(BaseModel):
    task_id: str
    mode: Literal["generate", "edit", "inpaint"]
    source_paths: list[Path]
    mask_path: Path | None
    rendered_prompt: str
    output_plan: list[Path]

class TaskResult(BaseModel):
    task_id: str
    status: Literal["succeeded", "failed", "skipped", "canceled"]
    output_files: list[Path]
    partial_files: list[Path]
    usage: UsageInfo | None
    error: ErrorInfo | None
```

# 11. OpenAI API 调用设计

## 11.1 生成模式

适用于无输入图的 text-to-image。

伪代码：

```python
async def generate_image(task: TaskPlan, params: ImageParams) -> TaskResult:
    if params.stream:
        stream = await client.images.generate(
            model=params.model,
            prompt=task.rendered_prompt,
            n=params.n,
            size=params.size,
            quality=params.quality,
            output_format=params.output_format,
            output_compression=params.output_compression_if_supported(),
            background=params.background,
            moderation=params.moderation,
            stream=True,
            partial_images=params.partial_images,
        )
        async for event in stream:
            await handle_generation_event(event, task)
    else:
        response = await client.images.generate(
            model=params.model,
            prompt=task.rendered_prompt,
            n=params.n,
            size=params.size,
            quality=params.quality,
            output_format=params.output_format,
            output_compression=params.output_compression_if_supported(),
            background=params.background,
            moderation=params.moderation,
        )
        await save_response_images(response, task)
```

## 11.2 编辑/参考图模式

适用于输入图作为待编辑图或参考图。

伪代码：

```python
async def edit_image(task: TaskPlan, params: ImageParams) -> TaskResult:
    files = [open(path, "rb") for path in task.source_paths]
    try:
        kwargs = {
            "model": params.model,
            "image": files if len(files) > 1 else files[0],
            "prompt": task.rendered_prompt,
            "n": params.n,
            "size": params.size,
            "quality": params.quality,
            "output_format": params.output_format,
            "background": params.background,
            "moderation": params.moderation,
        }
        if task.mask_path:
            kwargs["mask"] = open(task.mask_path, "rb")
        if params.stream:
            kwargs["stream"] = True
            kwargs["partial_images"] = params.partial_images
        response_or_stream = await client.images.edit(**kwargs)
        return await consume_result(response_or_stream, task, params)
    finally:
        for f in files:
            f.close()
```

注意：

- 对 `gpt-image-2` 不要传 `input_fidelity`。
- mask 模式下要预先校验 mask。
- 多参考图可能显著增加输入 image tokens，应在成本估算中提示。

## 11.3 流式事件处理

必须处理：

- `image_generation.partial_image`
- `image_generation.completed`
- `image_edit.partial_image`
- `image_edit.completed`

事件处理逻辑：

1. 若事件包含 partial image，保存到 `partials/<task_stem>/partial_<index>.<format>`。
2. 若 GUI 需要预览，输出 `partial_saved` JSONL 事件。
3. 若事件为 completed，保存最终图。
4. 从 completed 事件读取 usage，如果 SDK 返回 usage 字段。
5. completed 事件才标记任务成功。
6. partial image 不能当作最终成品，除非用户明确选择“保留中间图”。

# 12. 并发、重试与恢复

## 12.1 并发模型

使用异步信号量：

```python
sem = asyncio.Semaphore(config.execution.concurrency)

async def run_task(task):
    async with sem:
        return await run_with_retries(task)
```

默认并发度为 2。GUI 可以允许 1 到 8，但必须提示：

- 并发越高，越容易触发限流。
- 并发越高，本地磁盘与内存占用越高。
- 首次使用建议从 1 或 2 开始。

## 12.2 重试策略

可重试错误：

- 网络超时。
- 连接中断。
- 429 rate limit。
- 5xx 服务错误。
- 临时文件写入失败。

不可重试错误：

- API Key 无效。
- 参数不合法。
- 文件不存在或无权限。
- mask 尺寸不匹配。
- 内容策略拒绝。
- 输出目录不可写。

重试使用指数退避与随机抖动：

```text
delay = min(max_delay, base_delay * 2 ** attempt + random_jitter)
```

建议默认：

- `max_retries=2`
- `base_delay=2s`
- `max_delay=60s`

## 12.3 暂停、取消、恢复

暂停实现建议：

- GUI 写入 `job.control.json`，设置 `pause_requested=true`。
- runner 在每个任务开始前检查。
- 正在运行的任务允许完成，不强制中断 API 请求。
- 恢复时设置 `pause_requested=false`。

取消实现建议：

- GUI 发送 terminate。
- runner 捕获信号，停止拉取新任务，正在运行任务尽量取消。
- 标记未运行任务为 `canceled`。
- 保留已完成输出。

恢复实现建议：

- 读取 `manifest.jsonl`。
- 根据 `task_id` 和输出文件判断成功任务。
- 默认跳过 succeeded。
- 允许仅重跑 failed。
- 允许强制重跑全部。

# 13. 成本控制与用量统计

## 13.1 预估成本

运行前给出估算：

```text
预计任务数 = 输入图片数 × 每任务生成张数
预计最终图输出成本 = 任务数 × size/quality 对应的输出 token 估算 × 图像输出单价
预计 partial 成本 = 实际可能 partial 数 × 100 image output tokens × 图像输出单价
预计输入成本 = prompt text tokens + 输入图片 tokens
```

因为输入图片 tokens 与具体图片、模型高保真处理有关，预估应标记为“估算值”。运行完成后，以 API usage 字段为准汇总。

## 13.2 运行中预算保护

增强版应支持：

- 最大任务数限制。
- 最大预计成本限制。
- 最大失败数或失败率停止。
- 单任务 token 异常高时提醒。
- 输出 usage CSV。

## 13.3 usage 汇总

`summary.json` 示例：

```json
{
  "job_id": "job-20260518-153012",
  "tasks_total": 52,
  "succeeded": 50,
  "failed": 2,
  "total_input_tokens": 12345,
  "total_output_tokens": 67890,
  "total_tokens": 80235,
  "partial_images_saved": 70,
  "estimated_cost_usd": 0.0,
  "started_at": "...",
  "finished_at": "..."
}
```

# 14. 安全与隐私

## 14.1 API Key 管理

读取优先级：

1. `OPENAI_API_KEY` 环境变量。
2. Windows Credential Manager，通过 `keyring` 读取。
3. GUI 本次会话输入。

要求：

- 不在命令行参数中传 API Key。
- 不写入 `config.snapshot.json`。
- 不写入日志。
- 不在异常堆栈中泄露。
- UI 中只显示尾号，例如 `sk-...abcd`。
- 提供“清除已保存 Key”按钮。

## 14.2 本地文件隐私

- 默认不上传非用户选择的文件。
- 只扫描用户指定目录。
- 日志中可选择隐藏完整路径，只保留文件名。
- 临时文件在任务结束后清理。
- 不启用遥测；若以后增加，必须显式 opt-in。

## 14.3 内容安全

- UI 显示“所有 prompt 和生成图会经过内容政策过滤”的说明。
- moderation 默认 `auto`。
- 如果 API 返回内容策略相关错误，应将任务标为 failed，并在错误中提示用户调整 prompt。
- 不提供绕过安全策略的功能。

# 15. 错误处理与用户提示

| 错误类别 | 识别方式 | 用户提示 | 自动处理 |
|---|---|---|---|
| API Key 缺失 | 启动预检 | “请设置 OPENAI_API_KEY 或在设置中保存 Key” | 阻止执行 |
| 参数不合法 | config validation | “尺寸不符合 gpt-image-2 约束” | 阻止生成命令 |
| 输出目录不可写 | 文件系统检查 | “输出目录不可写，请选择其他目录” | 阻止执行 |
| mask 不合格 | Pillow 验证 | “mask 与原图尺寸不一致或无 alpha 通道” | 标记任务失败或跳过 |
| 限流 | API 429 | “触发限流，正在等待并重试” | 退避重试，可降低并发 |
| 超时 | timeout | “任务超时，可降低并发或简化 prompt” | 重试 |
| 内容策略 | API error | “请求未通过安全过滤，请调整 prompt” | 不重试 |
| base64 解码失败 | decode exception | “图片返回解析失败” | 重试一次 |
| 磁盘空间不足 | write exception | “输出磁盘空间不足” | 暂停 job |
| 用户取消 | control event | “任务已取消，已保留完成结果” | 写入 manifest |

# 16. 质量要求

## 16.1 性能目标

| 指标 | MVP 目标 |
|---|---|
| 启动时间 | 5 秒内进入主界面 |
| 扫描 1000 张图片 | 10 秒内完成基本扫描，不读取完整图片像素 |
| GUI 响应性 | API 执行期间 UI 不阻塞 |
| 任务进度延迟 | runner 事件到 GUI 更新不超过 1 秒 |
| 单 job 恢复 | 读取 1000 条 manifest 不超过 2 秒 |
| 内存占用 | 常规批处理低于 1GB，不一次性加载所有原图 |

## 16.2 可用性目标

- 新用户 5 分钟内能完成一次单图测试。
- 批量执行前必须有预检结果。
- 用户能明确知道当前在执行哪张图、成功多少、失败多少。
- 所有失败都应有可读原因。
- 输出目录结构清晰，不覆盖用户原图。
- 生成命令可复制到 PowerShell 独立执行。

## 16.3 工程质量目标

- 核心逻辑测试覆盖率不低于 80%。
- CLI 与 GUI 共用同一个配置模型和执行引擎。
- JSONL 事件协议有单元测试。
- 所有路径使用 `pathlib.Path`。
- 代码有类型标注。
- 使用能力配置管理 API 参数，不散落魔法字符串。
- 所有外部调用集中在 `openai_image_client.py`。

# 17. 测试计划

## 17.1 单元测试

必须覆盖：

1. `size` 合法性校验。
2. `background` 对 `gpt-image-2` 禁止 transparent。
3. `output_compression` 仅对 JPEG/WebP 生效。
4. prompt 变量渲染。
5. 文件扫描与扩展名过滤。
6. mask 匹配规则。
7. mask alpha 验证。
8. 输出命名模板。
9. command builder 的 PowerShell 转义。
10. config JSON 序列化与反序列化。
11. manifest 恢复逻辑。
12. JSONL 事件解析。
13. 错误分类与重试判断。

## 17.2 集成测试

使用 mock OpenAI client：

- 非流式 generations 返回一张图。
- 非流式 edits 返回一张图。
- 流式返回两个 partial 与一个 completed。
- API 429 后重试成功。
- 内容策略错误不重试。
- 写文件失败暂停 job。
- 并发度为 3 时同时最多运行 3 个任务。

## 17.3 GUI 测试

- 启动主窗口。
- 选择输入输出文件夹。
- 参数非法时按钮禁用。
- 点击“生成命令”后命令预览更新。
- dry-run 后队列表格显示任务。
- runner 输出事件后状态更新。
- partial image 保存事件后预览更新。

## 17.4 真实 API 冒烟测试

仅在设置 `OPENAI_API_KEY` 且显式启用时运行：

1. 文本生成 1 张低质量小图。
2. 单张图片 edit。
3. 流式生成，保存 1 张 partial。
4. mask 编辑，如果测试资源存在。
5. 记录 request_id 与 usage，如 SDK 提供。

## 17.5 Windows 打包测试

在干净 Windows 10/11 环境验证：

- EXE 能启动。
- GUI 能选择文件夹。
- keyring 能保存和读取 API Key。
- PowerShell 命令可执行。
- 输出文件可打开。
- 中文路径可处理。
- 空格路径可处理。
- 程序目录无管理员权限也能运行。

# 18. 里程碑与交付计划

## 18.1 Phase 0：项目初始化

交付物：

- Git 仓库。
- Python 项目结构。
- 依赖管理文件。
- 基础 README。
- `api_capabilities.json`。
- 空 GUI 窗口。
- CLI `--help` 可运行。

验收：

- `GptImageBatch.exe gui` 或 `python -m app gui` 能打开窗口。
- `python -m app run --help` 能显示命令帮助。
- 单元测试框架可运行。

## 18.2 Phase 1：配置模型与命令生成

交付物：

- Pydantic 配置模型。
- 参数校验。
- PowerShell 命令生成。
- dry-run 输出。
- 配置保存/加载。

验收：

- GUI 中填写参数后能生成命令。
- 非法尺寸阻止生成命令。
- 命令不包含 API Key。
- 配置 JSON 可反复加载且无信息丢失。

## 18.3 Phase 2：文件扫描与任务规划

交付物：

- 输入文件夹扫描。
- mask 文件夹匹配。
- prompt 变量渲染。
- output path 规划。
- manifest 初始化。

验收：

- 100 张图片能生成 100 个任务。
- mask 不匹配项能被识别。
- 输出文件名不会冲突。
- dry-run 能列出任务摘要。

## 18.4 Phase 3：Image API Runner

交付物：

- `OpenAIImageClient`。
- generations 调用。
- edits 调用。
- base64 保存。
- 重试与超时。
- JSONL 事件输出。

验收：

- mock 模式下所有路径通过。
- 真实 API 冒烟测试至少完成 text-to-image。
- 失败任务写入 manifest。
- 成功任务保存输出图片。

## 18.5 Phase 4：并发与恢复

交付物：

- asyncio semaphore 并发调度。
- pause/cancel/resume。
- 失败项重跑。
- manifest 读取恢复。

验收：

- 并发度设置生效。
- 取消后已完成结果不丢失。
- 重启后可继续未完成任务。
- 只重跑失败项成功。

## 18.6 Phase 5：GUI 完整闭环

交付物：

- 主界面完整控件。
- 队列表格。
- 日志面板。
- 命令预览。
- 执行控制。
- 结果预览。

验收：

- 用户无需命令行即可完成一次批处理。
- GUI 执行 runner 并实时显示进度。
- 执行结束可打开输出文件夹。
- 错误原因可读。

## 18.7 Phase 6：流式预览、成本与增强体验

交付物：

- `stream` 与 `partial_images`。
- partial 保存与预览。
- 运行前成本估算。
- 运行后 usage 汇总。
- profile 管理。
- 单图测试按钮。

验收：

- 开启流式后 partial 能保存和预览。
- summary.json 记录 usage。
- profile 能保存和切换。
- 单图测试不影响批处理队列。

## 18.8 Phase 7：打包、文档与发布

交付物：

- PyInstaller 打包脚本。
- Windows 便携包。
- 用户指南。
- Agent 开发指南。
- 示例配置。
- 示例命令。

验收：

- 干净 Windows 环境可运行。
- README 能指导用户完成第一次任务。
- 所有 P0/P1 功能通过验收。
- 发布包不包含 API Key、测试图片或私密日志。

# 19. 功能 Backlog

## 19.1 P0：必须实现

- [ ] Windows GUI 主窗口。
- [ ] 输入文件夹与输出文件夹选择。
- [ ] 参数表单与校验。
- [ ] Prompt 编辑器。
- [ ] 命令生成与复制。
- [ ] CLI runner。
- [ ] Image API generate。
- [ ] Image API edit。
- [ ] 并发执行。
- [ ] 非流式保存最终图。
- [ ] 日志与 manifest。
- [ ] 重试与失败记录。
- [ ] 恢复未完成任务。
- [ ] API Key 安全读取。
- [ ] 打包为 Windows 可执行程序。

## 19.2 P1：好用标准

- [ ] 单图测试。
- [ ] stream partial 预览。
- [ ] 保存 partial images。
- [ ] mask 模式。
- [ ] profile 管理。
- [ ] 输出命名模板。
- [ ] 成本估算。
- [ ] usage 汇总。
- [ ] 结果图库。
- [ ] 前后对比。
- [ ] CSV prompt 映射。
- [ ] 失败项重跑按钮。
- [ ] 参数 tooltip 与内置帮助。
- [ ] 运行完成系统通知。
- [ ] 主题切换。

## 19.3 P2：进阶体验

- [ ] Responses API 多轮编辑实验模式。
- [ ] Prompt 版本管理。
- [ ] 自动生成缩略图缓存。
- [ ] 文件夹监听，新增图片自动入队。
- [ ] 任务模板市场或模板包导入。
- [ ] 多 job 管理。
- [ ] 自动上传结果到云盘或对象存储。
- [ ] Web UI 版本。
- [ ] 插件系统。
- [ ] 命令历史搜索。
- [ ] 本地 SQLite 作业数据库。
- [ ] 多 API Key 轮转。
- [ ] 队列优先级。
- [ ] 批量导出 HTML 报告。

# 20. 配置文件示例

```json
{
  "version": 1,
  "api": {
    "provider": "openai",
    "api_type": "image",
    "model": "gpt-image-2",
    "api_key_source": "env"
  },
  "input": {
    "mode": "edit",
    "input_dir": "D:/source_images",
    "recursive": false,
    "extensions": [".png", ".jpg", ".jpeg", ".webp"],
    "mask_dir": null,
    "reference_grouping": "one_task_per_image"
  },
  "prompt": {
    "template": "保持主体不变，将背景替换为纯白摄影棚背景。源文件名：{stem}",
    "variables_enabled": true,
    "csv_prompt_map": null
  },
  "image": {
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png",
    "output_compression": null,
    "background": "auto",
    "moderation": "auto",
    "n": 1,
    "stream": false,
    "partial_images": 0,
    "save_partials": false
  },
  "execution": {
    "concurrency": 2,
    "max_retries": 2,
    "timeout_seconds": 240,
    "failure_policy": "continue",
    "overwrite_policy": "skip_existing"
  },
  "output": {
    "output_dir": "D:/outputs",
    "job_subdir_enabled": true,
    "filename_template": "{stem}_gpt_{variant}",
    "save_manifest": true,
    "save_logs": true,
    "save_config_snapshot": true
  }
}
```

# 21. 输出命名规范

建议默认命名：

```text
{stem}_gpt_{variant}.{ext}
```

变量：

| 变量 | 示例 |
|---|---|
| `{stem}` | `product_001` |
| `{index}` | `000001` |
| `{variant}` | `v1` |
| `{quality}` | `medium` |
| `{size}` | `1024x1024` |
| `{date}` | `20260518` |
| `{hash}` | `a1b2c3` |

冲突处理：

- `skip_existing`：如果目标存在，跳过任务。
- `overwrite`：覆盖。
- `append_counter`：追加 `_2`、`_3`。
- `new_job_dir`：推荐默认，每次运行新目录。

# 22. Agent 实施规则

开发 Agent 在实现时应遵守：

1. 不要把 GUI 与 API 调用直接耦合；GUI 必须通过配置和 runner 执行。
2. 所有外部文件路径都使用 `pathlib.Path`。
3. 所有命令生成都必须通过 `CommandBuilder`，不允许在 UI 控件中拼接命令。
4. 所有 API 参数必须从 `AppConfig` 派生。
5. 所有任务状态变化必须写 JSONL 事件。
6. 不要在日志中写 API Key。
7. 不要吞掉异常；需要分类、记录、展示。
8. 对同一功能同时写单元测试。
9. 先写 mock API 集成测试，再跑真实 API 冒烟测试。
10. 任何新增参数都要同步更新：
    - GUI 控件。
    - 配置模型。
    - 命令生成。
    - API 调用。
    - 文档。
    - 测试。
11. 如果官方文档更新参数，先改 `api_capabilities.json`，再改 UI。
12. 真实 API 测试必须受环境变量开关保护，默认不跑。
13. GUI 主线程不得执行网络请求或长时间文件扫描。
14. 任何可恢复状态必须写入 manifest，不只存在内存中。
15. partial image 保存失败不应导致最终图任务失败，但必须记录警告。

# 23. 验收标准

## 23.1 MVP 验收

- [ ] 在 Windows 10/11 上可启动 GUI。
- [ ] 用户能选择输入图片文件夹和输出文件夹。
- [ ] 用户能设置并发度。
- [ ] 用户能设置 prompt、size、quality、format、background、moderation。
- [ ] 用户点击“生成命令”能看到可复制命令。
- [ ] 生成的命令能在 PowerShell 中独立执行。
- [ ] GUI 能执行该命令并更新进度。
- [ ] 10 张测试图片在并发度 2 下能完成批处理。
- [ ] 输出目录包含最终图片、manifest、日志和配置快照。
- [ ] 错误任务不会导致整个程序崩溃。
- [ ] API Key 不出现在命令、日志、manifest 中。
- [ ] 取消任务后已完成输出仍保留。
- [ ] 关闭应用后可恢复未完成 job。
- [ ] 非法尺寸、非法背景、不可写目录能提前阻止执行。

## 23.2 好用标准验收

- [ ] 能保存和切换多个 profile。
- [ ] 支持单图测试。
- [ ] 支持 stream partial preview。
- [ ] 支持保存 partial images。
- [ ] 支持 mask 文件夹并做校验。
- [ ] 支持失败项重跑。
- [ ] 支持结果图库和打开输出文件夹。
- [ ] 支持成本估算与 usage 汇总。
- [ ] 支持 prompt 变量。
- [ ] 支持 CSV prompt 映射。
- [ ] 支持中文路径、空格路径和长路径。
- [ ] 支持日志导出。
- [ ] 打包后无需安装 Python 即可运行。

# 24. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| API 参数随官方更新变化 | 参数校验失效 | 使用 capabilities 配置，集中更新 |
| 并发过高触发限流 | 大量失败 | 默认低并发、指数退避、动态降并发 |
| GUI 卡顿 | 用户误以为崩溃 | 子进程 runner + JSONL 事件，GUI 不阻塞 |
| 图片过大或格式异常 | API 失败 | 预检读取元数据，必要时提示转换 |
| mask 不合格 | 局部编辑失败 | 执行前校验尺寸、格式、alpha |
| 成本不可控 | 用户意外消费 | 运行前估算、成本上限、partial 成本提示 |
| API Key 泄露 | 安全事故 | keyring/env，日志脱敏，命令不带 key |
| 结果覆盖 | 数据丢失 | 默认新 job 目录，不覆盖 |
| 中断后状态丢失 | 无法恢复 | manifest 每任务实时写入 |
| 文本生成不精准 | 用户不满意 | 提示模型限制，提供 prompt 建议和单图测试 |
| 打包体积较大 | 影响分发 | 便携目录发布，压缩资源，延迟加载 |
| Windows 杀软误报 | 用户无法运行 | 签名、发布说明、减少可疑行为 |

# 25. 未来扩展路线

## 25.1 Responses API 多轮编辑模式

在 MVP 稳定后，可增加“对话式编辑”模式：

- 用户选中某个输出图。
- 在右侧聊天面板输入“再把背景调暖一点”。
- 使用 Responses API 维持上下文。
- 输出新版本，并与旧版本建立版本链。

注意：该模式不是批处理核心路径，应作为独立实验功能。

## 25.2 作业数据库

把 manifest 扩展为 SQLite：

- 支持多 job 历史。
- 支持搜索 prompt、文件名、错误。
- 支持结果标签。
- 支持导出报告。

## 25.3 自动化与集成

- 导出 GitHub Actions 示例。
- 支持命令行纯批处理。
- 支持文件夹监听。
- 支持 Webhook 完成通知。
- 支持上传到 S3、Azure Blob 或本地 NAS。

# 26. 推荐开发顺序

给编码 Agent 的具体执行顺序：

1. 建立项目骨架和依赖。
2. 实现 `api_capabilities.json`。
3. 实现 Pydantic 配置模型。
4. 实现 size、background、format、compression 校验。
5. 实现 command builder。
6. 实现 file scanner。
7. 实现 prompt renderer。
8. 实现 output planner。
9. 实现 manifest store。
10. 实现 mock OpenAI client。
11. 实现 batch engine。
12. 实现 real OpenAIImageClient。
13. 实现 CLI runner。
14. 实现 GUI 主窗口。
15. 接入 GUI 与 runner 子进程。
16. 实现日志和队列表格。
17. 实现单图测试。
18. 实现 streaming 和 partial 保存。
19. 实现 mask 模式。
20. 实现 profile 管理。
21. 实现成本估算。
22. 完成测试、打包和文档。

# 27. 最小可运行闭环定义

在项目早期不要追求完整界面。第一版闭环只需要：

```text
输入：一个文件夹 + 一个 prompt + 一个输出文件夹 + 并发度
处理：扫描文件 -> 生成任务 -> 调用 edits -> 保存图片
输出：final 图片 + manifest + log
```

GUI 第一版可以只有 6 个控件：

1. 输入文件夹。
2. 输出文件夹。
3. Prompt。
4. 并发度。
5. 生成命令。
6. 执行。

在这个闭环跑通后，再增加 partial、mask、profile、gallery、cost 等功能。

# 28. 附录：单任务 curl 示例

生成图：

```powershell
curl https://api.openai.com/v1/images/generations `
  -H "Authorization: Bearer $env:OPENAI_API_KEY" `
  -H "Content-Type: application/json" `
  -d '{
    "model": "gpt-image-2",
    "prompt": "A clean product photo on a white background",
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png"
  }'
```

编辑图：

```powershell
curl https://api.openai.com/v1/images/edits `
  -H "Authorization: Bearer $env:OPENAI_API_KEY" `
  -F "model=gpt-image-2" `
  -F "image[]=@D:\input\product.png" `
  -F "prompt=Keep the product unchanged and replace the background with a clean white studio background" `
  -F "size=1024x1024" `
  -F "quality=medium" `
  -F "output_format=png"
```

实际产品中不建议通过 GUI 直接拼接复杂 curl 执行批处理。推荐用本地 runner 执行，因为它能更好处理路径转义、并发、重试、日志、恢复和错误分类。

# 29. 附录：参考链接

1. OpenAI Image Generation Guide：`https://developers.openai.com/api/docs/guides/image-generation?multi-turn=imageid&api=image`
2. OpenAI Images API Reference：`https://developers.openai.com/api/reference/resources/images`
3. OpenAI API Pricing：`https://developers.openai.com/api/docs/pricing`
4. OpenAI API Dashboard：`https://platform.openai.com/`
5. OpenAI content policy：`https://openai.com/policies/`
