"""업무 성숙도 측정 CLI.

    python -m maturity sample > tasks.csv     예시 입력 파일 생성
    python -m maturity report tasks.csv       터미널 리포트
    python -m maturity report tasks.csv --format md
    python -m maturity report tasks.csv --format json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .render import as_json, as_markdown, as_text
from .report import Report, load

# 도구 동작 확인용 가상 데이터. 특정 조직의 업무 목록이 아니고, 실제 운영 상태와 무관하다.
# 열 규격과 두 축(성숙도 × 실행 위치)의 조합만 보여주기 위한 것이다.
SAMPLE = """업무명,성숙도,실행위치,담당,비고
정기 지표 리포트 발송,무인 자동,공용 인프라,,일 1회 정기 발송
야간 데이터 적재 배치,무인 자동,개인 환경,A,개인 환경 의존 — 이관 대상
이상 데이터 자동 격리,무인 자동,공용 인프라,,
큐 적체 임계 알림,무인 자동,개인 환경,A,
외부 연동 응답 감시,무인 자동,공용 인프라,,분 단위 주기 폴링
설정 일괄 적용 도구,도구화,사람이 직접 실행,A,명령 1회
설정 원복 도구,도구화,사람이 직접 실행,A,
입력값 정합 검사 스크립트,도구화,사람이 직접 실행,A,
전수 조회 도구,도구화,사람이 직접 실행,A,읽기 전용
식별키 매핑 조회,도구화,사람이 직접 실행,B,
대상 상태 일괄 변경,도구화,사람이 직접 실행,A,
알림 일괄 발송,도구화,사람이 직접 실행,B,
제출 파일 생성,도구화,사람이 직접 실행,B,
신규 항목 등록 절차,절차화,사람이 직접 실행,B,체크리스트 있음
반려 건 재처리 절차,절차화,사람이 직접 실행,C,
월별 집계 대사,담당자 전속,,A,문서 없음 — 이관 필요
예외 규정 판정,담당자 전속,,A,암묵지
변경 요청 사전 검토,담당자 전속,,A,
장기 보관 데이터 정리,담당자 전속,,A,미확인
운영 지표 정의 조정,담당자 전속,개인 환경,A,
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="maturity",
        description="업무를 4단계로 분류하고 자동화 성숙도·실행 위치 집중도를 산출합니다.",
        epilog="방법론: docs/maturity-framework.md")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sample", help="예시 입력 CSV 를 표준출력으로 내보냅니다")
    sp.set_defaults(func=lambda a: (sys.stdout.write(SAMPLE), 0)[1])

    rp = sub.add_parser("report", help="CSV 를 읽어 리포트를 출력합니다")
    rp.add_argument("csv", type=Path, help="입력 CSV (필수 열: 업무명, 성숙도)")
    rp.add_argument("--format", "-f", choices=["text", "md", "json"], default="text")
    rp.add_argument("--strict", action="store_true",
                    help="규격에 맞지 않는 행이 하나라도 있으면 실패로 종료")

    def run(a) -> int:
        if not a.csv.exists():
            print(f"파일이 없습니다: {a.csv}", file=sys.stderr)
            return 2
        tasks, skipped = load(a.csv)
        r = Report(tasks, skipped)
        out = {"text": as_text, "md": as_markdown, "json": as_json}[a.format](r)
        print(out)
        # 🔴 조용한 실패 방지 — 집계 결과가 0건이면 성공으로 끝내지 않는다
        if r.total == 0:
            print("집계된 업무가 0건입니다. 입력을 확인하세요.", file=sys.stderr)
            return 1
        if a.strict and skipped:
            print(f"--strict: 규격 불일치 {len(skipped)}건", file=sys.stderr)
            return 1
        return 0

    rp.set_defaults(func=run)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
