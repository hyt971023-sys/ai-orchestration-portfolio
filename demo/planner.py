"""자연어 지시 → 실행 계획.

여기서 LLM 을 호출해도 되지만, 데모는 결정적(deterministic) 파서를 쓴다.
이유: 포트폴리오 데모는 **누가 언제 돌려도 같은 결과**가 나와야 하고,
      이 케이스의 핵심은 모델이 아니라 그 앞뒤의 안전장치이기 때문이다.

실무에서는 이 자리에 코딩 에이전트가 들어가고, 산출물은 동일한 Plan 객체다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import Catalog, Sku


@dataclass
class Action:
    barcode: str
    sellable: bool
    reason: str


@dataclass
class Plan:
    intent: str
    actions: list[Action]
    unresolved: list[str]        # 매칭 실패 — 추측하지 않고 사람에게 넘긴다
    notes: list[str]
    # 이름은 걸렸지만 정본키(바코드)가 달라 대상에서 뺀 단종 SKU.
    # 조용히 빼면 "안 걸린 것"과 구분되지 않으므로 결과에 그대로 남긴다.
    excluded_discontinued: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.actions


_BLOCK = re.compile(r"막아|차단|중단|끄|품절|정지|stop|block")
_OPEN = re.compile(r"열어|풀어|재개|켜|판매\s*재개|open|resume")
_STOPWORDS = {
    "재고", "부족", "하니까", "해줘", "해주세요", "전", "채널", "에서", "모든",
    "좀", "지금", "바로", "다시", "해라", "please", "the", "on", "all",
}


def parse(text: str, catalog: Catalog) -> Plan:
    notes: list[str] = []

    if _BLOCK.search(text):
        sellable, verb = False, "판매 차단"
    elif _OPEN.search(text):
        sellable, verb = True, "판매 재개"
    else:
        return Plan(text, [], [], ["의도를 판정하지 못함 — 실행하지 않고 종료"])

    # 지시문에서 검색어 후보 추출
    tokens = [t for t in re.split(r"[\s,·/]+", text) if t and t not in _STOPWORDS]
    terms = [t for t in tokens
             if len(t) >= 2 and not _BLOCK.search(t) and not _OPEN.search(t)]

    # 🔴 내 초기 구현은 상품 단위로 전 조합을 닫았다. 검색어를 OR 로 합치면 결과가 그것과 같아진다 —
    #    "형광펜 A 옐로" 가 형광펜 A 전 색상을 잡는다.
    #    한 옵션만 부족한데 전 조합을 닫으면 팔 수 있는 재고까지 스스로 막는다.
    #    그게 왜 틀렸는지 알고 나서 조합 단위로(교집합, AND) 좁히도록 고쳤다.
    matched: list[set[str]] = []
    unresolved: list[str] = []
    for term in terms:
        found = catalog.search(term)
        if found:
            matched.append({s.barcode for s in found})
        else:
            unresolved.append(term)

    # 🔴 상품명으로 골랐다면 무엇이 걸렸을지를 같은 규칙으로 재현한다.
    #    구형/단종 옵션은 현행과 이름이 그대로 겹치므로 이름 매칭에서는 구분되지 않는다.
    #    바코드를 정본키로 쓰면 여기서 갈린다 — 그 차이를 숨기지 않고 보고한다.
    naive: list[set[str]] = []
    for term in terms:
        found = catalog.search(term, include_discontinued=True)
        if found:
            naive.append({s.barcode for s in found})
    excluded = sorted(
        b for b in (set.intersection(*naive) if naive else set())
        if catalog.sku(b).discontinued
    )

    if not matched:
        notes.append("검색어로 SKU 를 특정하지 못함 — 추측하지 않고 중단한다")
        return Plan(text, [], unresolved, notes, excluded)

    narrowed = set.intersection(*matched)
    if not narrowed:
        # 교집합이 비면 넓히지 않는다. 넓히는 순간 의도하지 않은 대상이 섞인다.
        notes.append("검색어 조합에 해당하는 SKU 없음 — 넓히지 않고 중단한다")
        return Plan(text, [], terms, notes, excluded)

    if len(matched) > 1:
        notes.append(f"검색어 {len(matched)}개를 교집합으로 좁힘 — 대상 {len(narrowed)}건")

    # 세트 SKU 는 구성품이 대상에 포함되면 함께 잡는다 (세트만 남으면 오버셀)
    for sku in catalog.all_skus():
        if sku.is_set and not sku.discontinued and any(
                c.barcode in narrowed for c in sku.components):
            narrowed.add(sku.barcode)

    hits = {b: catalog.sku(b) for b in narrowed}

    # 🔴 부족한 것만 골라 닫는다.
    #    상품 단위로 전 조합을 닫으면 팔 수 있는 재고까지 함께 막는다.
    actions = [Action(s.barcode, sellable, f"{verb}: {s.name} {s.variant}")
               for s in sorted(hits.values(), key=lambda x: x.barcode)]

    if any(catalog.sku(a.barcode).is_set for a in actions):
        notes.append("세트 SKU 포함 — 구성품 환산이 적용된다")
    if excluded:
        notes.append(
            f"이름이 겹치는 단종 SKU {len(excluded)}건을 정본키로 제외 "
            f"— 상품명으로 골랐다면 함께 차단됐다")
    else:
        notes.append("이름이 겹치는 단종 SKU 없음")

    return Plan(text, actions, unresolved, notes, excluded)
