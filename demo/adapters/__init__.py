"""채널 어댑터 — 전부 가짜다. 실제 API 는 호출하지 않는다.

실무 교훈: **설계 전에 채널별 '쓰기 가능 여부'부터 전수 조사해야 한다.**
조회만 되고 수정이 안 되는 채널을 모르고 설계하면
실행 단계에서 절반이 수동으로 되돌아온다.
"""
from .base import ChannelAdapter, Capability, WriteResult
from .fake import FakeMall, FakeMarketplace, FakeReadOnlyChannel

__all__ = [
    "ChannelAdapter", "Capability", "WriteResult",
    "FakeMall", "FakeMarketplace", "FakeReadOnlyChannel",
]
