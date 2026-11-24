#!/usr/bin/env bash
# 本地复现 CI：不需要云端 API Key，也不会读取真实 .env 值到测试断言中。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if [[ ! -d agent-service/.venv ]]; then
  python3 -m venv agent-service/.venv
fi
# shellcheck disable=SC1091
source agent-service/.venv/bin/activate
python -m pip install -q -r agent-service/requirements-dev.txt
( cd agent-service && pytest -q )
node --test tests/product-isolation.test.mjs tests/gateway-supervisor.test.mjs
