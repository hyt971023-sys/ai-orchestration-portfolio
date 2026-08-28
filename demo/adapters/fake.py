"""더미 채널 3종. 실제 서비스와 무관한 가짜 데이터로 동작한다."""
from __future__ import annotations

import json
from pathlib import Path

from .base import Capability, ChannelAdapter, Listing, WriteResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


class _MemoryChannel(ChannelAdapter):
    def __init__(self, name: str, capability: Capability, listings: dict[str, Listing]):
        self.name = name
        self.capability = capability
        self._listings = listings
        self.write_count = 0

    @classmethod
    def from_fixture(cls, name: str, capability: Capability) -> "_MemoryChannel":
        raw = json.loads((FIXTURES / "channels.json").read_text(encoding="utf-8"))
        rows = raw[name]
        return cls(name, capability, {r["channel_code"]: Listing(**r) for r in rows})

    def fetch(self, channel_code: str) -> Listing | None:
        item = self._listings.get(channel_code)
        # 사본을 돌려준다 — 호출자가 내부 상태를 직접 바꾸지 못하게
        return Listing(**vars(item)) if item else None

    def list_all(self) -> list[Listing]:
        return [Listing(**vars(v)) for v in self._listings.values()]

    def set_sellable(self, channel_code: str, sellable: bool) -> WriteResult:
        if not self.supports_write():
            return WriteResult(False, self.name, channel_code,
                               "쓰기 미지원 채널 — 수동 처리 대상으로 분리")
        item = self._listings.get(channel_code)
        if item is None:
            return WriteResult(False, self.name, channel_code, "채널에 해당 코드 없음")
        item.sellable = sellable
        # 🔴 진열(displayed)은 건드리지 않는다.
        #    진열까지 끄면 상품이 목록에서 사라져 되돌아올 경로를 잃는다.
        self.write_count += 1
        return WriteResult(True, self.name, channel_code,
                           f"판매 플래그 → {'ON' if sellable else 'OFF'}")


class FakeMall(_MemoryChannel):
    """자사몰 — 조회·수정 모두 가능."""
    def __init__(self):
        c = _MemoryChannel.from_fixture("mall", Capability.READ_WRITE)
        super().__init__("mall", c.capability, c._listings)


class FakeMarketplace(_MemoryChannel):
    """마켓플레이스 — 조회·수정 모두 가능."""
    def __init__(self):
        c = _MemoryChannel.from_fixture("marketplace", Capability.READ_WRITE)
        super().__init__("marketplace", c.capability, c._listings)


class FakeReadOnlyChannel(_MemoryChannel):
    """조회만 되는 채널 — 실제 운영에 반드시 하나쯤 있다.

    이 채널의 존재가 이 데모의 요점 중 하나다.
    전 채널 자동 제어를 가정하고 설계하면 여기서 무너진다.
    """
    def __init__(self):
        c = _MemoryChannel.from_fixture("partner", Capability.READ_ONLY)
        super().__init__("partner", c.capability, c._listings)
