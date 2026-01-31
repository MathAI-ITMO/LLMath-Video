import os

from flask import Flask
from flask_cors import CORS

from config_manager import (
    get_url_prefix,
    is_cors_disabled,
    load_config,
    resolve_cors_origins,
)
from llmath_video import load_settings
from llmath_video.logging_setup import setup_logging
from llmath_video.processing import ProcessingService
from llmath_video.routes import content, llm_routes, main, media
from llmath_video.storage import (
    FrameStore,
    LogStore,
    SubtitleStore,
    SuggestionStore,
    SummaryStore,
    VideoStore,
)


def _prefix_middleware(wsgi_app, prefix):
    """WSGI middleware that mounts the app at a URL prefix (e.g. /some-path)."""

    def wrapper(environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        if path.startswith(prefix):
            environ["SCRIPT_NAME"] = prefix
            environ["PATH_INFO"] = path[len(prefix) :] or "/"
        return wsgi_app(environ, start_response)

    return wrapper


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_url_path="/static",
        static_folder="static",
        template_folder="templates",
    )
    base_dir = os.path.abspath(os.path.dirname(__file__))
    settings = load_settings(base_dir)
    setup_logging(settings.dirs.logs, level="INFO")
    app.config["APP_SETTINGS"] = settings.as_dict()
    app.config["JSON_AS_ASCII"] = False

    if not is_cors_disabled():
        cors_origins = resolve_cors_origins(settings.config)
        CORS(app, resources={r"/*": {"origins": cors_origins}})

    video_store = VideoStore(
        settings.dirs.video, settings.allowed_extensions
    )
    subtitle_store = SubtitleStore(settings.dirs.subtitles)
    summary_store = SummaryStore(settings.dirs.summaries)
    suggestion_store = SuggestionStore(settings.dirs.suggestions)
    log_store = LogStore(settings.dirs.logs)
    frame_store = FrameStore(settings.dirs.frames)

    dir_map = {
        "video": settings.dirs.video,
        "audio": settings.dirs.audio,
        "subtitles": settings.dirs.subtitles,
        "frames": settings.dirs.frames,
        "summaries": settings.dirs.summaries,
        "logs": settings.dirs.logs,
        "suggestions": settings.dirs.suggestions,
        "base": settings.base_dir,
    }
    processing_service = ProcessingService(
        settings.llm_config,
        settings.config,
        dir_map,
        log_store,
        summary_store,
    )

    main.register(app, video_store, settings.config)
    media.register(
        app,
        video_store,
        subtitle_store,
        frame_store,
        dir_map,
        processing_service,
    )
    content.register(
        app,
        summary_store,
        suggestion_store,
        subtitle_store,
        log_store,
        settings.llm_config,
        settings.config,
    )
    llm_routes.register(
        app,
        frame_store,
        summary_store,
        subtitle_store,
        log_store,
        settings.llm_config,
        settings.config,
    )

    url_prefix = get_url_prefix(load_config(base_dir))
    if url_prefix:
        app.wsgi_app = _prefix_middleware(app.wsgi_app, url_prefix)

    return app


if __name__ == "__main__":
    application = create_app()
    base_dir = os.path.abspath(os.path.dirname(__file__))
    server_config = load_config(base_dir).get("server", {})
    host = os.environ.get(
        "FLASK_RUN_HOST", server_config.get("host", "0.0.0.0")
    )
    port = int(os.environ.get("FLASK_RUN_PORT", server_config.get("port", 5001)))
    application.run(host=host, port=port, debug=True)
