"""안전장치가 실제로 동작하는지 검증한다.

이 테스트들은 기능이 아니라 **가드**를 검증한다.
자동화가 잘 도는지가 아니라, 잘못 돌 때 멈추는지를 본다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo.adapters import FakeMall, FakeMarketplace, FakeReadOnlyChannel
from demo.catalog import Catalog
from demo.orchestrator import Orchestrator
from demo.planner import parse


@pytest.fixture
def setup(tmp_path):
    catalog = Catalog.load()
    channels = [FakeMall(), FakeMarketplace(), FakeReadOnlyChannel()]
    return catalog, channels, Orchestrator(catalog, channels, snapshot_dir=tmp_path)


# ── 원칙 1: 되돌릴 수 없으면 실행하지 않는다 ──────────────
def test_dry_run_is_default(setup):
    catalog, channels, orch = setup
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog))          # dry_run 미지정
    assert rep.dry_run is True
    assert all(ch.write_count == 0 for ch in channels), "dry-run 인데 쓰기가 발생했다"


def test_snapshot_written_before_apply(setup, tmp_path):
    catalog, _, orch = setup
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert rep.snapshot_path, "스냅샷 없이 실행됐다"
    saved = json.loads(Path(rep.snapshot_path).read_text(encoding="utf-8"))
    assert saved["changes"], "스냅샷이 비어 있다"
    assert all("before_sellable" in c for c in saved["changes"])


def test_abort_when_snapshot_cannot_be_written(setup, tmp_path):
    catalog, channels, _ = setup
    blocked = tmp_path / "blocked"
    blocked.write_text("파일이라 디렉토리를 만들 수 없다", encoding="utf-8")
    orch = Orchestrator(catalog, channels, snapshot_dir=blocked / "sub")
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert rep.changes == [], "스냅샷 실패인데 변경이 진행됐다"
    assert any("실행 중단" in n for n in rep.notes)
    assert all(ch.write_count == 0 for ch in channels)


def test_rollback_restores_previous_state(setup):
    catalog, channels, orch = setup
    mall = channels[0]
    before = mall.fetch("M-1001").sellable
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert mall.fetch("M-1001").sellable != before
    failures = orch.rollback(Path(rep.snapshot_path))
    assert failures == []
    assert mall.fetch("M-1001").sellable == before


# ── 원칙 3: 200 OK 를 반영으로 믿지 않는다 ────────────────
def test_readback_verifies_every_change(setup):
    catalog, _, orch = setup
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert rep.changes
    assert rep.verified_count == len(rep.changes)
    assert all(c.verified is True for c in rep.changes)


# ── 식별 정합 ────────────────────────────────────────────
def test_discontinued_sku_never_targeted(setup):
    """구형 옵션을 현행으로 오인해 차단하는 실패 유형을 막는다."""
    catalog, _, orch = setup
    plan = parse("형광펜 A 옐로 막아줘", catalog)
    for a in plan.actions:
        assert not catalog.sku(a.barcode).discontinued


def test_name_match_would_have_hit_the_discontinued_lookalike(setup):
    """이름만 보면 구형 옵션이 현행과 구분되지 않는다 — 그래서 정본키가 필요하다."""
    catalog, _, _ = setup
    naive = {s.barcode for s in catalog.search("옐로", include_discontinued=True)}
    live = {s.barcode for s in catalog.search("옐로")}
    assert "0000000000041" in naive, "픽스처에 이름이 겹치는 구형 SKU 가 없다 — 함정이 사라졌다"
    assert "0000000000041" not in live
    assert catalog.sku("0000000000041").discontinued


def test_excluded_lookalike_is_reported_and_left_untouched(setup):
    """제외를 조용히 하지 않는다. 그리고 채널에 남은 구형 리스팅을 건드리지 않는다."""
    catalog, channels, orch = setup
    mall = channels[0]
    assert mall.fetch("M-1004").sellable is True, "구형 리스팅이 판매 중이 아니면 함정이 성립하지 않는다"

    plan = parse("형광펜 A 옐로 막아줘", catalog)
    assert plan.excluded_discontinued == ["0000000000041"]

    rep = orch.run(plan, dry_run=False)
    assert any("0000000000041" in e for e in rep.excluded_discontinued)
    assert all(c.channel_code != "M-1004" for c in rep.changes)
    assert mall.fetch("M-1004").sellable is True, "이름이 겹치는 구형 옵션이 함께 차단됐다"


def test_narrows_by_intersection_not_union(setup):
    """'형광펜 A 옐로' 가 형광펜 A 전 색상을 잡으면 안 된다."""
    catalog, _, _ = setup
    plan = parse("형광펜 A 옐로 막아줘", catalog)
    variants = {catalog.sku(a.barcode).variant for a in plan.actions}
    assert all("옐로" in v for v in variants), f"의도하지 않은 옵션 포함: {variants}"


def test_readonly_channel_is_separated_not_failed(setup):
    """쓰기 불가 채널은 실패가 아니라 '수동 처리 대상'으로 분리한다."""
    catalog, channels, orch = setup
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert rep.skipped_readonly
    assert channels[2].write_count == 0


def test_set_sku_expands_to_components(setup):
    """묶음에 물리 재고를 그대로 걸면 실재고의 배수가 팔린다."""
    catalog, _, orch = setup
    rep = orch.run(parse("형광펜 A 옐로 막아줘", catalog))
    assert rep.component_demand["0000000000011"] >= 3   # 낱개 1 + 세트 구성 2


def test_no_write_when_already_in_target_state(setup):
    """이미 목표 상태면 불필요한 쓰기를 하지 않는다."""
    catalog, channels, orch = setup
    orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    counts = [ch.write_count for ch in channels]
    orch.run(parse("형광펜 A 옐로 막아줘", catalog), dry_run=False)
    assert [ch.write_count for ch in channels] == counts


def test_unknown_instruction_does_nothing(setup):
    """의도를 판정하지 못하면 아무것도 하지 않는다."""
    catalog, channels, orch = setup
    rep = orch.run(parse("음 그거 있잖아 그거", catalog), dry_run=False)
    assert rep.changes == []
    assert all(ch.write_count == 0 for ch in channels)


def test_orphan_codes_are_reported(setup):
    """채널에는 있는데 정본과 못 잇는 코드는 드러나야 한다."""
    catalog, _, _ = setup
    assert catalog.orphan_codes("marketplace") == ["MP-77999"]
