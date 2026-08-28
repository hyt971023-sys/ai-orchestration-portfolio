#!/usr/bin/env bash
# 공개 전 검사 게이트
#
# 🔴 설계 원칙 다섯 가지
#   1. 이 파일은 검사 대상 문자열을 하나도 담지 않는다.
#      금지어를 스크립트에 적으면 그 목록 자체가 정답표가 된다.
#   2. 자기 자신을 검사에서 제외하지 않는다. 검사 도구도 검사 대상이다.
#   3. 검사할 목록이 없으면 통과가 아니라 실패다.
#      "검사할 게 없어서 통과"는 무증상 미수행이다.
#   4. 실제 규칙 파일은 저장소 폴더 밖에 둔다.
#      gitignore 는 커밋만 막는다. 폴더를 zip·백업·클라우드 동기화하면 그대로 따라간다.
#      그래서 "추적되지 않는 파일"로는 부족하고, "저장소 안에 없는 파일"이어야 한다.
#      🔴 이 판정은 **파일명이 아니라 경로와 내용**으로 한다. 특정 파일명을 검사하면
#         다른 이름으로 복사하는 것만으로 우회된다.
#   5. 작업 트리만 본 검사는 통과로 처리하지 않는다.
#      작업 트리에서 지운 문자열은 커밋 객체에 그대로 남는다.
#      그래서 git 히스토리 객체까지 같은 규칙으로 스캔한다.
#
# ── 사용법 ─────────────────────────────────────────────
#
#   규칙 파일 준비 (한 번만) — 저장소 폴더 밖에 둔다:
#     mkdir -p ~/.config/redaction
#     cp .redaction-rules.example ~/.config/redaction/portfolio-rules
#     chmod 600 ~/.config/redaction/portfolio-rules
#     # 실제 값을 채운다 — 한 행에 식별자 하나, 파이프로 묶지 않는다
#
#   실행 (경로 주입은 필수. 기본값을 두면 저장소 안 파일을 쓰게 된다):
#     REDACTION_RULES_FILE=~/.config/redaction/portfolio-rules ./scripts/redaction-gate.sh
#
#   pre-commit 훅:
#     printf '%s\n' '#!/usr/bin/env bash' \
#       'REDACTION_RULES_FILE="$HOME/.config/redaction/portfolio-rules" exec ./scripts/redaction-gate.sh' \
#       > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#
#   CI:  저장소 밖에 만든 카나리 규칙으로 "탐지력이 살아 있는지"를 양성 대조로 검증한다.
#        실제 식별자 검사는 로컬 훅이 담당한다.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd -P)"
FAIL=0

TMPD="${TMPDIR:-/tmp}"
HIST="$(mktemp "${TMPD%/}/rgate-hist.XXXXXX")" || exit 1
BLOB="$(mktemp "${TMPD%/}/rgate-blob.XXXXXX")" || exit 1
trap 'rm -f "$HIST" "$BLOB"' EXIT

usage() {
  echo "     mkdir -p ~/.config/redaction"
  echo "     cp .redaction-rules.example ~/.config/redaction/portfolio-rules"
  echo "     REDACTION_RULES_FILE=~/.config/redaction/portfolio-rules ./scripts/redaction-gate.sh"
  echo "     실제 값을 담은 파일은 저장소 폴더 안에 두지 않습니다."
}

# ── 내용으로 판정하는 두 함수 ─────────────────────────
# 규칙 파일 형태인가: 「분류명<TAB>패턴」 두 칸짜리 줄이 2줄 이상인 텍스트 파일.
# 파일명·확장자·추적 여부를 보지 않는다.
is_rules_shaped() {
  [ -f "$1" ] || return 1
  grep -Iq . "$1" 2>/dev/null || return 1          # 바이너리·빈 파일 제외
  local n
  n=$(awk -F'\t' 'NF==2 && $1 !~ /^[[:space:]]*#/ && $1 != "" && $2 != "" {c++} END {print c+0}' "$1")
  [ "${n:-0}" -ge 2 ]
}

# 패턴 칸이 플레이스홀더 전용인가 (= 저장소 안에 있어도 되는 예시인가).
# 문자 클래스와 PLACEHOLDER_ 토큰을 지운 뒤 글자가 하나도 남지 않아야 한다.
# 남으면 리터럴 식별자를 담은 실제 규칙 파일로 본다.
patterns_are_placeholder_only() {
  local rest
  rest=$(awk -F'\t' 'NF==2 && $1 !~ /^[[:space:]]*#/ && $1 != "" && $2 != "" {print $2}' "$1" \
         | sed -e 's/\[[^]]*\]//g' -e 's/PLACEHOLDER[A-Z0-9_]*//g')
  ! printf '%s\n' "$rest" | LC_ALL=C grep -qE '[A-Za-z]|[^ -~]'
}

echo "── 공개 전 검사 ────────────────────────────────"

# ── 1. 규칙 파일 경로: 저장소 안이면 즉시 실패 (파일명·내용 무관) ──
RULES="${REDACTION_RULES_FILE:-}"
if [ -z "$RULES" ]; then
  echo "🔴 REDACTION_RULES_FILE 미지정 — 규칙 파일 경로를 주입해야 합니다"
  usage
  echo "────────────────────────────────────────────────"
  echo "❌ 검사 불가 — 통과로 처리하지 않습니다."
  exit 1
fi

rules_dir="$(cd "$(dirname "$RULES")" 2>/dev/null && pwd -P)"
RULES_ABS="${rules_dir:-}/$(basename "$RULES")"
if [ -z "${rules_dir:-}" ]; then
  echo "🔴 규칙 파일 경로를 해석할 수 없습니다: $RULES"
  usage
  echo "────────────────────────────────────────────────"
  echo "❌ 검사 불가 — 통과로 처리하지 않습니다."
  exit 1
fi
case "$RULES_ABS" in
  "$REPO"|"$REPO"/*)
    echo "🔴 [규칙 파일 위치] 지정된 규칙 파일이 저장소 폴더 안에 있습니다"
    echo "     $RULES_ABS"
    echo "     파일명은 보지 않습니다 — 어떤 이름이든 저장소 안이면 실패입니다."
    echo "     mv \"$RULES\" ~/.config/redaction/portfolio-rules"
    echo "────────────────────────────────────────────────"
    echo "❌ 검사 불가 — 통과로 처리하지 않습니다."
    exit 1 ;;
esac
echo "✅ 규칙 파일 저장소 밖"

if [ ! -f "$RULES" ]; then
  echo "🔴 규칙 파일 없음: $RULES"
  usage
  echo "────────────────────────────────────────────────"
  echo "❌ 검사 불가 — 통과로 처리하지 않습니다."
  exit 1
fi

# ── 2. 저장소 안 '식별자 목록 형태' 파일 색출 (파일명·추적 여부 무관) ──
# 실제 규칙 파일을 다른 이름으로 복사해 두는 것이 가장 흔한 우회다.
# 그래서 이름을 보지 않고 내용 형태로 판정한다.
FILES="$(find . -path ./.git -prune -o \( -type f -o -type l \) -print 2>/dev/null | sed 's|^\./||')"
SHAPED_LITERAL=""
SHAPED_EXAMPLE=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  is_rules_shaped "$f" || continue
  if patterns_are_placeholder_only "$f"; then
    SHAPED_EXAMPLE="${SHAPED_EXAMPLE}${f}
"
  else
    SHAPED_LITERAL="${SHAPED_LITERAL}${f}
"
  fi
done <<< "$FILES"

if [ -n "$SHAPED_LITERAL" ]; then
  echo "🔴 [식별자 목록] 저장소 안에 규칙 파일 형태의 파일이 있습니다 (파일명과 무관하게 내용으로 판정)"
  printf '%s' "$SHAPED_LITERAL" | sed 's/^/     /'
  echo "     플레이스홀더가 아닌 리터럴이 패턴 칸에 있습니다. 저장소 밖으로 옮기세요."
  FAIL=1
else
  echo "✅ 저장소 안 식별자 목록 없음"
fi

# 스캔 대상: 저장소 폴더 전체.
# 제외는 단 하나 — 내용상 플레이스홀더 전용으로 판정된 예시 파일.
# (이름으로 제외하지 않는다. 내용이 예시임을 증명한 파일만 빠진다.)
SCAN="$FILES"
if [ -n "$SHAPED_EXAMPLE" ]; then
  SCAN="$(printf '%s\n' "$FILES" | grep -vxF -f <(printf '%s' "$SHAPED_EXAMPLE"))"
fi

# ── 3. 히스토리 객체 수집 (작업 트리에서 지워도 커밋에는 남는다) ──
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "🔴 [히스토리] git 저장소가 아니어서 커밋 객체를 검사할 수 없습니다"
  FAIL=1
elif [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
  echo "🔴 [히스토리] 얕은 클론입니다 — 히스토리 전체를 볼 수 없어 통과로 처리하지 않습니다"
  echo "     git fetch --unshallow   ·   CI: actions/checkout 에 fetch-depth: 0"
  FAIL=1
else
  n_obj=0; n_blob=0
  while read -r h p; do
    [ -n "${h:-}" ] || continue
    n_obj=$((n_obj+1))
    [ -n "${p:-}" ] || continue
    [ "$(git cat-file -t "$h" 2>/dev/null)" = "blob" ] || continue
    git cat-file blob "$h" > "$BLOB" 2>/dev/null || continue
    grep -Iq . "$BLOB" 2>/dev/null || continue
    n_blob=$((n_blob+1))
    awk -v pre="$h $p" '{print pre "\t" $0}' "$BLOB" >> "$HIST"
  done < <(git rev-list --all --objects 2>/dev/null)
  echo "✅ 히스토리 객체 ${n_obj}건 · 텍스트 블롭 ${n_blob}건 수집"
fi

# ── 4. 규칙별 스캔 — 작업 트리 + 히스토리 ──
# 규칙 파일 형식:  분류명<TAB>정규식     (# 주석, 빈 줄 무시)
COUNT=0
while IFS=$'\t' read -r name pat; do
  case "$name" in ''|'#'*) continue ;; esac
  [ -z "${pat:-}" ] && continue
  COUNT=$((COUNT+1))
  wt=$(printf '%s\n' "$SCAN" | tr '\n' '\0' | xargs -0 grep -nIEi -- "$pat" 2>/dev/null) || true
  hs=""
  if [ -s "$HIST" ]; then hs=$(grep -IEi -- "$pat" "$HIST" 2>/dev/null) || true; fi
  if [ -n "$wt$hs" ]; then
    echo "🔴 [$name] 적중 — 아래 위치를 확인하세요"
    # 적중한 값 자체는 출력하지 않는다. 로그에 남으면 그것도 유출이다.
    [ -n "$wt" ] && echo "$wt" | cut -d: -f1,2 | sort -u | head -10 | sed 's/^/     작업트리  /'
    [ -n "$hs" ] && echo "$hs" | cut -f1     | sort -u | head -10 | sed 's/^/     히스토리  /'
    FAIL=1
  else
    echo "✅ $name"
  fi
done < "$RULES"

if [ "$COUNT" -eq 0 ]; then
  echo "🔴 규칙 0건 — 파일이 비어 있습니다"; FAIL=1
fi

# ── 5. 데이터 파일 유입 — 작업 트리와 히스토리 양쪽 ──
DATA=$(printf '%s\n' "$SCAN" | grep -E '\.(csv|xlsx|xls)$' | grep -v '^demo/fixtures/') || true
DATA_H=$(git rev-list --all --objects 2>/dev/null | awk 'NF>=2 {print $2}' \
         | grep -E '\.(csv|xlsx|xls)$' | grep -v '^demo/fixtures/' | sort -u) || true
if [ -n "$DATA$DATA_H" ]; then
  echo "🔴 [데이터 파일]"
  [ -n "$DATA" ]   && echo "$DATA"   | sed 's/^/     작업트리  /'
  [ -n "$DATA_H" ] && echo "$DATA_H" | sed 's/^/     히스토리  /'
  FAIL=1
else
  echo "✅ 데이터 파일"
fi

echo "────────────────────────────────────────────────"
if [ "$FAIL" -eq 1 ]; then
  echo "❌ 위반 있음 — PUBLISHING.md 기준으로 치환한 뒤 다시 실행하세요."
  exit 1
fi
echo "✅ 규칙 ${COUNT}건 + 구조 검사 전항목 통과 (작업 트리 · 히스토리 객체)"
