"""정본 식별키(바코드) 기준 카탈로그와 크로스워크 사전.

실무에서 배운 것: 자동화의 어려움은 실행이 아니라 **식별**에 있다.
채널마다 상품 체계가 다르므로, 상품명 매칭은 반드시 사고를 만든다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class Component:
    """세트를 구성하는 낱개 품목."""
    barcode: str
    qty: int


@dataclass(frozen=True)
class Sku:
    """정본 SKU. barcode 가 유일한 식별키다."""
    barcode: str
    name: str
    variant: str
    discontinued: bool = False
    components: tuple[Component, ...] = field(default_factory=tuple)

    @property
    def is_set(self) -> bool:
        return bool(self.components)


class Catalog:
    """바코드 ↔ 채널별 상품코드 크로스워크.

    실무 교훈 3가지를 그대로 반영했다.
      1. 상품명이 아니라 바코드를 정본키로 쓴다
      2. 매칭 실패는 조용히 넘기지 않고 '미파싱'으로 보고한다
      3. 단종 SKU 는 현행 SKU 와 반드시 구분한다 (구형/리뉴얼 혼동 방지)
    """

    def __init__(self, skus: dict[str, Sku], crosswalk: dict[str, dict[str, str]]):
        self._skus = skus
        self._crosswalk = crosswalk           # {channel: {channel_code: barcode}}

    @classmethod
    def load(cls, path: Path | None = None) -> "Catalog":
        raw = json.loads((path or FIXTURES / "catalog.json").read_text(encoding="utf-8"))
        skus = {
            s["barcode"]: Sku(
                barcode=s["barcode"],
                name=s["name"],
                variant=s["variant"],
                discontinued=s.get("discontinued", False),
                components=tuple(Component(**c) for c in s.get("components", [])),
            )
            for s in raw["skus"]
        }
        return cls(skus, raw["crosswalk"])

    # ── 조회 ────────────────────────────────────────────────
    def sku(self, barcode: str) -> Sku:
        return self._skus[barcode]

    def all_skus(self) -> list[Sku]:
        return list(self._skus.values())

    def resolve(self, channel: str, channel_code: str) -> Sku | None:
        """채널 상품코드 → 정본 SKU. 사전에 없으면 None (추측하지 않는다)."""
        barcode = self._crosswalk.get(channel, {}).get(channel_code)
        return self._skus.get(barcode) if barcode else None

    def channel_codes(self, channel: str, barcode: str) -> list[str]:
        """정본 SKU → 해당 채널의 상품코드들 (1:N 가능)."""
        return [c for c, b in self._crosswalk.get(channel, {}).items() if b == barcode]

    def search(self, term: str, *, include_discontinued: bool = False) -> list[Sku]:
        """자연어 지시에서 뽑은 단어로 SKU 검색.

        🔴 기본값은 단종 SKU 제외다 — 구형 옵션명이 현행과 그대로 겹치기 때문에
           (예: `01 옐로` 와 `01 옐로 (구형)`) 이름으로 고르면 엉뚱한 옵션을 닫게 된다.

        include_discontinued=True 는 **상품명 매칭이 무엇을 잡았을지**를 재현하는 용도다.
        이 결과와 기본 결과의 차이가 곧 정본키(바코드)가 막아준 오차다.
        """
        t = term.strip().lower()
        return [
            s for s in self._skus.values()
            if (include_discontinued or not s.discontinued)
            and (t in s.name.lower() or t in s.variant.lower())
        ]

    def parse_rate(self, channel: str) -> tuple[int, int]:
        """크로스워크 파싱률. 미파싱 건은 수동 대상으로 분리 보고한다."""
        codes = self._crosswalk.get(channel, {})
        matched = sum(1 for b in codes.values() if b in self._skus)
        return matched, len(codes)

    def to_component_demand(self, barcode: str, units: int) -> dict[str, int]:
        """세트 수량 → 구성품 수량 환산.

        묶음 상품에 물리 재고를 그대로 걸면 실재고의 배수가 팔린다.
        """
        sku = self.sku(barcode)
        if not sku.is_set:
            return {barcode: units}
        return {c.barcode: c.qty * units for c in sku.components}

    def orphan_codes(self, channel: str) -> list[str]:
        """채널에는 존재하지만 정본 SKU 로 잇지 못한 코드.

        이것이 진짜 '미매칭'이다. 채널이 그 상품을 안 파는 것과 구분해야 한다.
        """
        return [c for c, b in self._crosswalk.get(channel, {}).items()
                if b not in self._skus]
