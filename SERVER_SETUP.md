AI Video App — Server Setup (codai.ru)

This file documents everything installed and configured on the server 81.200.156.13 for the AI Video App deployment.

Summary
- Host: 81.200.156.13 (Ubuntu 24.04)
- Domain: codai.ru
- App path: /opt/ai_videoapp
- Venv: /opt/ai_videoapp/venv
- Service: ai_videoapp.service (systemd)
- Web: Nginx reverse proxy -> Gunicorn :8000
- TLS: Let’s Encrypt (certbot)

Installed packages
- System: python3, python3-venv, python3-pip, ffmpeg, nginx, certbot, python3-certbot-nginx, build-essential
- Python (venv): Flask, openai, openai-whisper (local mode), torch (CPU), numba, ffmpeg-python, gunicorn

App configuration
- config.json хранит только несекретные параметры (UI, сервер, подсказки).
- Значения `VIDEOAPP_*` задаются через `.env`:
  - `VIDEOAPP_OPENAI_API_KEY`
  - `VIDEOAPP_OPENAI_API_BASE`, `VIDEOAPP_OPENAI_MODEL`
  - `VIDEOAPP_TRANSCRIPTION_MODE`, `VIDEOAPP_OPENAI_STT_MODEL`
  - `VIDEOAPP_WHISPER_MODEL`, `VIDEOAPP_WHISPER_LANGUAGE`
- Переменные окружения перекрывают значения из config.json и дефолтов приложения.

Networking / firewall
- UFW: allow OpenSSH, Nginx Full (80/443); deny others by default

Notes
- ffmpeg is used for audio extraction to 16kHz mono MP3 to keep STT payloads small.
- Local Whisper requires more CPU/RAM; remote STT is recommended in production.

