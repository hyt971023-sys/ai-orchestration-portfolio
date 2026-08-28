"""CLI — 자연어 지시를 받아 실행 계획과 결과를 출력한다.

    python -m demo "형광펜 A 옐로 재고 부족하니까 전 채널에서 막아줘"
    python -m demo "..." --apply          # 실제 반영 (기본은 dry-run)
    python -m demo --rollback <스냅샷경로>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters import FakeMall, FakeMarketplace, FakeReadOnlyChannel
from .catalog import Catalog
from .orchestrator import Orchestrator, RunReport
from .planner import parse

BAR = "─" * 66


def _render(rep: RunReport) -> None:
    mode = "DRY-RUN (아무것도 바꾸지 않음)" if rep.dry_run else "APPLY (실제 반영)"
    print(f"\n{BAR}\n 지시  {rep.intent}\n 모드  {mode}\n{BAR}")

    if rep.changes:
        print("\n■ 변경 대상")
        for c in rep.changes:
            b = "판매" if c.before_sellable else "차단"
            a = "판매" if c.after_sellable else "차단"
            mark = {True: "✅", False: "🔴", None: "  "}[c.verified]
            print(f"  {mark} {c.channel:<12} {c.channel_code:<9} {c.listing_name:<22} {b} → {a}")
    else:
        print("\n■ 변경 대상 없음")

    if rep.component_demand:
        print("\n■ 구성품 환산 (세트는 낱개로 풀어서 계산)")
        for bc, qty in sorted(rep.component_demand.items()):
            print(f"     {bc}  × {qty}")

    if rep.excluded_discontinued:
        print("\n■ 이름이 겹치지만 제외한 단종 SKU — 정본키(바코드)로 구분")
        for e in rep.excluded_discontinued:
            print(f"     · {e}")

    if rep.skipped_readonly:
        print("\n■ 쓰기 미지원 채널 — 수동 처리로 분리")
        for s in rep.skipped_readonly:
            print(f"     · {s}")

    if rep.unmapped:
        print("\n■ 크로스워크 미매칭 — 추측하지 않고 사람에게 넘김")
        for u in rep.unmapped:
            print(f"     · {u}")

    if rep.snapshot_path:
        print(f"\n■ 롤백 스냅샷\n     {rep.snapshot_path}")

    if not rep.dry_run and rep.changes:
        print(f"\n■ 반영 검증 (read-back)  {rep.verified_count}/{len(rep.changes)} 확인")

    if rep.notes:
        print("\n■ 비고")
        for n in rep.notes:
            print(f"     · {n}")
    print(f"{BAR}\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="demo", description="멀티채널 재고 오케스트레이션 데모")
    p.add_argument("instruction", nargs="?", help="자연어 지시")
    p.add_argument("--apply", action="store_true", help="실제 반영 (기본은 dry-run)")
    p.add_argument("--rollback", metavar="SNAPSHOT", help="스냅샷으로 원복")
    args = p.parse_args(argv)

    catalog = Catalog.load()
    channels = [FakeMall(), FakeMarketplace(), FakeReadOnlyChannel()]
    orch = Orchestrator(catalog, channels)

    if args.rollback:
        failures = orch.rollback(Path(args.rollback))
        if failures:
            print(f"🔴 복원 실패 {len(failures)}건")
            for f in failures:
                print(f"   · {f}")
            return 1
        print("✅ 전량 복원 완료 · 실패 0건")
        return 0

    if not args.instruction:
        p.error("지시문을 입력하거나 --rollback 을 쓰세요")

    print("\n■ 채널 쓰기 가능 여부 (설계 전 실측 대상)")
    for ch in channels:
        print(f"     {ch.name:<12} {ch.capability.value}")
    for ch in channels:
        m, t = catalog.parse_rate(ch.name)
        pct = f"{m / t * 100:.0f}%" if t else "—"
        print(f"     크로스워크 {ch.name:<12} {m}/{t}  ({pct})")

    plan = parse(args.instruction, catalog)
    rep = orch.run(plan, dry_run=not args.apply)
    _render(rep)
    return 1 if rep.failed_verification else 0


if __name__ == "__main__":
    sys.exit(main())
