#!/bin/sh
set -eu
mkdir -p /data /oxidized-config /var/lib/oxidized /var/log/supervisor /home/oxidized/.config
mkdir -p /oxidized-config/.ssh
chown -R 30000:30000 /data /oxidized-config /var/lib/oxidized /var/log/supervisor
chmod 700 /oxidized-config/.ssh
rm -f /oxidized-config/pid
rm -rf /home/oxidized/.config/oxidized /home/oxidized/.ssh
ln -s /oxidized-config /home/oxidized/.config/oxidized
ln -s /oxidized-config/.ssh /home/oxidized/.ssh
chown -h 30000:30000 /home/oxidized/.config/oxidized /home/oxidized/.ssh
chmod 755 /home/oxidized /home/oxidized/.config
exec supervisord -c /etc/supervisor/supervisord.conf
