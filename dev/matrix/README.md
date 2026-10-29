# Local Matrix test setup

Synapse (`klinikum.example`) + Element Web + optional Mailpit, only for developing the bot.

    dev/matrix/setup.sh          # start, create users and the unencrypted room 'PGK requests'
    # copy the `export ...` lines it prints, then from the repo root:
    .venv/bin/uvicorn app.main:app      # ONE worker: the bot runs inside this process

- Element: http://localhost:8088, log in as `lena.hofer` / `hofer-dev-password`
- The bot is `@pgk-bot:klinikum.example`. It only obeys `MATRIX_ALLOWED_USERS` (default: Dr. Hofer).
- Rooms are unencrypted on purpose (the brief does not require end-to-end encryption).
- Mailpit: if another Mailpit already uses ports 1025/8025, keep it. Otherwise
  `docker compose --profile mail up -d`.
- Stop: `docker compose down` in this folder. Reset everything: also delete `synapse-data/`.
