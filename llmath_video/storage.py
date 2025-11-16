from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Sequence
import logging

from flask import url_for
from werkzeug.datastructures import FileStorage
import base64


@dataclass(frozen=True)
class FileRecord:
    name: str
    url: str


class VideoStore:
    def __init__(self, video_dir: str, allowed_extensions: Sequence[str]):
        self.video_dir = video_dir
        self.allowed_extensions = {ext.lower() for ext in allowed_extensions}

    def allowed_file(self, filename: str) -> bool:
        _, ext = os.path.splitext((filename or "").lower())
        return ext in self.allowed_extensions

    def list_videos(self) -> List[FileRecord]:
        videos = []
        for name in os.listdir(self.video_dir):
            file_path = os.path.join(self.video_dir, name)
            if os.path.isfile(file_path) and self.allowed_file(name):
                videos.append(
                    {
                        "name": name,
                        "mtime": os.path.getmtime(file_path),
                        "url": url_for("media.serve_video", filename=name),
                    }
                )
        videos.sort(key=lambda x: x["mtime"], reverse=True)
        for v in videos:
            v.pop("mtime", None)
        return [FileRecord(**v) for v in videos]

    def sanitize_name(self, filename: str) -> str:
        filename = os.path.basename(filename or "")
        if not filename:
            raise ValueError("Некорректное имя файла")
        base, ext = os.path.splitext(filename)
        if not self.allowed_file(filename):
            raise ValueError("Неподдерживаемый тип файла")
        allowed_chars = " ._()-"
        safe_base = "".join(
            ch for ch in base if ch.isalnum() or ch in allowed_chars
        ).strip()
        if not safe_base:
            safe_base = "video"
        return f"{safe_base}{ext}"

    def save(self, storage: FileStorage) -> str:
        filename = self.sanitize_name(storage.filename or "")
        save_path = os.path.join(self.video_dir, filename)
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            new_name = f"{base}_{counter}{ext}"
            save_path = os.path.join(self.video_dir, new_name)
            counter += 1
        storage.save(save_path)
        return os.path.basename(save_path)

    def path_for(self, name: str) -> str:
        return os.path.join(self.video_dir, os.path.basename(name))

    def delete_related(self, name: str, paths: Sequence[str]) -> List[str]:
        deleted = []
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(os.path.basename(path))
            except Exception:
                continue
        return deleted


class SubtitleStore:
    def __init__(self, directory: str):
        self.directory = directory

    def path_for(self, name: str) -> str:
        os.makedirs(self.directory, exist_ok=True)
        return os.path.join(self.directory, f"{os.path.basename(name)}.json")

    def read_segments(self, name: str):
        path = self.path_for(name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return (json.load(f).get("segments") or [])
        return []

    def write_segments(self, name: str, segments):
        path = self.path_for(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"segments": segments}, f, ensure_ascii=False)
        return path


class SummaryStore:
    def __init__(self, directory: str):
        self.directory = directory

    def path_for(self, name: str) -> str:
        os.makedirs(self.directory, exist_ok=True)
        return os.path.join(self.directory, f"{os.path.basename(name)}.txt")

    def read(self, name: str) -> str:
        path = self.path_for(name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def write(self, name: str, content: str):
        path = self.path_for(name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path


class SuggestionStore:
    def __init__(self, directory: str):
        self.directory = directory

    def path_for(self, name: str) -> str:
        os.makedirs(self.directory, exist_ok=True)
        return os.path.join(self.directory, f"{os.path.basename(name)}.json")

    def read(self, name: str):
        path = self.path_for(name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def write_items(self, name: str, items):
        path = self.path_for(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False)
        return path


class LogStore:
    def __init__(self, directory: str):
        self.directory = directory
        self.logger = logging.getLogger("llmath_video.logstore")

    def path_for(self, name: str) -> str:
        os.makedirs(self.directory, exist_ok=True)
        safe_name = os.path.basename(name)
        return os.path.join(self.directory, f"{safe_name}.log")

    def append(self, name: str, entry: dict):
        path = self.path_for(name)
        line = json.dumps(dict(entry), ensure_ascii=False)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        try:
            safe = os.path.basename(name)
            log_type = (entry or {}).get("type") or ""
            if str(log_type).lower() == "error":
                self.logger.error(f"[LOG:{safe}] {line}")
            else:
                self.logger.info(f"[LOG:{safe}] {line}")
        except Exception:
            pass

    def read_entries(self, name: str):
        path = self.path_for(name)
        entries = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
        return entries

    def clear(self, name: str):
        path = self.path_for(name)
        if os.path.exists(path):
            os.remove(path)


class FrameStore:
    def __init__(self, directory: str):
        self.directory = directory

    def save_data_url(self, video_name: str, image_data_url: str) -> str | None:
        try:
            header, b64 = image_data_url.split(",", 1)
            img_bytes = base64.b64decode(b64)
        except Exception:
            return None
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = os.path.splitext(os.path.basename(video_name))[0]
        subdir = os.path.join(self.directory, safe_name)
        os.makedirs(subdir, exist_ok=True)
        file_path = os.path.join(subdir, f"frame-{ts}.png")
        with open(file_path, "wb") as f:
            f.write(img_bytes)
        return os.path.relpath(file_path, self.directory).replace("\\", "/")

    def resolve(self, rel_path: str) -> str:
        safe_path = os.path.abspath(os.path.join(self.directory, rel_path))
        base = os.path.abspath(self.directory)
        if not safe_path.startswith(base):
            raise ValueError("invalid path")
        return safe_path

