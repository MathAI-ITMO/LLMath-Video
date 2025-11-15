AI Video App — Operations & Access

Environment
- Server: 81.200.156.13 (Ubuntu 24.04)
- Domain: codai.ru

Access
- SSH: ssh root@81.200.156.13
- Password: x8F16FvGuxx*.4

Paths
- App root: /opt/ai_videoapp
- Venv: /opt/ai_videoapp/venv
- Data dirs (created at runtime): /opt/ai_videoapp/data/(video|audio|subtitles|frames|summaries|logs|suggestions)

Service
- Systemd unit: ai_videoapp.service
- Commands:
  - systemctl status ai_videoapp
  - systemctl restart ai_videoapp
  - journalctl -u ai_videoapp -f

Web
- Local app socket: 127.0.0.1:8000 (Gunicorn)
- Public: https://codai.ru (Nginx reverse proxy with Let’s Encrypt)

Deploy update (manual quick steps)
1) SSH to server, pull/upload new code to /opt/ai_videoapp
2) source /opt/ai_videoapp/venv/bin/activate && pip install -r requirements.txt
3) systemctl restart ai_videoapp

Config toggles
- "openai_stt_model": "gpt-4o-transcribe" or "whisper-1" (все транскрипции выполняются удалённо)

Backup
- App code: /opt/ai_videoapp
- Data: /opt/ai_videoapp/data

Security
- Firewall allows 22/80/443 only. Mail ports blocked.

