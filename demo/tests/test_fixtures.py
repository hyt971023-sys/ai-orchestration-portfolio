"""픽스처가 실물과 이어지지 않는다는 사실을 '문장'이 아니라 '검사'로 고정한다.

더미 데이터라는 설명은 문서에 적어두면 조용히 낡는다.
값을 한 번 손대면 설명만 맞고 데이터는 틀린 상태가 되고, 그건 아무도 모른다.
그래서 픽스처 파일의 _note 가 주장하는 조건을 그대로 테스트로 옮겨 놓았다.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "catalog.json"
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))


def ean13_check_digit(first12: str) -> int:
    """EAN-13 검사숫자. 홀수 자리 가중치 1, 짝수 자리 가중치 3."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def all_barcodes() -> set[str]:
    codes = {s["barcode"] for s in RAW["skus"]}
    codes |= {c["barcode"] for s in RAW["skus"] for c in s.get("components", [])}
    codes |= {b for m in RAW["crosswalk"].values() for b in m.values()}
    return codes


def test_barcodes_are_13_digits():
    for bc in sorted(all_barcodes()):
        assert len(bc) == 13 and bc.isdigit(), f"13자리 숫자가 아니다: {bc}"


def test_every_barcode_check_digit_is_invalid():
    """🔴 전건 무효여야 한다.

    체크디지트가 유효한 값이 하나라도 섞이면 그 숫자는 '형식상 성립하는 GTIN' 이 되고,
    픽스처가 실물 상품을 가리킬 수 있게 된다. 그래서 개수가 아니라 전건으로 본다.
    """
    valid = [bc for bc in sorted(all_barcodes())
             if int(bc[12]) == ean13_check_digit(bc[:12])]
    assert not valid, f"체크디지트가 유효한 바코드가 섞였다: {valid}"


def test_barcode_inventory_matches_note():
    """_note 가 적어둔 개수(SKU 12 + 미연결 1 = 13)와 데이터가 어긋나지 않게 못박는다."""
    assert len(RAW["skus"]) == 12
    orphans = {b for m in RAW["crosswalk"].values() for b in m.values()} \
              - {s["barcode"] for s in RAW["skus"]}
    assert len(orphans) == 1, f"정본 미연결 코드 개수가 바뀌었다: {sorted(orphans)}"
    assert len(all_barcodes()) == 13
