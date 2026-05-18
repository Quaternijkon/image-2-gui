from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.command_builder import CommandBuilder
from app.core.config import AppConfig
from app.core.event_protocol import EventProtocol, EventProtocolError
from app.core.output_planner import OutputPlanner


Mode = Literal["generate", "edit", "inpaint", "mask"]


@dataclass
class GuiFormState:
    input_dir: Path | None = None
    output_dir: Path | None = None
    prompt: str = "Describe the image to generate or edit."
    mode: Mode = "edit"
    size: str = "auto"
    quality: str = "auto"
    output_format: str = "png"
    background: str = "auto"
    moderation: Literal["auto", "low"] = "auto"
    concurrency: int = 2
    api_key_source: str = "env"
    api_key: str | None = None

    def build_config(self) -> AppConfig:
        api_payload: dict[str, Any] = {"api_key_source": self.api_key_source}
        if self.api_key:
            api_payload["api_key"] = self.api_key
        return AppConfig(
            api=api_payload,
            input={"mode": self.mode, "input_dir": self.input_dir},
            prompt={"template": self.prompt},
            image={
                "size": self.size,
                "quality": self.quality,
                "output_format": self.output_format,
                "background": self.background,
                "moderation": self.moderation,
            },
            execution={"concurrency": self.concurrency},
            output={"output_dir": self.output_dir},
        )

    def prepare_job_files(self, *, dry_run: bool = False):
        config = self.build_config()
        layout = OutputPlanner(config).create_job_layout()
        command = CommandBuilder(config).build_powershell_command(
            config_path=layout.config_snapshot_path,
            input_dir=config.input.input_dir,
            output_dir=layout.root,
            concurrency=config.execution.concurrency,
            events_jsonl=True,
        )
        if dry_run:
            command = command.rstrip() + " `\n  --dry-run"
        layout.command_path.write_text(command + "\n", encoding="utf-8")
        return layout


@dataclass
class RunnerEventState:
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    issues: int = 0
    rows: dict[str, dict[str, str]] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)

    def handle_runner_event(self, event: dict[str, Any]) -> None:
        name = str(event.get("event", "unknown"))
        task_id = str(event.get("task_id", ""))

        if name == "dry_run_summary":
            self.total_tasks = int(event.get("total_tasks", self.total_tasks) or 0)
            self.issues = int(event.get("issues", self.issues) or 0)
        elif name == "job_started":
            self.total_tasks = int(event.get("total_tasks", self.total_tasks) or 0)
        elif name == "task_started" and task_id:
            self._set_row(task_id, "running", "started")
        elif name == "task_succeeded" and task_id:
            self.completed_tasks += 1
            outputs = event.get("output_files") or event.get("output_path") or ""
            self._set_row(task_id, "succeeded", _message_text(outputs))
        elif name == "task_failed" and task_id:
            self.failed_tasks += 1
            self._set_row(task_id, "failed", _message_text(event.get("message") or event.get("error")))
        elif name == "job_completed":
            self.completed_tasks = int(event.get("succeeded", self.completed_tasks) or 0)
            self.failed_tasks = int(event.get("failed", self.failed_tasks) or 0)
            self.skipped_tasks = int(event.get("skipped", self.skipped_tasks) or 0)

        self.log_lines.append(json.dumps(event, sort_keys=True, default=str))

    def _set_row(self, task_id: str, status: str, message: str) -> None:
        self.rows[task_id] = {"task_id": task_id, "status": status, "message": message}


def _message_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def launch_gui() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is required to launch the GUI. Install project dependencies or run "
            "`pip install PySide6`."
        ) from exc

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return int(app.exec())


class MainWindow:
    def __new__(cls):
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
        except ImportError as exc:
            raise RuntimeError(
                "PySide6 is required to launch the GUI. Install project dependencies or run "
                "`pip install PySide6`."
            ) from exc

        class _MainWindow(QtWidgets.QMainWindow):
            def __init__(self) -> None:
                super().__init__()
                self.setWindowTitle("GPT Image Batch")
                self.resize(980, 680)
                self.event_state = RunnerEventState()
                self.current_layout = None
                self.process: QtCore.QProcess | None = None
                self._stdout_buffer = ""
                self._build_ui(QtWidgets, QtGui, QtCore)
                self.refresh_command_preview()

            def _build_ui(self, QtWidgets, QtGui, QtCore) -> None:
                central = QtWidgets.QWidget()
                self.setCentralWidget(central)
                root = QtWidgets.QVBoxLayout(central)

                form = QtWidgets.QFormLayout()
                self.input_edit = QtWidgets.QLineEdit()
                self.output_edit = QtWidgets.QLineEdit()
                self.prompt_edit = QtWidgets.QPlainTextEdit()
                self.prompt_edit.setPlainText("Describe the image to generate or edit.")
                self.prompt_edit.setFixedHeight(80)
                self.mode_combo = _combo(QtWidgets, ["generate", "edit", "inpaint", "mask"], "edit")
                self.size_combo = _combo(QtWidgets, ["auto", "1024x1024", "1536x1024", "1024x1536"], "auto")
                self.quality_combo = _combo(QtWidgets, ["auto", "low", "medium", "high"], "auto")
                self.format_combo = _combo(QtWidgets, ["png", "jpeg", "webp"], "png")
                self.background_combo = _combo(QtWidgets, ["auto", "opaque"], "auto")
                self.moderation_combo = _combo(QtWidgets, ["auto", "low"], "auto")
                self.concurrency_spin = QtWidgets.QSpinBox()
                self.concurrency_spin.setRange(1, 8)
                self.concurrency_spin.setValue(2)

                form.addRow("Input folder", self.input_edit)
                form.addRow("Output folder", self.output_edit)
                form.addRow("Prompt", self.prompt_edit)
                form.addRow("Mode", self.mode_combo)
                form.addRow("Size", self.size_combo)
                form.addRow("Quality", self.quality_combo)
                form.addRow("Output format", self.format_combo)
                form.addRow("Background", self.background_combo)
                form.addRow("Moderation", self.moderation_combo)
                form.addRow("Concurrency", self.concurrency_spin)
                root.addLayout(form)

                self.command_preview = QtWidgets.QPlainTextEdit()
                self.command_preview.setReadOnly(True)
                self.command_preview.setFixedHeight(110)
                root.addWidget(self.command_preview)

                actions = QtWidgets.QHBoxLayout()
                self.refresh_button = QtWidgets.QPushButton("Generate command")
                self.copy_button = QtWidgets.QPushButton("Copy command")
                self.dry_run_button = QtWidgets.QPushButton("Dry-run / preflight")
                self.execute_button = QtWidgets.QPushButton("Execute")
                self.pause_button = QtWidgets.QPushButton("Pause")
                self.cancel_button = QtWidgets.QPushButton("Cancel")
                for button in [
                    self.refresh_button,
                    self.copy_button,
                    self.dry_run_button,
                    self.execute_button,
                    self.pause_button,
                    self.cancel_button,
                ]:
                    actions.addWidget(button)
                actions.addStretch(1)
                root.addLayout(actions)

                self.status_label = QtWidgets.QLabel("Idle")
                root.addWidget(self.status_label)

                self.queue_table = QtWidgets.QTableWidget(0, 3)
                self.queue_table.setHorizontalHeaderLabels(["Task", "Status", "Message"])
                self.queue_table.horizontalHeader().setStretchLastSection(True)
                root.addWidget(self.queue_table, stretch=1)

                self.log_widget = QtWidgets.QPlainTextEdit()
                self.log_widget.setReadOnly(True)
                self.log_widget.setFixedHeight(120)
                root.addWidget(self.log_widget)

                self.refresh_button.clicked.connect(self.refresh_command_preview)
                self.copy_button.clicked.connect(self.copy_command)
                self.dry_run_button.clicked.connect(lambda: self.start_runner(dry_run=True))
                self.execute_button.clicked.connect(lambda: self.start_runner(dry_run=False))
                self.pause_button.clicked.connect(lambda: self.write_control({"pause_requested": True}))
                self.cancel_button.clicked.connect(lambda: self.write_control({"cancel_requested": True}))

            def form_state(self) -> GuiFormState:
                return GuiFormState(
                    input_dir=_optional_path(self.input_edit.text()),
                    output_dir=_optional_path(self.output_edit.text()),
                    prompt=self.prompt_edit.toPlainText(),
                    mode=self.mode_combo.currentText(),
                    size=self.size_combo.currentText(),
                    quality=self.quality_combo.currentText(),
                    output_format=self.format_combo.currentText(),
                    background=self.background_combo.currentText(),
                    moderation=self.moderation_combo.currentText(),
                    concurrency=self.concurrency_spin.value(),
                )

            def refresh_command_preview(self) -> None:
                try:
                    layout = self.form_state().prepare_job_files(dry_run=True)
                except Exception as exc:
                    self.command_preview.setPlainText(f"Error: {exc}")
                    self.status_label.setText(str(exc))
                    return
                self.current_layout = layout
                self.command_preview.setPlainText(layout.command_path.read_text(encoding="utf-8"))
                self.status_label.setText(f"Command saved: {layout.command_path}")

            def copy_command(self) -> None:
                QtGui.QGuiApplication.clipboard().setText(self.command_preview.toPlainText())

            def start_runner(self, *, dry_run: bool) -> None:
                try:
                    self.current_layout = self.form_state().prepare_job_files(dry_run=dry_run)
                except Exception as exc:
                    self.status_label.setText(str(exc))
                    return

                self.event_state = RunnerEventState()
                self.queue_table.setRowCount(0)
                self.log_widget.clear()
                args = [
                    "-m",
                    "app",
                    "run",
                    "--config",
                    str(self.current_layout.config_snapshot_path),
                    "--output-dir",
                    str(self.current_layout.root),
                    "--events-jsonl",
                ]
                if dry_run:
                    args.append("--dry-run")

                self.process = QtCore.QProcess(self)
                env = QtCore.QProcessEnvironment.systemEnvironment()
                if os.environ.get("GPT_IMAGE_BATCH_MOCK_API") == "1":
                    env.insert("GPT_IMAGE_BATCH_MOCK_API", "1")
                self.process.setProcessEnvironment(env)
                self.process.setProgram(sys.executable)
                self.process.setArguments(args)
                self.process.readyReadStandardOutput.connect(self._read_stdout)
                self.process.readyReadStandardError.connect(self._read_stderr)
                self.process.finished.connect(self._process_finished)
                self.process.start()
                self.status_label.setText("Running dry-run" if dry_run else "Running")

            def _read_stdout(self) -> None:
                if self.process is None:
                    return
                text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
                self._stdout_buffer += text
                while "\n" in self._stdout_buffer:
                    line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
                    self.handle_stdout_line(line)

            def _read_stderr(self) -> None:
                if self.process is None:
                    return
                text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
                self.log_widget.appendPlainText(_redact(text.rstrip()))

            def handle_stdout_line(self, line: str) -> None:
                if not line.strip():
                    return
                try:
                    event = EventProtocol.parse_line(line)
                except EventProtocolError:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        self.log_widget.appendPlainText(_redact(line))
                        return
                self.handle_runner_event(event)

            def handle_runner_event(self, event: dict[str, Any]) -> None:
                self.event_state.handle_runner_event(event)
                self._sync_table()
                self.log_widget.appendPlainText(_redact(json.dumps(event, sort_keys=True, default=str)))
                self.status_label.setText(
                    f"{self.event_state.completed_tasks} completed, "
                    f"{self.event_state.failed_tasks} failed, "
                    f"{self.event_state.total_tasks} total"
                )

            def _sync_table(self) -> None:
                self.queue_table.setRowCount(len(self.event_state.rows))
                for row_index, row in enumerate(self.event_state.rows.values()):
                    for col_index, key in enumerate(["task_id", "status", "message"]):
                        self.queue_table.setItem(row_index, col_index, QtWidgets.QTableWidgetItem(row[key]))

            def _process_finished(self, exit_code: int, exit_status) -> None:
                if self._stdout_buffer.strip():
                    self.handle_stdout_line(self._stdout_buffer.strip())
                self._stdout_buffer = ""
                self.status_label.setText(f"Runner exited with code {exit_code}")

            def write_control(self, payload: dict[str, bool]) -> None:
                if self.current_layout is None:
                    self.status_label.setText("No active job layout")
                    return
                control_path = self.current_layout.root / "job.control.json"
                control_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                self.status_label.setText(f"Control written: {control_path.name}")

        return _MainWindow()


def _combo(QtWidgets, values: list[str], current: str):
    combo = QtWidgets.QComboBox()
    combo.addItems(values)
    combo.setCurrentText(current)
    return combo


def _optional_path(text: str) -> Path | None:
    stripped = text.strip()
    return Path(stripped) if stripped else None


def _redact(text: str) -> str:
    if "sk-" not in text:
        return text
    return text.split("sk-", 1)[0] + "sk-[REDACTED]"


__all__ = ["GuiFormState", "MainWindow", "RunnerEventState", "launch_gui"]
