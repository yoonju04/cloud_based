# AI 평가 확장 모듈

선택 사항입니다. 결정론적 안전 판정을 바꾸지 않습니다.

## English

SIL log, then the deterministic KPI, then a vector of review questions, then a Ridge score and a logistic probability. The two models only order human review. `Confirmed` / `No Material Regression` / `Inconclusive` / `Not Evaluated` come from `src/fts/verdict.py` and the KPI rules. The extension returns a side object. It has no function that writes a verdict, and `may_override_safety_verdict` is fixed to false.

The proposal mentions an example of about 25 questions and names such as Jev and Laya. The count, the wording, and those models are unconfirmed. This module uses eight illustrative questions so the pipeline can run with no network and no driving labels. Coefficients are fit on a fixed synthetic matrix (`random.Random(0)`). The holdout MAE on that matrix is a self-check of the linear algebra, not an accuracy on driving data. Do not quote it as a result.

## 흐름

```text
SIL log
  -> deterministic KPI          (collision, lane departure, min distance, reaction time)
  -> question scores in [0, 1]  (concern polarity, not a second pass/fail threshold)
  -> Ridge priority
  -> logistic review probability
  -> suggestion strings that are NOT follow-up tasks
```

판정 객체는 이 흐름에 들어가기 전에 이미 정해져 있습니다. `annotate()`는 판정 상태와 근거를 복사합니다. 패키지를 다시 봉인하지 않습니다. 데모는 suggestion 문자열이 패키지 JSON에 들어가지 않았는지 확인합니다.

Inconclusive에 실험을 더 제안하는 Follow-up Planner는, 제안서에서 확장 기능으로 적혀 있습니다. 이 모듈의 `suggest_followups()`는 문장만 돌려줍니다. 그 문장을 `Verdict.follow_up_tasks`에 넣는 코드 경로는 없습니다. 과제로 받아들이려면 사람 또는 `verdict.py`의 사전 규칙이 별도로 추가해야 합니다.

## 문항

코드의 질문 id와 한국어 프롬프트는 `src/fts/extension/questions.py`의 `QUESTIONS`입니다. 늦게 반응했는지, 차선을 이탈했는지, 조향이 진동했는지, 거리가 가까웠는지, 충돌했는지, 제동이 급했는지, 가림 이후가 늦었는지, 횡단 위치 전에 멈췄는지입니다. 일부 문항은 의도적으로 겹칩니다. 검증된 설문이라고 하지 않습니다.

진동 점수는 횡방향 부호 변화로 계산합니다. 이 가상 장면의 후보는 한쪽으로만 벗어나므로 진동 점수는 낮을 수 있습니다. 그것이 충돌 판정을 끄지는 않습니다.

## 회귀

- Ridge: `(X'X + λI)^{-1} X'y`, λ = 1. 합성 행 24개 중 16개로 맞추고 나머지 8개의 절대오차 평균을 `synthetic_holdout_mae`에 둡니다.
- Logistic: 같은 특징, 이진 라벨(합성 점수가 1.5 이상인지). 제안서대로 이진 검토 우선순위에는 logistic을 비교 모델로 둡니다.
- 라벨은 운전 데이터가 아닙니다. `trained_on` 필드는 `synthetic_stand_in_not_driving_labels`만 허용합니다.

## 실행

데모 맨 아래에 확장 출력이 붙습니다.

```bash
python -m fts demo
```

테스트 `tests/test_extension.py`는 같은 로그에 대해 점수가 결정론적인지, 호출 전후 판정 덤프가 같은지, override 플래그를 true로 만들 수 없는지 확인합니다.
