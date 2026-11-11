#!/usr/bin/env bash
# 헤드리스 UI 확인 하나를 실행한다.
# 사용: tools/ui-check/run.sh <확인 이름> [추가 인자...]   예) WIDTH=375 tools/ui-check/run.sh mobile-check
# 매번 임시 DB·업로드 폴더를 새로 만들고 확인용 서버를 따로 띄우므로 dev.db·uploads/는 건드리지 않는다.
set -u
name="$1"; shift

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${UI_CHECK_OUT:-$HERE/out}"
mkdir -p "$OUT"
# Git Bash에서는 /c/... 대신 C:/... 형태로 바꿔야 파이썬·노드가 같은 경로로 읽는다.
OUT="$(cd "$OUT" && (pwd -W 2>/dev/null || pwd))"

if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/venv/Scripts/python.exe" ]; then PYTHON="$ROOT/venv/Scripts/python.exe"; else PYTHON="$ROOT/venv/bin/python"; fi
fi
export PYTHON
export UI_CHECK_PORT="${UI_CHECK_PORT:-8001}"
export UI_CHECK_BASE="${UI_CHECK_BASE:-http://127.0.0.1:$UI_CHECK_PORT}"
# 확인용 서버 전용 값. .env의 값보다 우선하도록 환경 변수로 넘긴다. 키는 실행할 때마다 새로 만든다.
export DATABASE_URL="sqlite:///$OUT/ui-check.db"
export UPLOAD_DIR="$OUT/uploads-check"
export SECRET_KEY="${UI_CHECK_SECRET_KEY:-$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')}"
export EMAIL_HASH_KEY="$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"

rm -rf "$OUT/ui-check.db" "$OUT/chrome-profile" "$OUT/uploads-check"
cd "$ROOT"
"$PYTHON" -m uvicorn app.main:app --port "$UI_CHECK_PORT" > "$OUT/server-$name.log" 2>&1 &
pid=$!
trap 'kill $pid 2>/dev/null; wait $pid 2>/dev/null' EXIT
for _ in $(seq 1 60); do curl -s -o /dev/null "$UI_CHECK_BASE/static/index.html" && break; sleep 0.5; done

"$PYTHON" "$HERE/seed.py" "$OUT/ui-check.db" "$OUT/seed.json" > /dev/null
node "$HERE/$name.mjs" "$OUT" "$@"

# 결과 파일(<이름>.txt)이 있으면 화면 폭별로 보관하고 요약을 보여 준다.
if [ -f "$OUT/$name.txt" ]; then
  mv "$OUT/$name.txt" "$OUT/$name-${WIDTH:-375}.txt"
  result="$OUT/$name-${WIDTH:-375}.txt"
  echo "== $name @${WIDTH:-375}: $(grep -c '^PASS' "$result") PASS, $(grep -c '^FAIL\|^ERROR' "$result") FAIL"
  grep -A3 '^FAIL\|^ERROR' "$result"
fi
