# maturity — 업무 성숙도 측정 도구

운영 업무를 4단계로 분류하고 **자동화 성숙도**와 **실행 위치 집중도** 두 지표를 산출합니다.
방법론: [`docs/maturity-framework.md`](../../docs/maturity-framework.md)

```bash
export PYTHONPATH=tools
python -m maturity sample > tasks.csv     # 예시 입력 생성
python -m maturity report tasks.csv       # 리포트
python -m maturity report tasks.csv -f md
python -m maturity report tasks.csv -f json
python -m pytest tools/maturity/tests -q  # 방법론 검증 21건
```

## 입력 형식

| 열 | 필수 | 값 |
|---|---|---|
| `업무명` | ✅ | 자유 텍스트 |
| `성숙도` | ✅ | 무인 자동 / 도구화 / 절차화 / 담당자 전속 (또는 `1`~`4`, 영문) |
| `실행위치` | | 공용 인프라 / 개인 환경 / 사람이 직접 실행 / 미확인 (비우면 미확인) |
| `담당` | | |
| `비고` | | |

## 이 도구가 실제로 하는 일

**두 축을 분리해서 셉니다.** 성숙도만 보면 놓치는 구간이 있기 때문입니다.

```
🔴 숨은 위험 2건 — 무인 자동인데 개인 환경에서 실행
   자동화된 것처럼 보이지만 실제로는 사람 한 명에게 묶여 있습니다.

   · 야간 데이터 적재 배치  (A)
   · 큐 적체 임계 알림  (A)
```

`무인 자동`으로 분류돼 성숙도 지표를 올려주지만, 담당자가 자리를 비우면 멈춥니다.
축을 하나만 쓰면 **이 구간이 성과로 집계**됩니다.

## 측정 규칙이 코드에 박혀 있습니다

부풀림 방지 규칙을 문서로만 두지 않고 테스트로 고정했습니다.

| 규칙 | 구현 | 테스트 |
|---|---|---|
| 모름은 모름으로 | 미확인을 분모에서 빼지 않음 | `test_unknown_location_is_not_dropped_from_denominator` |
| 조용히 버리지 않음 | 규격 불일치 행을 사유와 함께 보고 | `test_bad_rows_are_reported_not_silently_dropped` |
| 커버리지 명시 | 모든 출력 형식에 커버리지 포함 | `test_coverage_is_always_reported` |
| **0건은 성공이 아님** | 집계 0건이면 종료코드 1 | `test_zero_rows_exits_nonzero` |
| 필수 열 누락은 즉시 실패 | 조용히 빈 결과 대신 예외 | `test_missing_required_column_fails_loudly` |

마지막 두 개가 핵심입니다. **"검사할 게 없어서 통과"** 는 이 저장소가
[조용한 실패 유형 3](../../docs/silent-failure-patterns.md)으로 정의한 실패 유형이고,
[케이스 06](../../cases/06-gate-failure.md)에서 실제로 당한 적이 있습니다.
그래서 제가 만드는 도구에는 매번 이 가드를 넣습니다.
