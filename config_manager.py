import json
import os
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from dotenv import load_dotenv

DEFAULT_CONFIG = {
    "subtitles_panel_enabled": True,
    "server": {
        "host": "0.0.0.0",
        "port": 5001
    },
    "cors": {
        "origins": ["http://localhost:8080", "http://127.0.0.1:8080"]
    }
}

LLM_DEFAULTS = {
    "openai_api_key": "",
    "openai_api_base": "https://api.openai.com/v1",
    "openai_model": "gpt-5-nano",
    "transcription_mode": "openai",
    "openai_stt_model": "whisper-1",
    "whisper_model": "tiny",
    "whisper_language": "ru"
}

DATA_SUBDIRS = {
    "video": ("data", "video"),
    "audio": ("data", "audio"),
    "subtitles": ("data", "subtitles"),
    "frames": ("data", "frames"),
    "summaries": ("data", "summaries"),
    "logs": ("data", "logs"),
    "suggestions": ("data", "suggestions"),
}

PROMPT_DEFAULTS = {
    "frame_system": "Ты выступаешь в роли лектора. Если к теории подходят формулы, можешь использовать LaTeX.",
    "frame_user_template": (
        "Лекция: {lecture}\n"
        "Краткое содержание: {summary}\n\n"
        "Мы находимся в разделе:\n{context}\n\n"
        "На изображении выделен красным полупрозрачным кругом интересующий фрагмент. "
        "Дай пояснение по этому фрагменту."
    ),
    "summary": (
        "Ты опытный лектор. Сформируй краткое описание лекции и перечисли основные вопросы, "
        "которые были разобраны. Ответ на русском языке. Текст лекции ниже:\n\n{transcript}"
    ),
    "suggestions": (
        "Ты помощник студента, который смотрит видео-лекцию. Тебе дан полный транскрипт "
        "с пометками времени начала реплик в формате [HH:mm:ss]. На основе этого текста "
        "составь МНОГО коротких, конкретных и уместных вопросов, которые студент может "
        "задать преподавателю, когда соответствует обсуждаемой теме.\n\n"
        "Правила составления вопросов:\n"
        "- Каждый вопрос максимально короткий (желательно до 8-12 слов).\n"
        "- Вопросы формулируй так, чтобы они перекрывали всю длительность видео.\n"
        "- У каждого вопроса должен быть интервал актуальности (start/end в HH:mm:ss), "
        "в течение которого этот вопрос уместен. Интервалы ДОЛЖНЫ перекрываться, "
        "чтобы в любой момент времени было несколько релевантных вопросов.\n"
        "- Привязывай вопросы к содержанию лекции: терминам, определениям, шагам, примерам.\n"
        "- Верни ТОЛЬКО JSON-массив объектов вида:\n"
        "  [{\"text\":\"...\",\"start\":\"HH:mm:ss\",\"end\":\"HH:mm:ss\"}, ...]\n"
        "- Без дополнительного текста, без комментариев и пояснений. Только JSON.\n\n"
        "Транскрипт с тайм-кодами:\n{timecoded_transcript}"
    ),
    "chat_user_template": (
        "Лекция: {lecture}\nКраткое содержание: {summary}\n\n"
        "Мы находимся в разделе:\n{context}\n\n"
        "Предыдущий диалог:\n{history}\n\n"
        "У студента возник новый вопрос: {question}"
    ),
    "chat_system": "Ты выступаешь в роли лектора, отвечай четко и по делу."
}


def load_config(base_dir: str) -> Dict:
    """
    Load config.json, creating it with defaults if necessary, and load .env.
    """
    load_dotenv(os.path.join(base_dir, ".env"))
    config_path = os.path.join(base_dir, "config.json")
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_data_directories(base_dir: str) -> Dict[str, str]:
    """
    Create required data directories inside the project and return their paths.
    """
    resolved_dirs: Dict[str, str] = {}
    for key, segments in DATA_SUBDIRS.items():
        path = os.path.join(base_dir, *segments)
        os.makedirs(path, exist_ok=True)
        resolved_dirs[key] = path
    return resolved_dirs


def build_llm_config(
    config: Mapping[str, str],
    env: Optional[MutableMapping[str, str]] = None
) -> Dict[str, str]:
    """
    Merge environment overrides with config values for LLM-related settings.
    """
    source_env = env or os.environ
    llm_config: Dict[str, str] = {}
    for key, default in LLM_DEFAULTS.items():
        env_key = f"VIDEOAPP_{key.upper()}"
        value = source_env.get(env_key)
        if value is None:
            value = config.get(key, default)
        llm_config[key] = value
    return llm_config


def get_llm_setting(
    llm_config: Mapping[str, str],
    key: str
) -> str:
    """
    Retrieve an LLM setting value, falling back to centralized defaults.
    """
    value = llm_config.get(key)
    if value in (None, ""):
        value = LLM_DEFAULTS.get(key, "")
    return str(value)


def get_prompt_template(config: Mapping[str, Any], key: str) -> str:
    """
    Retrieve prompt templates with defaults centralized in this module.
    """
    prompts = {}
    if config:
        prompts = (config.get("prompts") or {}) if isinstance(config.get("prompts"), Mapping) else {}
    value = prompts.get(key)
    if value:
        return str(value)
    return PROMPT_DEFAULTS.get(key, "")


def resolve_cors_origins(
    config: Mapping,
    env: Optional[MutableMapping[str, str]] = None
) -> List[str]:
    """
    Determine allowed CORS origins using env override or fallback config.
    """
    source_env = env or os.environ
    cors_origins_env = source_env.get("VIDEOAPP_CORS_ORIGINS")
    if cors_origins_env:
        return [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    return config.get("cors", {}).get("origins", ["http://localhost:8080", "http://127.0.0.1:8080"])


def is_cors_disabled(env: Optional[MutableMapping[str, str]] = None) -> bool:
    """
    Check if CORS should be disabled entirely via environment variable.
    """
    source_env = env or os.environ
    flag = source_env.get("VIDEOAPP_DISABLE_CORS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}

