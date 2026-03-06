#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=/home/ubuntu/langchain-openwork
SERVER_DIR="$PROJECT_DIR/server"

printf "==> Install system deps\n"
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-dev \
  build-essential pkg-config git curl \
  autoconf bison flex gcc g++ libprotobuf-dev libnl-route-3-dev libtool protobuf-compiler \
  mysql-server

printf "==> Build nsjail\n"
if ! command -v nsjail >/dev/null 2>&1; then
  git clone https://github.com/google/nsjail.git /tmp/nsjail
  (cd /tmp/nsjail && make)
  sudo ln -sf /tmp/nsjail/nsjail /usr/local/bin/nsjail
fi
nsjail --version || true

printf "==> Install uv\n"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  sudo cp ~/.local/bin/uv /usr/local/bin/uv
fi
uv --version || true

printf "==> Setup MySQL\n"
sudo service mysql start || true
sudo mysql -e "CREATE DATABASE IF NOT EXISTS openwork;"
sudo mysql -e "CREATE USER IF NOT EXISTS 'openwork'@'localhost' IDENTIFIED BY 'openwork123';"
sudo mysql -e "GRANT ALL PRIVILEGES ON openwork.* TO 'openwork'@'localhost'; FLUSH PRIVILEGES;"

printf "==> Update config.yaml\n"
cd "$SERVER_DIR"
python3 - <<'PY'
import yaml
from pathlib import Path
cfg_path = Path("config.yaml")
data = yaml.safe_load(cfg_path.read_text())
data["database"]["url"] = "mysql+pymysql://openwork:openwork123@127.0.0.1:3306/openwork"
cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
PY

printf "==> Create venv and install deps\n"
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install uv
uv sync

printf "==> Run migrations\n"
alembic upgrade head

printf "==> Start server\n"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
