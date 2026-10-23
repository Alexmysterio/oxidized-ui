#!/bin/sh
set -eu
rm -f /oxidized-config/pid
while ! curl -fsS -H "X-Oxidized-Source-Token: ${OXIDIZED_SOURCE_TOKEN}" \
  "${UI_INTERNAL_URL}/api/internal/source/nodes" | grep -q '"name"'; do
  sleep 5
done
exec oxidized
