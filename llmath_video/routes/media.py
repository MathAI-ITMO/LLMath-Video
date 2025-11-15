from __future__ import annotations

import os

from flask import (
    Blueprint,
    jsonify,
    request,
    send_from_directory,
    url_for,
)

from ..processing import ProcessingService
from ..storage import FrameStore, SubtitleStore, VideoStore


def register(
    app,
    video_store: VideoStore,
    subtitle_store: SubtitleStore,
    frame_store: FrameStore,
    dirs: dict,
    processing_service: ProcessingService,
):
    bp = Blueprint("media", __name__)

    @bp.route("/videos", methods=["GET"])
    def list_videos():
        records = video_store.list_videos()
        return jsonify([r.__dict__ for r in records])

    @bp.route("/video/<path:filename>")
    def serve_video(filename):
        return send_from_directory(dirs["video"], filename, as_attachment=False)

    @bp.route("/video/<path:filename>", methods=["DELETE"])
    def delete_video(filename):
        filename = os.path.basename(filename)
        video_path = os.path.join(dirs["video"], filename)
        base, _ = os.path.splitext(filename)
        audio_path = os.path.join(dirs["audio"], f"{base}.mp3")
        subs_path = subtitle_store.path_for(filename)
        sugg_path = os.path.join(dirs["suggestions"], f"{filename}.json")
        errors = []
        deleted = []
        for path in (video_path, audio_path, subs_path, sugg_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(os.path.basename(path))
            except Exception as e:
                errors.append(str(e))
        status = 200 if not errors else 207
        return jsonify({"deleted": deleted, "errors": errors}), status

    @bp.route("/upload", methods=["POST"])
    def upload_video():
        if "file" not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        try:
            name = video_store.save(file)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        save_path = os.path.join(dirs["video"], name)
        processing_service.queue(save_path)
        return (
            jsonify(
                {
                    "name": name,
                    "url": url_for("media.serve_video", filename=name),
                }
            ),
            201,
        )

    @bp.route("/api/ensure_processed", methods=["POST"])
    def api_ensure_processed():
        data = request.get_json(silent=True) or {}
        name = (
            request.args.get("name")
            or (data.get("name") if isinstance(data, dict) else None)
            or request.form.get("name")
            or ""
        )
        name = os.path.basename(name)
        if not name:
            return jsonify({"status": "error", "error": "missing name"}), 400
        video_path = video_store.path_for(name)
        if not os.path.isfile(video_path):
            return jsonify({"status": "error", "error": "not found"}), 404
        processing_service.queue(video_path)
        return jsonify({"status": "queued"})

    @bp.route("/subtitles/<path:filename>.json")
    def serve_subtitles(filename):
        segments = subtitle_store.read_segments(filename)
        return jsonify({"segments": segments})

    @bp.route("/frames/<path:filename>")
    def serve_frame(filename):
        try:
            safe_path = frame_store.resolve(filename)
        except ValueError:
            return jsonify({"error": "invalid path"}), 400
        if not os.path.isfile(safe_path):
            return jsonify({"error": "not found"}), 404
        return send_from_directory(
            os.path.dirname(safe_path),
            os.path.basename(safe_path),
            as_attachment=False,
        )

    @bp.route("/favicon.ico")
    def favicon():
        return ("", 204)

    app.register_blueprint(bp)

