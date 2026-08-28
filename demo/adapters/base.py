from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Capability(Enum):
    """채널이 실제로 할 수 있는 것. 설계 전에 반드시 실측해야 하는 값."""
    READ_ONLY = "조회만 가능"
    READ_WRITE = "조회·수정 가능"


@dataclass
class WriteResult:
    ok: bool
    channel: str
    channel_code: str
    detail: str


@dataclass
class Listing:
    """채널에 올라가 있는 판매 단위."""
    channel_code: str
    name: str
    sellable: bool          # 실제 판매 차단 플래그
    displayed: bool         # 노출 플래그 — 이것만 꺼서는 판매가 안 막힌다
    qty: int


class ChannelAdapter(ABC):
    """채널 어댑터 인터페이스.

    설계 원칙 — 쓰기 메서드는 read-back 검증까지 책임진다.
    `200 OK` 를 반영으로 믿지 않는다.
    """
    name: str
    capability: Capability

    @abstractmethod
    def fetch(self, channel_code: str) -> Listing | None: ...

    @abstractmethod
    def list_all(self) -> list[Listing]: ...

    @abstractmethod
    def set_sellable(self, channel_code: str, sellable: bool) -> WriteResult: ...

    def supports_write(self) -> bool:
        return self.capability is Capability.READ_WRITE
