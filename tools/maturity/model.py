"""도메인 모델 — 4단계 정의와 판별 규칙."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Stage(Enum):
    """업무 성숙도 4단계. 순서가 곧 성숙도 서열이다."""
    UNATTENDED = ("무인 자동", "사람 개입 없이 정해진 시각에 실행", "계속 돈다")
    TOOLED = ("도구화", "명령 1회 실행으로 완료", "멈추지만 누구나 재개")
    DOCUMENTED = ("절차화", "문서·체크리스트로 인계 가능", "멈추지만 인계 가능")
    PERSONAL = ("담당자 전속", "아직 한 사람 손에만 있음", "멈추고 재개 방법을 모른다")

    def __init__(self, label: str, definition: str, on_absence: str):
        self.label = label
        self.definition = definition
        self.on_absence = on_absence          # 담당자 부재 시 무슨 일이 생기나

    @property
    def is_upper(self) -> bool:
        """상위 2단계 — 사람의 기억에 의존하지 않는 구간."""
        return self in (Stage.UNATTENDED, Stage.TOOLED)

    @classmethod
    def parse(cls, raw: str) -> "Stage":
        t = (raw or "").strip().lower()
        alias = {
            "무인 자동": cls.UNATTENDED, "무인자동": cls.UNATTENDED,
            "unattended": cls.UNATTENDED, "auto": cls.UNATTENDED, "1": cls.UNATTENDED,
            "도구화": cls.TOOLED, "tooled": cls.TOOLED, "tool": cls.TOOLED, "2": cls.TOOLED,
            "절차화": cls.DOCUMENTED, "documented": cls.DOCUMENTED, "doc": cls.DOCUMENTED, "3": cls.DOCUMENTED,
            "담당자 전속": cls.PERSONAL, "담당자전속": cls.PERSONAL,
            "personal": cls.PERSONAL, "individual": cls.PERSONAL, "4": cls.PERSONAL,
        }
        if t not in alias:
            raise ValueError(
                f"알 수 없는 성숙도: {raw!r}\n"
                f"  허용: 무인 자동 / 도구화 / 절차화 / 담당자 전속 (또는 1~4, 영문)")
        return alias[t]


class Location(Enum):
    """실행 위치 — 성숙도와 독립된 축.

    무인 자동인데 개인 환경에서 도는 자산은
    '자동화된 것처럼 보이지만 실제로는 사람 한 명에게 묶여 있다.'
    """
    SHARED = ("공용 인프라", False)
    PERSONAL = ("개인 환경", True)
    MANUAL = ("사람이 직접 실행", False)
    UNKNOWN = ("미확인", False)

    def __init__(self, label: str, is_spof: bool):
        self.label = label
        self.is_spof = is_spof            # 단일 환경 의존인가

    @classmethod
    def parse(cls, raw: str) -> "Location":
        t = (raw or "").strip().lower()
        alias = {
            "": cls.UNKNOWN, "미확인": cls.UNKNOWN, "unknown": cls.UNKNOWN, "?": cls.UNKNOWN,
            "공용": cls.SHARED, "공용 인프라": cls.SHARED, "서버": cls.SHARED,
            "shared": cls.SHARED, "server": cls.SHARED,
            "개인": cls.PERSONAL, "개인 환경": cls.PERSONAL, "로컬": cls.PERSONAL,
            "personal": cls.PERSONAL, "local": cls.PERSONAL,
            "수동": cls.MANUAL, "사람이 직접 실행": cls.MANUAL, "manual": cls.MANUAL,
        }
        if t not in alias:
            raise ValueError(
                f"알 수 없는 실행 위치: {raw!r}\n"
                f"  허용: 공용 인프라 / 개인 환경 / 사람이 직접 실행 / 미확인")
        return alias[t]


@dataclass(frozen=True)
class Task:
    name: str
    stage: Stage
    location: Location
    owner: str = ""
    note: str = ""
