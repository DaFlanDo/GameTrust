#!/bin/sh
set -e

flask db upgrade
if [ "${SEED_DEMO:-0}" = "1" ]; then
  flask seed
fi

exec gunicorn --bind 0.0.0.0:5000 --workers 2 --access-logfile - "app:create_app()"
