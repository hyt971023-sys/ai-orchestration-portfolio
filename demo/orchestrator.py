"""오케스트레이터 — 안전장치가 본체다.

실행 순서 (안전 설계 4원칙을 코드로 옮긴 것):
  1. dry-run 이 기본값             — 무엇이 바뀔지 먼저 보여준다
  2. 쓰기 전 before 스냅샷         — 없으면 실행하지 않는다
  3. 판매 플래그로 차단            — 노출 플래그만으로는 안 막힌다
  4. 쓰기 후 read-back 재조회      — 200 OK 를 반영으로 믿지 않는다
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .adapters.base import ChannelAdapter
from .catalog import Catalog
from .planner import Plan


@dataclass
class Change:
    channel: str
    channel_code: str
    listing_name: str
    before_sellable: bool
    after_sellable: bool
    verified: bool | None = None      # read-back 결과. None = 미검증


@dataclass
class RunReport:
    dry_run: bool
    intent: str
    changes: list[Change] = field(default_factory=list)
    skipped_readonly: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    component_demand: dict[str, int] = field(default_factory=dict)
    excluded_discontinued: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    snapshot_path: str | None = None

    @property
    def verified_count(self) -> int:
        return sum(1 for c in self.changes if c.verified)

    @property
    def failed_verification(self) -> list[Change]:
        return [c for c in self.changes if c.verified is False]


class Orchestrator:
    def __init__(self, catalog: Catalog, channels: list[ChannelAdapter],
                 snapshot_dir: Path | None = None):
        self.catalog = catalog
        self.channels = channels
        self.snapshot_dir = snapshot_dir or (Path(__file__).parent / "_snapshots")

    # ── 실행 ────────────────────────────────────────────────
    def run(self, plan: Plan, *, dry_run: bool = True) -> RunReport:
        """dry_run 기본값이 True 인 것이 이 클래스의 핵심 설계다."""
        report = RunReport(dry_run=dry_run, intent=plan.intent, notes=list(plan.notes))

        # 이름이 겹쳐 잡힐 뻔한 단종 SKU 를 채널 코드까지 붙여 드러낸다.
        # 실행 여부와 무관하게 보고한다 — 제외는 결과의 일부이지 생략이 아니다.
        for bc in plan.excluded_discontinued:
            sku = self.catalog.sku(bc)
            codes = [f"{ch.name}:{c}"
                     for ch in self.channels
                     for c in self.catalog.channel_codes(ch.name, bc)]
            where = " · ".join(codes) if codes else "채널 리스팅 없음"
            report.excluded_discontinued.append(
                f"{bc}  {sku.name} {sku.variant}  ←  {where}")

        if plan.is_empty:
            report.notes.append("실행할 액션 없음 — 아무것도 바꾸지 않았다")
            report.unmapped = plan.unresolved
            return report

        # 1) 세트 → 구성품 환산 (묶음에 물리 재고를 그대로 걸면 배수로 팔린다)
        for a in plan.actions:
            for bc, qty in self.catalog.to_component_demand(a.barcode, 1).items():
                report.component_demand[bc] = report.component_demand.get(bc, 0) + qty

        # 2) 대상 수집 — 쓰기 가능 채널과 불가 채널을 먼저 가른다
        targets: list[tuple[ChannelAdapter, str, Change]] = []
        for action in plan.actions:
            for ch in self.channels:
                codes = self.catalog.channel_codes(ch.name, action.barcode)
                if not codes:
                    # 해당 채널이 이 SKU 를 취급하지 않는 정상 상황.
                    # 진짜 '미매칭'(채널에는 코드가 있는데 정본과 못 잇는 것)과 구분한다.
                    continue
                for code in codes:
                    listing = ch.fetch(code)
                    if listing is None:
                        report.unmapped.append(f"{ch.name}:{code}")
                        continue
                    if not ch.supports_write():
                        report.skipped_readonly.append(
                            f"{ch.name}:{code} ({listing.name}) — 수동 처리 대상")
                        continue
                    if listing.sellable == action.sellable:
                        continue           # 이미 목표 상태 — 불필요한 쓰기 금지
                    targets.append((ch, code, Change(
                        channel=ch.name, channel_code=code, listing_name=listing.name,
                        before_sellable=listing.sellable, after_sellable=action.sellable)))

        report.changes = [t[2] for t in targets]

        if dry_run:
            report.notes.append("DRY-RUN — 아무것도 변경하지 않았다. 실행하려면 --apply")
            return report

        if not targets:
            report.notes.append("변경 대상 없음")
            return report

        # 3) 🔴 쓰기 전 스냅샷. 저장에 실패하면 실행하지 않는다.
        try:
            report.snapshot_path = str(self._snapshot(targets))
        except OSError as e:
            report.notes.append(f"🔴 스냅샷 저장 실패 — 되돌릴 수 없으므로 실행 중단 ({e})")
            report.changes = []
            return report

        # 4) 쓰기 + read-back 검증
        for ch, code, change in targets:
            res = ch.set_sellable(code, change.after_sellable)
            if not res.ok:
                change.verified = False
                report.notes.append(f"쓰기 실패 {ch.name}:{code} — {res.detail}")
                continue
            after = ch.fetch(code)                       # 독립 재조회
            change.verified = bool(after and after.sellable == change.after_sellable)

        if report.failed_verification:
            report.notes.append(
                f"🔴 반영 검증 실패 {len(report.failed_verification)}건 — 롤백 검토 필요")
        return report

    # ── 롤백 ────────────────────────────────────────────────
    def rollback(self, snapshot_path: Path) -> list[str]:
        """스냅샷 1개로 전량 원복. 복원 실패는 요약해서 반환한다."""
        rows = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))["changes"]
        by_name = {c.name: c for c in self.channels}
        failures: list[str] = []
        for r in rows:
            ch = by_name.get(r["channel"])
            if ch is None or not ch.supports_write():
                failures.append(f"{r['channel']}:{r['channel_code']} — 복원 불가")
                continue
            res = ch.set_sellable(r["channel_code"], r["before_sellable"])
            after = ch.fetch(r["channel_code"])
            if not res.ok or not after or after.sellable != r["before_sellable"]:
                failures.append(f"{r['channel']}:{r['channel_code']} — 복원 검증 실패")
        return failures

    # ── 내부 ────────────────────────────────────────────────
    def _snapshot(self, targets) -> Path:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.snapshot_dir / f"rollback-{stamp}.json"
        path.write_text(json.dumps(
            {"created_at": stamp, "changes": [asdict(c) for _, _, c in targets]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return path
