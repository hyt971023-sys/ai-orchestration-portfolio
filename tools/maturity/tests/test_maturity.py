"""측정 규칙이 실제로 지켜지는지 검증한다.

기능 테스트가 아니라 **방법론 테스트**다 —
부풀림 방지 규칙과 조용한 실패 방지가 코드에 실제로 박혀 있는지 본다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from maturity.__main__ import SAMPLE, main
from maturity.model import Location, Stage, Task
from maturity.render import as_json, as_markdown, as_text
from maturity.report import Report, load


@pytest.fixture
def csv_file(tmp_path) -> Path:
    p = tmp_path / "tasks.csv"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


@pytest.fixture
def report(csv_file) -> Report:
    return Report(*load(csv_file))


# ── 두 축이 독립인가 ──────────────────────────────────
def test_stage_and_location_are_independent_axes(report):
    """성숙도가 높아도 실행 위치가 나쁘면 위험하다 — 이 도구의 존재 이유."""
    assert report.hidden_risk, "무인 자동 + 개인 환경 조합이 탐지되지 않았다"
    for t in report.hidden_risk:
        assert t.stage is Stage.UNATTENDED
        assert t.location.is_spof


def test_upper_stage_definition():
    assert Stage.UNATTENDED.is_upper and Stage.TOOLED.is_upper
    assert not Stage.DOCUMENTED.is_upper and not Stage.PERSONAL.is_upper


# ── 부풀림 방지 ──────────────────────────────────────
def test_unknown_location_is_not_dropped_from_denominator(report):
    """모름을 분모에서 빼면 지표가 좋아 보인다. 그래서 빼지 않는다."""
    assert report.unknown_location > 0
    assert sum(report.by_location.values()) == report.total


def test_metrics_use_full_total(report):
    assert report.maturity_rate == report.upper_count / report.total
    assert report.spof_rate == report.spof_count / report.total


def test_bad_rows_are_reported_not_silently_dropped(tmp_path):
    """규격 불일치 행을 조용히 버리면 커버리지가 거짓이 된다."""
    p = tmp_path / "bad.csv"
    p.write_text("업무명,성숙도,실행위치\n정상,도구화,공용 인프라\n이상,알수없는단계,공용 인프라\n",
                 encoding="utf-8")
    tasks, skipped = load(p)
    assert len(tasks) == 1
    assert len(skipped) == 1 and "이상" in skipped[0]


def test_missing_required_column_fails_loudly(tmp_path):
    p = tmp_path / "nocol.csv"
    p.write_text("이름,단계\n가,나\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load(p)


# ── 조용한 실패 방지 ──────────────────────────────────
def test_zero_rows_exits_nonzero(tmp_path, capsys):
    """0건인데 성공으로 끝나면 '검사했는데 아무 문제 없음'과 구분이 안 된다."""
    p = tmp_path / "empty.csv"
    p.write_text("업무명,성숙도\n", encoding="utf-8")
    assert main(["report", str(p)]) == 1


def test_strict_mode_fails_on_bad_rows(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("업무명,성숙도\n정상,도구화\n이상,없는단계\n", encoding="utf-8")
    assert main(["report", str(p)]) == 0
    assert main(["report", str(p), "--strict"]) == 1


def test_missing_file_exits_nonzero(tmp_path):
    assert main(["report", str(tmp_path / "nope.csv")]) == 2


# ── 출력 ────────────────────────────────────────────
def test_all_formats_render(report):
    assert "업무 성숙도 리포트" in as_text(report)
    assert "| 단계 |" in as_markdown(report)
    d = json.loads(as_json(report))
    assert d["total"] == report.total
    assert d["coverage"]["unknown_location"] == report.unknown_location


def test_coverage_is_always_reported(report):
    """세지 않은 것을 밝히지 않은 조사는 전수라고 부를 수 없다."""
    for fn in (as_text, as_markdown):
        assert "커버리지" in fn(report)


def test_sample_is_valid_input(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(SAMPLE, encoding="utf-8")
    tasks, skipped = load(p)
    assert tasks and not skipped, "예시 파일이 자기 규격을 못 지키면 안 된다"


# ── 별칭 파싱 ────────────────────────────────────────
@pytest.mark.parametrize("raw,expect", [
    ("무인 자동", Stage.UNATTENDED), ("무인자동", Stage.UNATTENDED),
    ("1", Stage.UNATTENDED), ("tooled", Stage.TOOLED), ("담당자 전속", Stage.PERSONAL),
])
def test_stage_aliases(raw, expect):
    assert Stage.parse(raw) is expect


@pytest.mark.parametrize("raw,expect", [
    ("", Location.UNKNOWN), ("로컬", Location.PERSONAL),
    ("서버", Location.SHARED), ("manual", Location.MANUAL),
])
def test_location_aliases(raw, expect):
    assert Location.parse(raw) is expect
