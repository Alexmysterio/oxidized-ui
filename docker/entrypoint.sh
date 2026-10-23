#!/bin/sh
set -eu

for directory in "${DATA_DIR:-/data}" "${OXIDIZED_CONFIG_DIR:-/oxidized-config}"; do
    if [ ! -d "$directory" ]; then
        echo "ERROR: required directory does not exist: $directory" >&2
        exit 1
    fi
    if [ ! -w "$directory" ]; then
        echo "ERROR: $directory is not writable by UID $(id -u)." >&2
        echo "Initialize the named volume with UID/GID 30000, or chown bind mounts:" >&2
        echo "  sudo chown -R 30000:30000 /path/to/volume" >&2
        exit 1
    fi
done

exec "$@"
