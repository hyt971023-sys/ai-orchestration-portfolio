"""출력 — 터미널 / 마크다운 / JSON."""
from __future__ import annotations

import json

from .model import Location, Stage
from .report import Report

BAR_W = 32


def _bar(n: int, total: int, ch: str = "█") -> str:
    if not total:
        return ""
    return ch * max(0, round(n / total * BAR_W))


def as_text(r: Report) -> str:
    if not r.total:
        return "집계할 업무가 없습니다."
    L = ["", "═" * 62, " 업무 성숙도 리포트", "═" * 62, "",
         f" 총 {r.total}건", ""]
    for s in Stage:
        n = r.by_stage[s]
        L.append(f"  {s.label:<12} {_bar(n, r.total):<{BAR_W}} {n:>4}건  {n/r.total*100:>5.1f}%")
    L += ["", "─" * 62, "",
          f"  자동화 성숙도     {r.maturity_rate*100:>5.1f}%   "
          f"상위 2단계 {r.upper_count}/{r.total}건 — 사람의 기억에 의존하지 않는 구간",
          f"  실행 위치 집중도  {r.spof_rate*100:>5.1f}%   "
          f"개인 환경 의존 {r.spof_count}/{r.total}건 — 담당자 부재 시 정지",
          "", "─" * 62, "", " 실행 위치", ""]
    for loc in Location:
        n = r.by_location[loc]
        if n:
            L.append(f"  {loc.label:<16} {n:>4}건")

    if r.hidden_risk:
        L += ["", "─" * 62, "",
              f" 🔴 숨은 위험 {len(r.hidden_risk)}건 — 무인 자동인데 개인 환경에서 실행",
              "    자동화된 것처럼 보이지만 실제로는 사람 한 명에게 묶여 있습니다.", ""]
        for t in r.hidden_risk[:10]:
            L.append(f"    · {t.name}" + (f"  ({t.owner})" if t.owner else ""))
        if len(r.hidden_risk) > 10:
            L.append(f"    … 외 {len(r.hidden_risk)-10}건")

    if r.transfer_targets:
        L += ["", f" 🧠 이관 대상 {len(r.transfer_targets)}건 — 담당자 전속 단계", ""]
        for t in r.transfer_targets[:10]:
            L.append(f"    · {t.name}" + (f"  ({t.owner})" if t.owner else ""))
        if len(r.transfer_targets) > 10:
            L.append(f"    … 외 {len(r.transfer_targets)-10}건")

    L += ["", "─" * 62, " 커버리지", ""]
    L.append(f"  집계 {r.total}건" + (f" · 제외 {len(r.skipped)}건" if r.skipped else ""))
    if r.unknown_location:
        L.append(f"  실행 위치 미확인 {r.unknown_location}건 — 추측으로 채우지 않았습니다")
    if r.skipped:
        L += ["", "  제외된 행 (값이 규격과 달라 집계하지 않음):"]
        L += [f"    · {s}" for s in r.skipped[:5]]
        if len(r.skipped) > 5:
            L.append(f"    … 외 {len(r.skipped)-5}건")
    L += ["", "═" * 62, ""]
    return "\n".join(L)


def as_markdown(r: Report) -> str:
    L = ["## 업무 성숙도 리포트", "",
         f"총 **{r.total}건** 집계", "",
         "| 단계 | 건수 | 비율 | 담당자 부재 시 |", "|---|---:|---:|---|"]
    for s in Stage:
        n = r.by_stage[s]
        L.append(f"| {s.label} | {n} | {n/r.total*100:.1f}% | {s.on_absence} |")
    L += ["", "### 지표", "",
          "| 지표 | 값 | 의미 |", "|---|---:|---|",
          f"| 자동화 성숙도 | **{r.maturity_rate*100:.1f}%** | 상위 2단계 {r.upper_count}/{r.total}건 |",
          f"| 실행 위치 집중도 | **{r.spof_rate*100:.1f}%** | 개인 환경 의존 {r.spof_count}/{r.total}건 |", ""]
    if r.hidden_risk:
        L += [f"### 🔴 숨은 위험 {len(r.hidden_risk)}건", "",
              "무인 자동으로 분류됐지만 개인 환경에서 실행됩니다. "
              "자동화된 것처럼 보이지만 실제로는 사람 한 명에게 묶여 있습니다.", ""]
        L += [f"- {t.name}" + (f" ({t.owner})" if t.owner else "") for t in r.hidden_risk]
        L.append("")
    if r.transfer_targets:
        L += [f"### 🧠 이관 대상 {len(r.transfer_targets)}건", ""]
        L += [f"- {t.name}" + (f" ({t.owner})" if t.owner else "") for t in r.transfer_targets]
        L.append("")
    L += ["### 커버리지", "",
          f"- 집계 {r.total}건" + (f", 규격 불일치로 제외 {len(r.skipped)}건" if r.skipped else ""),
          f"- 실행 위치 미확인 {r.unknown_location}건 (추측으로 채우지 않음)", ""]
    return "\n".join(L)


def as_json(r: Report) -> str:
    return json.dumps({
        "total": r.total,
        "stages": {s.label: r.by_stage[s] for s in Stage},
        "locations": {l.label: r.by_location[l] for l in Location},
        "metrics": {
            "maturity_rate": round(r.maturity_rate, 4),
            "spof_rate": round(r.spof_rate, 4),
            "upper_count": r.upper_count,
            "spof_count": r.spof_count,
        },
        "hidden_risk": [t.name for t in r.hidden_risk],
        "transfer_targets": [t.name for t in r.transfer_targets],
        "coverage": {"counted": r.total, "skipped": len(r.skipped),
                     "unknown_location": r.unknown_location},
    }, ensure_ascii=False, indent=2)
