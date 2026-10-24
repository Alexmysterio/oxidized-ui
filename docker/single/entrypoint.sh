#!/bin/sh
set -eu
mkdir -p /data /oxidized-config /var/lib/oxidized /var/log/supervisor /home/oxidized/.config
mkdir -p /oxidized-config/.ssh
chown -R 30000:30000 /data /oxidized-config /var/lib/oxidized /var/log/supervisor
chmod 700 /oxidized-config/.ssh
chmod -R go-rwx /data /oxidized-config
chmod 755 /var/log/supervisor
rm -f /oxidized-config/pid
rm -rf /home/oxidized/.config/oxidized /home/oxidized/.ssh
ln -s /oxidized-config /home/oxidized/.config/oxidized
ln -s /oxidized-config/.ssh /home/oxidized/.ssh
chown -h 30000:30000 /home/oxidized/.config/oxidized /home/oxidized/.ssh
chmod 755 /home/oxidized /home/oxidized/.config

# Persist generated secrets so the installation can start without a .env file.
SECRETS_FILE=/data/.runtime-secrets
if [ -f "$SECRETS_FILE" ]; then
    . "$SECRETS_FILE"
fi
if [ -z "${SECRET_KEY:-}" ]; then
    SECRET_KEY=$(/opt/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
fi
if [ -z "${FERNET_KEY:-}" ]; then
    if [ -f /data/oxidized-ui.sqlite3 ]; then
        echo "FERNET_KEY is required for an existing database. Create .env from .env.example or restore the original secrets." >&2
        exit 1
    fi
    FERNET_KEY=$(/opt/venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
fi
if [ -z "${OXIDIZED_SOURCE_TOKEN:-}" ]; then
    OXIDIZED_SOURCE_TOKEN=$(/opt/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
fi
umask 077
printf 'SECRET_KEY=%s\nFERNET_KEY=%s\nOXIDIZED_SOURCE_TOKEN=%s\n' "$SECRET_KEY" "$FERNET_KEY" "$OXIDIZED_SOURCE_TOKEN" > "$SECRETS_FILE"
chown 30000:30000 "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"
export SECRET_KEY FERNET_KEY OXIDIZED_SOURCE_TOKEN

exec supervisord -c /etc/supervisor/supervisord.conf
