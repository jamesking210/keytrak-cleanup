import logging
import os
import re
import shutil
import smtplib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
LOG_DIR = BASE_DIR / "logs"
TMP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

APP_TITLE = os.getenv("APP_TITLE", "KeyTrak Cleanup")
APP_SUBTITLE = os.getenv(
    "APP_SUBTITLE",
    "Upload Zeus and KeyTrak inventory files, compare them, preview the cleanup list, and email yourself a copy.",
)
APP_PORT = int(os.getenv("APP_PORT", "8088"))
RESULT_RETENTION_MINUTES = int(os.getenv("RESULT_RETENTION_MINUTES", "30"))
MAX_CONTENT_LENGTH_MB = int(os.getenv("MAX_CONTENT_LENGTH_MB", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").strip().lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_TO = os.getenv("SMTP_TO", "")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH_MB * 1024 * 1024


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("keytrak_cleanup")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


logger = setup_logging()


@dataclass
class Task:
    id: str
    created_at: datetime
    status: str = "queued"
    message: str = "Waiting to start."
    error: Optional[str] = None
    summary: Dict[str, int] = field(default_factory=dict)
    result_filename: Optional[str] = None
    result_path: Optional[Path] = None
    preview_rows: List[Dict[str, str]] = field(default_factory=list)
    email_sent_to: Optional[str] = None
    cleanup_at: Optional[datetime] = None


TASKS: Dict[str, Task] = {}
TASKS_LOCK = threading.Lock()


class ProcessingError(Exception):
    pass


def normalize_stock(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"\s+", "", text)
    return text.upper()


def allowed_csv(filename: str) -> bool:
    return filename.lower().endswith(".csv")


def read_zeus_csv(path: Path) -> pd.DataFrame:
    logger.info("Reading Zeus CSV: %s", path.name)
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="latin-1")

    if len(df.columns) < 2:
        raise ProcessingError(
            "Zeus file does not have enough columns. Expected stock number in column 2."
        )

    stock_col = df.columns[1]
    df = df.copy()
    df[stock_col] = df[stock_col].apply(normalize_stock)
    df = df[df[stock_col] != ""]
    df = df.drop_duplicates(subset=[stock_col])
    df.attrs["stock_column"] = stock_col
    logger.info("Zeus rows after cleanup: %s", len(df))
    return df


def read_keytrak_csv(path: Path) -> pd.DataFrame:
    logger.info("Reading KeyTrak CSV: %s", path.name)
    try:
        df = pd.read_csv(
            path, dtype=str, keep_default_na=False, skiprows=2, encoding="utf-8-sig"
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            path, dtype=str, keep_default_na=False, skiprows=2, encoding="latin-1"
        )

    if len(df.columns) < 1:
        raise ProcessingError(
            "KeyTrak file does not have any columns. Expected stock number in column 1."
        )

    stock_col = df.columns[0]
    df = df.copy()
    df[stock_col] = df[stock_col].apply(normalize_stock)
    df = df[df[stock_col] != ""]
    df = df.drop_duplicates(subset=[stock_col])
    df.attrs["stock_column"] = stock_col
    logger.info("KeyTrak rows after cleanup: %s", len(df))
    return df


def build_result_dataframe(zeus_df: pd.DataFrame, keytrak_df: pd.DataFrame) -> pd.DataFrame:
    zeus_stock_col = zeus_df.attrs["stock_column"]
    keytrak_stock_col = keytrak_df.attrs["stock_column"]

    zeus_stock_set = set(zeus_df[zeus_stock_col].tolist())
    result_df = keytrak_df[~keytrak_df[keytrak_stock_col].isin(zeus_stock_set)].copy()
    result_df.insert(0, "Status", "In KeyTrak, not in Zeus (likely sold/stale)")
    result_df.insert(1, "Normalized Stock #", result_df[keytrak_stock_col])
    result_df = result_df.sort_values(by=[keytrak_stock_col], kind="stable").reset_index(drop=True)

    logger.info(
        "Compare complete. Zeus rows=%s | KeyTrak rows=%s | Result rows=%s",
        len(zeus_df),
        len(keytrak_df),
        len(result_df),
    )
    return result_df


def write_result_csv(result_df: pd.DataFrame, task_dir: Path, task_id: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"keytrak_cleanup_{timestamp}_{task_id[:8]}.csv"
    path = task_dir / filename
    result_df.to_csv(path, index=False)
    logger.info("Result CSV written: %s", path)
    return path


def send_email_with_attachment(recipient: str, result_path: Path, summary: Dict[str, int]) -> None:
    if not SMTP_ENABLED:
        raise ProcessingError(
            "SMTP is disabled. This app is email-only, so set SMTP_ENABLED=true and fill in your mail settings."
        )
    if not recipient:
        raise ProcessingError("No email recipient provided.")
    if not SMTP_HOST or not SMTP_FROM:
        raise ProcessingError("SMTP settings are incomplete. SMTP_HOST and SMTP_FROM are required.")

    logger.info("Preparing email to %s with attachment %s", recipient, result_path.name)

    subject = f"{APP_TITLE} results - {datetime.now().strftime('%Y-%m-%d %I:%M %p')}"
    body = (
        f"Your KeyTrak cleanup run is complete.\n\n"
        f"Zeus rows: {summary.get('zeus_rows', 0)}\n"
        f"KeyTrak rows: {summary.get('keytrak_rows', 0)}\n"
        f"Likely sold/stale units still in KeyTrak: {summary.get('result_rows', 0)}\n\n"
        f"The CSV is attached."
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg.set_content(body)

    with open(result_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype="csv", filename=result_path.name)

    if SMTP_USE_SSL:
        logger.info("Sending email using SMTP SSL to %s:%s", SMTP_HOST, SMTP_PORT)
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
    else:
        logger.info("Sending email using SMTP to %s:%s | TLS=%s", SMTP_HOST, SMTP_PORT, SMTP_USE_TLS)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

    logger.info("Email sent successfully to %s", recipient)


def set_task(task_id: str, **kwargs) -> None:
    with TASKS_LOCK:
        task = TASKS[task_id]
        for key, value in kwargs.items():
            setattr(task, key, value)


def task_to_dict(task: Task) -> Dict[str, object]:
    return {
        "id": task.id,
        "status": task.status,
        "message": task.message,
        "error": task.error,
        "summary": task.summary,
        "preview_rows": task.preview_rows,
        "email_sent_to": task.email_sent_to,
        "result_filename": task.result_filename,
        "created_at": task.created_at.isoformat(),
    }


def cleanup_task_files(task_id: str) -> None:
    task_dir = TMP_DIR / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)
        logger.info("Cleaned task files for task %s", task_id)


def cleanup_old_tasks(force_all_completed: bool = False) -> None:
    now = datetime.now()
    stale_ids: List[str] = []

    with TASKS_LOCK:
        for task_id, task in list(TASKS.items()):
            if task.status in {"processing", "queued"}:
                continue
            if force_all_completed or (task.cleanup_at and now >= task.cleanup_at):
                stale_ids.append(task_id)

        for task_id in stale_ids:
            TASKS.pop(task_id, None)

    for task_id in stale_ids:
        cleanup_task_files(task_id)

    if stale_ids:
        logger.info("Removed stale completed tasks: %s", ", ".join(stale_ids))


def process_files(task_id: str, zeus_path: Path, keytrak_path: Path, recipient: str) -> None:
    task_dir = TMP_DIR / task_id
    logger.info("Task %s started", task_id)

    try:
        set_task(task_id, status="processing", message="Reading Zeus inventory file...")
        zeus_df = read_zeus_csv(zeus_path)

        set_task(task_id, status="processing", message="Reading KeyTrak inventory file...")
        keytrak_df = read_keytrak_csv(keytrak_path)

        set_task(task_id, status="processing", message="Comparing KeyTrak against Zeus truth source...")
        result_df = build_result_dataframe(zeus_df, keytrak_df)

        result_path = write_result_csv(result_df, task_dir, task_id)
        preview_rows = result_df.head(25).fillna("").to_dict(orient="records")
        summary = {
            "zeus_rows": int(len(zeus_df)),
            "keytrak_rows": int(len(keytrak_df)),
            "result_rows": int(len(result_df)),
        }

        set_task(
            task_id,
            message="Sending email...",
            summary=summary,
            preview_rows=preview_rows,
            result_filename=result_path.name,
            result_path=result_path,
        )

        for file_path in [zeus_path, keytrak_path]:
            try:
                file_path.unlink(missing_ok=True)
            except TypeError:
                if file_path.exists():
                    file_path.unlink()
        logger.info("Uploaded source files deleted for task %s", task_id)

        send_email_with_attachment(recipient, result_path, summary)

        set_task(
            task_id,
            status="done",
            message="Done. Your cleanup CSV has been emailed.",
            email_sent_to=recipient,
            cleanup_at=datetime.now() + timedelta(minutes=RESULT_RETENTION_MINUTES),
        )
        logger.info("Task %s completed successfully", task_id)

    except Exception as exc:
        logger.exception("Task %s failed", task_id)
        set_task(
            task_id,
            status="error",
            message="Processing failed.",
            error=str(exc),
            cleanup_at=datetime.now() + timedelta(minutes=RESULT_RETENTION_MINUTES),
        )


@app.get("/")
def index():
    logger.info("Homepage loaded")
    return render_template(
        "index.html",
        app_title=APP_TITLE,
        app_subtitle=APP_SUBTITLE,
        smtp_default_to=SMTP_TO,
        smtp_enabled=SMTP_ENABLED,
    )


@app.post("/upload")
def upload():
    cleanup_old_tasks(force_all_completed=False)

    zeus_file = request.files.get("zeus_file")
    keytrak_file = request.files.get("keytrak_file")
    recipient = (request.form.get("email_to") or SMTP_TO).strip()

    if not SMTP_ENABLED:
        logger.warning("Upload rejected: SMTP is disabled in email-only mode")
        return jsonify(
            {
                "error": "SMTP is not enabled. This app is email-only, so set SMTP_ENABLED=true in .env before running a job."
            }
        ), 400

    if not zeus_file or not zeus_file.filename:
        logger.warning("Upload rejected: missing Zeus file")
        return jsonify({"error": "Please choose the Zeus CSV file."}), 400

    if not keytrak_file or not keytrak_file.filename:
        logger.warning("Upload rejected: missing KeyTrak file")
        return jsonify({"error": "Please choose the KeyTrak CSV file."}), 400

    if not allowed_csv(zeus_file.filename) or not allowed_csv(keytrak_file.filename):
        logger.warning("Upload rejected: non-CSV file uploaded")
        return jsonify({"error": "Both files must be CSV files."}), 400

    if not recipient:
        logger.warning("Upload rejected: no recipient provided")
        return jsonify({"error": "Please provide an email address or set SMTP_TO in the environment."}), 400

    task_id = uuid.uuid4().hex
    task_dir = TMP_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    zeus_filename = secure_filename(zeus_file.filename)
    keytrak_filename = secure_filename(keytrak_file.filename)
    zeus_path = task_dir / zeus_filename
    keytrak_path = task_dir / keytrak_filename
    zeus_file.save(zeus_path)
    keytrak_file.save(keytrak_path)

    logger.info(
        "Upload accepted. Task=%s | Zeus=%s | KeyTrak=%s | Recipient=%s",
        task_id,
        zeus_filename,
        keytrak_filename,
        recipient,
    )

    task = Task(id=task_id, created_at=datetime.now(), message="Files uploaded. Starting processor...")
    with TASKS_LOCK:
        TASKS[task_id] = task

    thread = threading.Thread(
        target=process_files,
        args=(task_id, zeus_path, keytrak_path, recipient),
        daemon=True,
        name=f"task-{task_id[:8]}",
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.get("/status/<task_id>")
def status(task_id: str):
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        if not task:
            logger.warning("Status requested for missing task %s", task_id)
            return jsonify({"error": "Task not found or already cleaned up."}), 404
        return jsonify(task_to_dict(task))


@app.post("/cleanup/<task_id>")
def cleanup(task_id: str):
    with TASKS_LOCK:
        task = TASKS.pop(task_id, None)
    cleanup_task_files(task_id)
    logger.info("Manual cleanup requested for task %s", task_id)
    if task is None:
        return jsonify({"ok": True, "message": "Already cleaned up."})
    return jsonify({"ok": True})


if __name__ == "__main__":
    logger.info("Starting Flask dev server on port %s", APP_PORT)
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
