"""
MediaConvert — Flask Backend
A media URL converter powered by yt-dlp.
Converts YouTube and Instagram URLs to MP3/MP4 formats.
"""

import os
import uuid
import threading
import sqlite3
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify,
    Response, stream_with_context
)
import yt_dlp

# ──────────────────────────────────────────────
# App Configuration
# ──────────────────────────────────────────────
app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "mediaconvert.db"

# In-memory task status tracker
tasks = {}

# ──────────────────────────────────────────────
# Database Helpers
# ──────────────────────────────────────────────

def get_db():
    """Return a new database connection with Row factory."""
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the conversions table if it does not exist."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         TEXT UNIQUE NOT NULL,
            original_url    TEXT NOT NULL,
            platform        TEXT,
            format          TEXT NOT NULL,
            filename        TEXT,
            filesize        INTEGER,
            status          TEXT DEFAULT 'queued',
            error_message   TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at    TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_conversion(task_id, url, platform, fmt):
    """Insert a new conversion record."""
    conn = get_db()
    conn.execute(
        """INSERT INTO conversions
           (task_id, original_url, platform, format, status)
           VALUES (?, ?, ?, ?, 'queued')""",
        (task_id, url, platform, fmt),
    )
    conn.commit()
    conn.close()


def update_conversion(task_id, **kwargs):
    """Update fields on an existing conversion record."""
    conn = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [task_id]
    conn.execute(f"UPDATE conversions SET {sets} WHERE task_id = ?", vals)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────

def detect_platform(url: str) -> str:
    """Detect the source platform from a URL."""
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "instagram.com" in url_lower:
        return "instagram"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    return "other"


def cleanup_stale_tasks(max_age_hours=1):
    """Clean up any abandoned task temp directories older than max_age_hours."""
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    abandoned_ids = []
    
    for tid, tinfo in tasks.items():
        # Clean if done/error and it's been in the dict for a long time
        # For simplicity, we just check if it's over the cutoff we can just wipe it
        if "created_at" not in tinfo:
            tinfo["created_at"] = datetime.now()
            
        if tinfo["created_at"] < cutoff:
            abandoned_ids.append(tid)
            if "temp_dir" in tinfo and os.path.exists(tinfo["temp_dir"]):
                try:
                    shutil.rmtree(tinfo["temp_dir"], ignore_errors=True)
                except:
                    pass
                    
    for tid in abandoned_ids:
        tasks.pop(tid, None)


def run_conversion(task_id: str, url: str, fmt: str):
    """
    Background worker: download and convert a media URL.
    Updates in-memory task dict and SQLite record.
    """
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["created_at"] = datetime.now()
    update_conversion(task_id, status="processing")

    temp_dir = tempfile.mkdtemp(prefix=f"media_cv_{task_id}_")
    tasks[task_id]["temp_dir"] = temp_dir
    
    output_template = os.path.join(temp_dir, f"{task_id}.%(ext)s")

    try:
        shared_ydl_opts = {
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {"youtube": ["player_client=ios,android"]},
            "impersonate": "chrome",
            "source_address": "0.0.0.0",
        }
        if fmt == "mp3":
            ydl_opts = {
                **shared_ydl_opts,
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
        else:  # mp4
            ydl_opts = {
                **shared_ydl_opts,
                "format": "b[ext=mp4]/best",
                "merge_output_format": "mp4",
            }

        # Progress hook
        def progress_hook(d):
            if d["status"] == "downloading":
                pct = d.get("_percent_str", "0%").strip()
                tasks[task_id]["progress"] = pct
            elif d["status"] == "finished":
                tasks[task_id]["progress"] = "100%"

        ydl_opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "media")

        # Find the output file
        ext = "mp3" if fmt == "mp3" else "mp4"
        output_file = Path(temp_dir) / f"{task_id}.{ext}"

        if not output_file.exists():
            # Sometimes the extension differs; find any file with the task_id
            candidates = list(Path(temp_dir).glob(f"{task_id}.*"))
            if candidates:
                output_file = candidates[0]
                ext = output_file.suffix.lstrip(".")
            else:
                raise FileNotFoundError("Converted file not found on disk.")

        filesize = output_file.stat().st_size
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
        filename = f"{safe_title}.{ext}" if safe_title else f"media.{ext}"

        tasks[task_id].update({
            "status": "done",
            "progress": "100%",
            "filename": filename,
            "filepath": str(output_file),
            "filesize": filesize,
        })
        update_conversion(
            task_id,
            status="done",
            filename=filename,
            filesize=filesize,
            completed_at=datetime.now().isoformat(),
        )

    except Exception as exc:
        error_msg = str(exc)
        tasks[task_id].update({"status": "error", "error": error_msg})
        update_conversion(task_id, status="error", error_message=error_msg)


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the single-page application."""
    return render_template("index.html")


@app.route("/api/convert", methods=["POST"])
def api_convert():
    """Accept a URL + format and start a background conversion."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp3").lower()

    # Validation
    if not url:
        return jsonify({"error": "URL is required."}), 400
    if fmt not in ("mp3", "mp4"):
        return jsonify({"error": "Format must be mp3 or mp4."}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL. Must start with http:// or https://"}), 400

    task_id = uuid.uuid4().hex
    platform = detect_platform(url)

    # Initialize task tracking
    tasks[task_id] = {
        "status": "queued",
        "progress": "0%",
        "url": url,
        "format": fmt,
        "platform": platform,
    }

    save_conversion(task_id, url, platform, fmt)

    # Run cleanup in background periodically
    threading.Thread(target=cleanup_stale_tasks, daemon=True).start()

    # Start conversion in background
    thread = threading.Thread(target=run_conversion, args=(task_id, url, fmt), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id, "status": "queued"}), 202


@app.route("/api/status/<task_id>")
def api_status(task_id):
    """Return the current status of a conversion task."""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404

    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", "0%"),
    }
    if task["status"] == "done":
        response["filename"] = task.get("filename")
        response["filesize"] = task.get("filesize")
    elif task["status"] == "error":
        response["error"] = task.get("error", "Unknown error")

    return jsonify(response)


@app.route("/api/download/<task_id>")
def api_download(task_id):
    """Stream the converted file to the user and delete its directory securely."""
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        return jsonify({"error": "File not ready or task not found."}), 404

    filepath = task.get("filepath")
    temp_dir = task.get("temp_dir")
    
    if not filepath or not Path(filepath).exists():
        return jsonify({"error": "File no longer available."}), 410

    filename = task.get("filename", "download")

    def generate():
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
        finally:
            # Secure clean-up after streaming finishes
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            # Remove from tasks to free memory and prevent re-download
            tasks.pop(task_id, None)

    return Response(
        stream_with_context(generate()),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/octet-stream"
        }
    )


@app.route("/api/history")
def api_history():
    """Return all conversion records from the database."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM conversions ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    history = []
    for row in rows:
        history.append({
            "task_id": row["task_id"],
            "url": row["original_url"],
            "platform": row["platform"],
            "format": row["format"],
            "filename": row["filename"],
            "filesize": row["filesize"],
            "status": row["status"],
            "error": row["error_message"],
            "created_at": str(row["created_at"]).replace(" ", "T") + "Z" if row["created_at"] else None,
            "completed_at": str(row["completed_at"]).replace(" ", "T") + "Z" if row["completed_at"] else None,
        })

    return jsonify(history)


@app.route("/api/history/<task_id>", methods=["DELETE"])
def api_history_delete(task_id):
    """Delete a conversion record from the database."""
    conn = get_db()
    conn.execute("DELETE FROM conversions WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"}), 200


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    print("=" * 50)
    print("  MediaConvert is running!")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
