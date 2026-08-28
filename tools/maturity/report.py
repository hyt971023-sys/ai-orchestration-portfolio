"""집계와 지표 산출.

측정 규칙 (부풀림 방지 — 방법론 문서와 동일):
  1. 추정 금지 — 입력에 없는 값을 만들어내지 않는다
  2. 모름은 모름으로 — 미확인은 미확인으로 집계하고 분모에서 빼지 않는다
  3. 커버리지 명시 — 세지 않은 것을 결과에 함께 보고한다
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .model import Location, Stage, Task

REQUIRED = ("업무명", "성숙도")


def load(path: Path) -> tuple[list[Task], list[str]]:
    """CSV 로드. 잘못된 행은 버리지 않고 사유와 함께 돌려준다."""
    tasks: list[Task] = []
    skipped: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(
                f"필수 열이 없습니다: {', '.join(missing)}\n"
                f"  현재 열: {', '.join(reader.fieldnames or [])}\n"
                f"  `python -m maturity sample` 로 예시 파일을 만들어 보세요.")
        for i, row in enumerate(reader, start=2):
            name = (row.get("업무명") or "").strip()
            if not name:
                continue
            try:
                tasks.append(Task(
                    name=name,
                    stage=Stage.parse(row.get("성숙도", "")),
                    location=Location.parse(row.get("실행위치", "")),
                    owner=(row.get("담당") or "").strip(),
                    note=(row.get("비고") or "").strip(),
                ))
            except ValueError as e:
                skipped.append(f"{i}행 「{name}」 — {e}")
    return tasks, skipped


@dataclass
class Report:
    tasks: list[Task]
    skipped: list[str]

    @property
    def total(self) -> int:
        return len(self.tasks)

    @property
    def by_stage(self) -> Counter:
        return Counter(t.stage for t in self.tasks)

    @property
    def by_location(self) -> Counter:
        return Counter(t.location for t in self.tasks)

    @property
    def upper_count(self) -> int:
        return sum(1 for t in self.tasks if t.stage.is_upper)

    @property
    def maturity_rate(self) -> float:
        """자동화 성숙도 — 상위 2단계 비율."""
        return self.upper_count / self.total if self.total else 0.0

    @property
    def spof_count(self) -> int:
        return sum(1 for t in self.tasks if t.location.is_spof)

    @property
    def spof_rate(self) -> float:
        """실행 위치 집중도 — 개인 환경 의존 비율."""
        return self.spof_count / self.total if self.total else 0.0

    @property
    def hidden_risk(self) -> list[Task]:
        """가장 위험한 구간 — 무인 자동인데 개인 환경에서 도는 것.

        자동화된 것처럼 보이지만 실제로는 사람 한 명에게 묶여 있다.
        지표를 두 축으로 나누기 전에는 보이지 않던 항목이다.
        """
        return [t for t in self.tasks
                if t.stage is Stage.UNATTENDED and t.location.is_spof]

    @property
    def transfer_targets(self) -> list[Task]:
        """이관 대상 — 담당자 전속 단계."""
        return [t for t in self.tasks if t.stage is Stage.PERSONAL]

    @property
    def unknown_location(self) -> int:
        return self.by_location[Location.UNKNOWN]
