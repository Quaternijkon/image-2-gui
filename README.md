# GPT Image Batch 用户操作手册

GPT Image Batch 是一个面向 Windows 的 `gpt-image-2` 批量图片生成与编辑工具。它同时提供图形界面和命令行入口，适合把一批图片按统一 prompt 批量编辑，或者按文本 prompt 批量生成图片。

本项目主要使用 OpenAI Image API 的 `generations` 和 `edits` 能力。模型、尺寸、格式、压缩、背景、流式 partial image 等限制集中放在 `app/api_capabilities.json` 与配置校验代码中，便于以后跟随官方文档更新。

## 功能概览

- Windows GUI：填写输入目录、输出目录、prompt、图片参数和并发度后生成命令或直接执行。
- CLI runner：可在 PowerShell 中独立运行，适合批处理、脚本化和恢复任务。
- 支持模式：文本生图 `generate`、图片编辑 `edit`、局部重绘/遮罩相关模式 `inpaint` / `mask`。
- 支持输出：`png`、`jpeg`、`webp`。
- 支持参数：`size`、`quality`、`background`、`moderation`、`n`、`output_compression`、`stream`、`partial_images`、并发、超时、重试。
- 支持 dry-run 预检：只检查配置和规划任务，不调用 API。
- 支持 mock 模式：不联网也能验证完整执行流程。
- 支持 manifest、JSONL 事件、日志、配置快照和命令快照。
- 支持暂停、取消、失败记录、恢复未完成任务。
- 支持 profile 管理：保存、读取、切换、删除常用配置。
- 支持 Windows 打包脚本：可用 PyInstaller 打包为目录版或单文件版。

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- PowerShell
- OpenAI API key
- GUI 需要 `PySide6`

建议使用虚拟环境运行，避免污染系统 Python。

## 安装步骤

在项目目录中打开 PowerShell：

```powershell
cd D:\Code\image-2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

如果只想运行工具而不跑测试，也可以安装基础依赖：

```powershell
python -m pip install -e .
```

如果 GUI 启动时报缺少 Qt/PySide6：

```powershell
python -m pip install PySide6
```

## API Key 设置

不要把 API key 写进配置文件、README、命令参数、profile、日志或 manifest。推荐只用环境变量：

```powershell
$env:OPENAI_API_KEY="你的 API Key"
```

如果你使用兼容 OpenAI SDK 的代理或自建网关，可以临时设置 SDK 支持的 base URL 环境变量：

```powershell
$env:OPENAI_BASE_URL="https://your-compatible-endpoint/v1"
```

运行结束后可以清理环境变量：

```powershell
Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
```

安全约定：生成的配置快照、profile 文件、命令快照、日志、manifest 和 summary 都设计为不包含密钥。英文关键提示：no API keys。

## 启动 GUI

```powershell
python -m app gui
```

GUI 界面会使用同一套 `AppConfig` 配置模型和 CLI runner。常用流程：

1. 在 `Input folder` 中填写输入图片目录。文本生图模式可以留空。
2. 在 `Output folder` 中填写输出目录。
3. 在 `Prompt` 中填写全局 prompt。
4. 选择 `Mode`：
   - `generate`：不需要输入图片，根据 prompt 生图。
   - `edit`：对输入目录中的图片做编辑。
   - `inpaint` / `mask`：用于带 mask 的局部编辑流程。
5. 设置 `Size`、`Quality`、`Output format`、`Background`、`Moderation`。
6. 设置 `Images per input`，即每个输入要生成几张结果图。
7. 设置 `Concurrency` 并发度。
8. 点击 `Generate command` 生成可复制的 PowerShell 命令。
9. 点击 `Dry-run / preflight` 做预检。
10. 点击 `Execute` 正式运行。
11. 运行中可点击 `Pause` 或 `Cancel` 写入控制文件。

GUI 不会直接在主线程里调用 OpenAI API；它会生成配置快照和命令，再通过子进程运行 CLI runner，并解析 JSONL 事件更新队列表格。

## CLI 基本命令

查看帮助：

```powershell
python -m app run --help
python -m app gui --help
python -m app profile --help
```

使用示例配置做 dry-run 预检：

```powershell
python -m app run --config examples/example.config.json --output-dir .\out --dry-run --events-jsonl
```

dry-run 会完成配置校验、任务规划、输出目录规划和成本 token-unit 估算，但不会调用 API。

使用 mock API 跑完整流程，不产生网络请求：

```powershell
$env:GPT_IMAGE_BATCH_MOCK_API=1
python -m app run --config examples/example.config.json --output-dir .\out --events-jsonl
Remove-Item Env:\GPT_IMAGE_BATCH_MOCK_API -ErrorAction SilentlyContinue
```

调用真实 API：

```powershell
$env:OPENAI_API_KEY="你的 API Key"
python -m app run --config examples/example.config.json --output-dir .\out --events-jsonl
```

## 配置文件说明

最小示例见 [examples/example.config.json](examples/example.config.json)。

常见字段：

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
    "mode": "generate",
    "input_dir": null,
    "recursive": false,
    "extensions": [".png", ".jpg", ".jpeg", ".webp"]
  },
  "prompt": {
    "template": "Create a clean product image with soft studio lighting."
  },
  "image": {
    "size": "auto",
    "quality": "auto",
    "output_format": "png",
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
    "output_dir": ".\\out",
    "filename_template": "{stem}_gpt_{variant}.{ext}"
  }
}
```

`api_key_source` 支持：

- `env`：读取 `OPENAI_API_KEY`。
- `env:变量名`：读取自定义环境变量，例如 `env:MY_OPENAI_KEY`。
- `keyring` 或 `windows_credential_manager`：通过 keyring / Windows Credential Manager 读取。
- `none`：不主动传入 API key，适合完全由外层 SDK 环境接管的场景。

不要在配置文件里写 `api.api_key`。即便 GUI 会在快照里排除该字段，也不建议把密钥放进任何持久文件。

## Prompt 变量

默认启用变量替换。常用变量：

- `{stem}`：输入文件名，不含扩展名。
- `{index}`：任务序号。
- `{variant}`：同一个输入的结果序号，例如 `v1`、`v2`。
- `{quality}`：当前质量设置。
- `{size}`：当前尺寸设置。
- `{date}`：日期字段。
- `{hash}`：任务哈希短值。

示例：

```json
{
  "prompt": {
    "template": "Retouch {stem}, keep original composition, output variant {variant}."
  }
}
```

## 输出目录结构

每次运行会生成一个 job 目录。典型结构：

```text
out/
  job-YYYYMMDD-HHMMSS/
    final/
    partials/
    failed/
    thumbnails/
    logs/
      app.log
      events.jsonl
      errors.jsonl
    manifest.jsonl
    summary.json
    config.snapshot.json
    command.ps1
```

重要文件：

- `final/`：最终图片。
- `partials/`：流式 partial image，只有开启保存时才会写入。
- `manifest.jsonl`：任务状态记录，用于恢复和审计。
- `summary.json`：任务汇总。
- `config.snapshot.json`：本次运行配置快照，不包含 API key。
- `command.ps1`：可复现本次运行的命令。

## 暂停、取消和恢复

GUI 的 `Pause` / `Cancel` 会在 job 根目录写入 `job.control.json`。runner 会在任务开始前检查控制文件：

- `pause_requested: true`：未开始的任务标记为 paused。
- `cancel_requested: true`：未开始的任务标记为 canceled。

已经发出的 API 请求不会被强制中断；它们可能会正常完成并写入输出。

恢复任务依赖 `manifest.jsonl`。已成功或已跳过的任务不会重复执行，需要重试失败项时由 runner 根据 manifest 选择需要恢复的任务。

## Profile 管理

profile 用来保存常用配置。默认保存到用户目录下的 `.gpt-image-batch/profiles`，也可以用 `--profiles-dir` 指定项目内目录。

```powershell
python -m app profile save demo --config examples/example.config.json
python -m app profile list
python -m app profile load demo
python -m app profile switch demo
python -m app profile delete demo
```

使用自定义 profile 目录：

```powershell
python -m app profile save demo --config examples/example.config.json --profiles-dir .\profiles
python -m app profile list --profiles-dir .\profiles
```

profile 写入和读取时会排除 `api.api_key`。

## 真实 API 冒烟测试

真实 API 测试默认跳过，必须同时设置 API key 和开关：

```powershell
$env:OPENAI_API_KEY="你的 API Key"
$env:GPT_IMAGE_BATCH_RUN_REAL_API_SMOKE=1
pytest tests/test_real_api_smoke.py
Remove-Item Env:\GPT_IMAGE_BATCH_RUN_REAL_API_SMOKE -ErrorAction SilentlyContinue
```

如果使用兼容端点：

```powershell
$env:OPENAI_BASE_URL="https://your-compatible-endpoint/v1"
pytest tests/test_real_api_smoke.py
```

## Windows 打包

项目提供 PyInstaller 辅助脚本：[scripts/build_windows.ps1](scripts/build_windows.ps1)。

目录版：

```powershell
.\scripts\build_windows.ps1
```

单文件版：

```powershell
.\scripts\build_windows.ps1 -OneFile
```

如果当前环境没有 PyInstaller，脚本会尝试安装或升级。打包后的程序仍应通过环境变量读取 API key，不会把密钥嵌入可执行文件。

## 开发与验证

常用验证命令：

```powershell
pytest
python -m app run --help
python -m app gui --help
python -m app profile --help
```

检查文档和示例：

```powershell
pytest tests/test_examples_docs.py
```

检查是否误写入真实密钥：

```powershell
rg -n "sk-[A-Za-z0-9_-]{20,}" README.md examples scripts app tests pyproject.toml
```

测试中出现的 `sk-secret...` 是假密钥断言，不是真实 API key。

## 常见问题

### GUI 提示 PySide6 缺失

运行：

```powershell
python -m pip install PySide6
```

然后重新执行：

```powershell
python -m app gui
```

### API key 不生效

确认当前 PowerShell 会话里能读到环境变量：

```powershell
$env:OPENAI_API_KEY
```

如果配置使用 `env:MY_OPENAI_KEY`，则需要设置对应变量：

```powershell
$env:MY_OPENAI_KEY="你的 API Key"
```

### dry-run 通过但真实运行失败

dry-run 不会联网。真实运行还依赖 API key、网络、兼容端点、账户权限和模型可用性。先用 mock 模式确认本地流程，再运行真实 API。

### 输出文件重名

检查 `output.filename_template` 和 `execution.overwrite_policy`。默认模板包含 `{variant}`，适合 `n > 1` 的场景。

### partial image 没有保存

需要同时设置：

```json
{
  "image": {
    "stream": true,
    "partial_images": 1,
    "save_partials": true
  }
}
```

`partial_images` 的范围是 0 到 3。

## 目录入口

- CLI 入口：[app/cli/main.py](app/cli/main.py)
- GUI 入口：[app/presentation/gui_app.py](app/presentation/gui_app.py)
- API 能力配置：[app/api_capabilities.json](app/api_capabilities.json)
- 示例配置：[examples/example.config.json](examples/example.config.json)
- 打包脚本：[scripts/build_windows.ps1](scripts/build_windows.ps1)
