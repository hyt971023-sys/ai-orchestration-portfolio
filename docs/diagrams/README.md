# 아키텍처 다이어그램

말로 설명하면 세 문단이 필요한 것을 한 장으로 보여주는 그림만 모았습니다.
GitHub 에서 바로 렌더링됩니다.

---

## 1. 멀티채널 재고 오케스트레이션 — 전체 구조

자연어 지시 한 줄이 여러 채널의 판매 상태로 도달하기까지.
**굵은 화살표가 실행 경로, 점선이 안전장치입니다.**

```mermaid
flowchart TB
    U["담당자 지시<br><i>&quot;형광펜 A 옐로 재고 부족하니<br>전 채널에서 막아줘&quot;</i>"]

    subgraph PLAN ["① 계획 수립"]
        P["플래너<br><small>지시 → 실행 계획</small>"]
        X["크로스워크 사전<br><small>바코드 = 정본키</small>"]
        P -.->|"검색어 교집합"| X
        X -.->|"단종 SKU 제외 <b>+ 제외 사실 보고</b><br>세트 → 구성품 환산"| P
    end

    subgraph GUARD ["② 안전장치"]
        D{"dry-run<br>기본값"}
        S[("롤백 스냅샷<br><small>before 값 저장</small>")]
        D -->|"--apply 시에만"| S
        S -.->|"저장 실패 시<br><b>실행 중단</b>"| STOP(["중단"])
    end

    subgraph EXEC ["③ 실행"]
        CAP{"채널 쓰기<br>가능?"}
        W["판매 플래그 OFF<br><small>노출 플래그 아님</small>"]
        M["수동 처리 목록<br><small>실패 아님, 분리</small>"]
        CAP -->|"가능"| W
        CAP -->|"조회만 가능"| M
    end

    subgraph VERIFY ["④ 검증"]
        RB["독립 재조회<br><small>read-back</small>"]
        OK(["반영 확인"])
        NG(["🔴 롤백 검토"])
        RB -->|"일치"| OK
        RB -->|"불일치"| NG
    end

    U ==> P
    P ==> D
    D ==>|"변경 예정 출력"| PREVIEW(["미리보기<br><small>아무것도 안 바꿈</small>"])
    S ==> CAP
    W ==> RB

    style U fill:#E8F0F7,stroke:#14568F,stroke-width:2px
    style STOP fill:#FBF0E7,stroke:#A85520,stroke-width:2px
    style NG fill:#FBF0E7,stroke:#A85520,stroke-width:2px
    style OK fill:#E9F2ED,stroke:#2A6349,stroke-width:2px
    style PREVIEW fill:#E9F2ED,stroke:#2A6349
    style M fill:#FBF0E7,stroke:#A85520
```

**설계 판단 4가지**

| 지점 | 왜 이렇게 했나 |
|---|---|
| 바코드를 정본키로 | 상품명 매칭은 구형·리뉴얼 버전을 혼동해 엉뚱한 옵션을 차단한다 |
| 검색어를 **교집합**으로 | 합집합이면 "형광펜 A 옐로"가 형광펜 A 전 색상을 잡아, 팔 수 있는 재고까지 막는다 |
| 노출이 아니라 **판매 플래그** | 품절 표시만으로는 실제 주문이 막히지 않는 채널이 있다 |
| 쓰기 불가 채널은 **분리** | 실패로 처리하면 전체가 실패한다. 수동 대상으로 넘겨야 나머지가 진행된다 |

---

## 2. 안전 설계 4원칙 — 실행 순서로 본 배치

원칙이 코드의 어느 지점에 박히는지.

```mermaid
flowchart LR
    A["변경 요청"] --> B{"원칙 2<br>읽기가 기본값인가"}
    B -->|"조회 도구"| RO(["읽기 전용<br>쓰기 권한 없음"])
    B -->|"실행 도구"| C{"원칙 1<br>되돌릴 수 있는가"}
    C -->|"스냅샷 없음"| STOP(["🔴 실행 중단"])
    C -->|"스냅샷 저장됨"| D{"원칙 4<br>판단을 위임하나"}
    D -->|"정책 판단 포함"| OBS["dry-run 으로 관찰<br><small>1주 · 알림만</small>"]
    D -->|"단순 실행"| E["쓰기"]
    OBS -->|"정확도 확인 후"| E
    E --> F{"원칙 3<br>반영됐는가"}
    F -->|"200 OK 만 확인"| BAD(["🔴 검증 아님"])
    F -->|"독립 재조회"| G(["반영 확인 완료"])

    style STOP fill:#FBF0E7,stroke:#A85520,stroke-width:2px
    style BAD fill:#FBF0E7,stroke:#A85520,stroke-width:2px
    style G fill:#E9F2ED,stroke:#2A6349,stroke-width:2px
    style RO fill:#E8F0F7,stroke:#14568F
```

---

## 3. 성숙도 프레임워크 — 두 축이 독립인 이유

성숙도만 보면 놓치는 구간이 있습니다.

```mermaid
quadrantChart
    title 성숙도 × 실행 위치
    x-axis "개인 환경 실행" --> "공용 인프라 실행"
    y-axis "담당자 전속" --> "무인 자동"
    quadrant-1 "안전 — 사람 없이 유지"
    quadrant-2 "🔴 숨은 위험 — 자동인데 한 사람에 묶임"
    quadrant-3 "이관 대상 — 보이는 위험"
    quadrant-4 "절차화 진행 중"
    "야간 데이터 적재 배치": [0.18, 0.88]
    "큐 적체 임계 알림": [0.22, 0.82]
    "정기 지표 리포트": [0.85, 0.90]
    "외부 연동 감시": [0.80, 0.84]
    "설정 일괄 적용 도구": [0.62, 0.55]
    "정합 검사 스크립트": [0.66, 0.50]
    "신규 항목 등록 절차": [0.55, 0.30]
    "월별 집계 대사": [0.15, 0.12]
    "예외 규정 판정": [0.12, 0.08]
```

**2사분면이 이 프레임워크를 만든 이유입니다.**
`무인 자동`으로 분류돼 성숙도 지표를 올려주지만, 실제로는 담당자 한 명에게 묶여 있습니다.
축을 하나만 쓰면 **이 구간이 성과로 집계**됩니다.

→ 측정 도구: [`tools/maturity`](../../tools/maturity/) — CSV 를 넣으면 이 구간을 자동으로 뽑아냅니다.

---

## 4. 조용한 실패 탐지 — 감시자를 어디에 두는가

```mermaid
flowchart TB
    subgraph BAD ["❌ 흔한 구성"]
        S1["스케줄러"] --> J1["작업"]
        J1 -->|"실패 시"| A1["알림"]
        S1 -.->|"스케줄러가 죽으면"| X1(["작업도 알림도<br>발생하지 않음"])
    end

    subgraph GOOD ["✅ 고친 구성"]
        S2["스케줄러"] --> J2["작업"]
        J2 -->|"성공 시"| H[("마지막 성공 시각<br>기록")]
        W["감시자<br><small>다른 실행 경로</small>"] -.->|"주기적으로<br>나이 확인"| H
        W -->|"기대 주기 초과"| A2(["알림"])
    end

    style X1 fill:#FBF0E7,stroke:#A85520,stroke-width:2px
    style A2 fill:#E9F2ED,stroke:#2A6349,stroke-width:2px
    style W fill:#E8F0F7,stroke:#14568F,stroke-width:2px
```

**핵심은 두 가지입니다.**
① 실패가 아니라 **마지막 성공 시각의 나이**를 감시한다 — 실행이 없으면 실패도 없으므로
② 감시자를 **감시 대상과 다른 실행 경로**에 둔다 — 같은 스케줄러 위에 있으면 함께 죽는다
