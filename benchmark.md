# ViewPoint 모델 벤치마크 계획

## 목적

현재 기본 생성 모델은 `llama3.1:8b`이다.  
하지만 quick/deep 분석에서 실제로 가장 적합한 모델인지 아직 비교 근거가 없다.

이 문서는 Ollama 로컬 모델들을 같은 조건에서 비교하여 다음 결정을 내리기 위한 기준이다.

1. quick mode 기본 모델
2. deep mode 기본 모델
3. 임베딩/RAG 전용 모델
4. 모델 교체보다 코드 최적화가 우선인지 여부

---

## 비교 대상

### 생성 모델

| 모델 | 비교 목적 |
|------|-----------|
| `llama3.1:8b` | 현재 기준 모델. 한국어 리포트 품질과 안정성 확인 |
| `mistral:7b` | 속도, 간결한 응답, JSON 생성 안정성 비교 |
| `mistral-developer-analyzer:latest` | 분석/추론 품질, 상세 리포트 품질 비교 |

### 임베딩 모델

| 모델 | 비교 목적 |
|------|-----------|
| `embeddinggemma:latest` | 메모 임베딩/RAG 전용 모델. 생성 모델 비교 대상에서는 제외 |

`embeddinggemma:latest`는 리포트 생성 모델이 아니라 벡터 생성용이다.  
따라서 planner/reporter/code generation 품질 비교에는 포함하지 않는다.

---

## 평가 기준

### 1. 속도

측정 항목:

- planner 응답 시간
- reporter 응답 시간
- code generation 응답 시간
- 전체 E2E 실행 시간

기록 방식:

```text
model:
task:
elapsed_seconds:
```

### 2. JSON 안정성

planner/reporter는 JSON 형식이 깨지면 전체 분석이 흔들린다.

확인 항목:

- JSON 파싱 성공 여부
- 필수 키 존재 여부
- 불필요한 마크다운 코드블록 포함 여부
- 한국어 설명 중 JSON 외부 텍스트가 섞이는지 여부

필수 키:

planner:

```json
{
  "hypotheses": [],
  "analysis_plan": []
}
```

reporter:

```json
{
  "summary": "",
  "analysis_details": [],
  "action_items": [],
  "chart_data": {}
}
```

### 3. 한국어 리포트 품질

확인 항목:

- 문장이 자연스러운가
- 소상공인 관점에서 이해하기 쉬운가
- 원인 분석이 데이터와 연결되는가
- 실행 방안이 구체적인가
- 과장된 결론이나 꾸며낸 수치가 없는가

점수:

```text
1점: 사용하기 어려움
2점: 일부 수정 필요
3점: 기본 사용 가능
4점: 품질 좋음
5점: 바로 사용 가능
```

### 4. Code Interpreter 코드 품질

확인 항목:

- Pandas 코드가 실행 가능한가
- `result` dict를 생성하는가
- 마크다운 코드블록 없이 코드만 출력하는가
- 금지된 import를 시도하지 않는가
- 표준 컬럼(`sold_at`, `amount`, `quantity`, `menu`, `category`)을 잘 사용하는가

현재 Code Interpreter에는 규칙 기반 fallback이 있으므로, 모델 비교에서는 “실패해도 전체 분석이 되는가”보다 “LLM 코드 자체가 쓸 만한가”를 본다.

### 5. E2E 안정성

최종 후보 모델은 전체 분석을 한 번 이상 실행한다.

확인 항목:

- `/analysis/analyze` 흐름이 끝까지 완료되는가
- Report status가 `completed`가 되는가
- `report_data`가 저장되는가
- `chart_data`가 저장되는가
- confidence level이 적절히 계산되는가

---

## quick/deep 가중치

### quick mode

quick mode는 빠른 브리핑이 목적이다.

| 항목 | 비중 |
|------|------|
| 속도 | 50% |
| JSON 안정성 | 30% |
| 리포트 품질 | 20% |

권장 방향:

- LLM 호출 횟수를 줄이는 것이 중요
- planner/evaluator는 규칙 기반으로 대체 가능
- reporter 1회 호출 품질이 가장 중요

### deep mode

deep mode는 상세 분석 품질이 목적이다.

| 항목 | 비중 |
|------|------|
| 리포트 품질 | 50% |
| JSON 안정성 | 30% |
| 속도 | 20% |

권장 방향:

- planner/reporter의 분석 품질을 우선
- evaluator 반복은 유지 가능
- 실행 시간이 조금 길어도 품질이 좋으면 허용

---

## 진행 순서

### 1단계 — Ollama 모델 상태 확인

명령어:

```bash
ollama list
curl http://localhost:11434/api/tags
```

확인할 것:

- 비교 대상 모델이 모두 설치되어 있는지
- `embeddinggemma:latest`는 임베딩 모델로만 분리되어 있는지

---

### 2단계 — 단일 프롬프트 벤치마크

전체 E2E는 오래 걸리므로 먼저 작은 프롬프트로 비교한다.

테스트 대상:

1. planner prompt
2. reporter quick prompt
3. reporter deep prompt
4. code generation prompt

기록할 것:

- 응답 시간
- JSON 파싱 성공 여부
- 필수 키 존재 여부
- 응답 품질 점수

---

### 3단계 — Code Interpreter 코드 생성 비교

같은 컬럼 정보를 주고 Pandas 코드를 생성하게 한다.

샘플 컬럼:

```text
sold_at: datetime64
amount: float64
quantity: int64
menu: object
category: object
```

평가:

- 코드 실행 성공
- `result` 생성
- `time_series`, `top_menus`, `hourly_sales` 포함 여부

---

### 4단계 — Reporter 품질 비교

같은 `internal_data`, `external_data`, `statistical_summary`를 넣고 리포트를 생성한다.

평가:

- summary 품질
- analysis_details 품질
- action_items 구체성
- chart_data 유효성
- 허위 수치 생성 여부

---

### 5단계 — 최종 후보 E2E 실행

단일 프롬프트 비교 후 후보 1~2개만 전체 E2E를 실행한다.

명령어 예시:

```bash
OLLAMA_MODEL=llama3.1:8b conda run -n capstone python scripts/e2e_analysis_test.py --mode quick
OLLAMA_MODEL=mistral:7b conda run -n capstone python scripts/e2e_analysis_test.py --mode quick
```

확인할 것:

- `E2E_OK`
- 총 실행 시간
- `has_report_data=True`
- `has_chart_data=True`
- 리포트 내용 품질

---

## 결과 기록 양식

### 단일 프롬프트 결과

| 모델 | 작업 | 시간(초) | JSON 성공 | 필수 키 | 품질점수 | 메모 |
|------|------|----------|-----------|---------|----------|------|
| `llama3.1:8b` | planner quick | 10.54 | ✅ | ✅ | 4 | JSON 안정적, 가설/계획 품질은 기본 이상 |
| `mistral:7b` | planner quick | 13.65 | ✅ | ✅ | 4 | JSON 안정적이나 `llama3.1:8b`보다 느림 |
| `mistral-developer-analyzer:latest` | planner quick | 19.79 | ✅ | ✅ | 4 | JSON 추출은 가능하지만 JSON 외부 설명 텍스트가 섞임 |
| `llama3.1:8b` | reporter quick | 14.05 | ✅ | ✅ | 5 | 한국어 요약과 실행방안 품질 좋음, chart_data 포함 |
| `mistral:7b` | reporter quick | 23.63 | ✅ | ✅ | 5 | 품질은 좋지만 reporter에서 `llama3.1:8b`보다 크게 느림 |
| `mistral-developer-analyzer:latest` | reporter quick | 23.87 | ✅ | ✅ | 5 | 품질은 괜찮지만 날씨 해석 일부 모순, 속도는 느림 |
| `llama3.1:8b` | code generation | 16.09 | N/A | N/A | 4 | `result` 생성은 가능하나 마크다운 코드블록과 예시 DataFrame 생성이 섞여 감점 |
| `mistral:7b` | code generation | 17.09 | N/A | N/A | 4 | 마크다운 코드블록 포함, `pd.read_csv('sales_data.csv')`처럼 외부 파일 가정이 섞임 |
| `mistral-developer-analyzer:latest` | code generation | 21.79 | N/A | N/A | 3 | 외부 CSV 파일 가정, 컬럼명 오타(`sol_at`) 등으로 안정성 낮음 |

### `llama3.1:8b` 1차 관찰

- JSON 생성 안정성은 좋음
- reporter quick 품질은 현재 기준으로 사용 가능
- code generation은 지시를 완전히 따르지 못함
  - 마크다운 코드블록 포함
  - 기존 `df`를 분석하기보다 예시 DataFrame을 새로 만드는 경향 확인
- 단일 프롬프트 기준으로도 10~16초가 걸리므로 quick mode에서 LLM 호출 횟수 축소가 중요함
- 현재 구조대로 planner + code_interpreter + evaluator + reporter를 모두 호출하면 모델 교체 없이도 응답 시간이 길어질 가능성이 큼

### `mistral:7b` 1차 관찰

- JSON 생성은 planner/reporter 모두 성공
- reporter quick 품질은 점수상 좋지만 `llama3.1:8b`보다 약 9.6초 느림
- planner/code generation도 `llama3.1:8b`보다 빠르지 않음
- code generation은 지시와 다르게 외부 CSV 파일명(`sales_data.csv`)을 가정하는 코드가 섞여 안정성이 낮음
- 현재 측정 기준으로는 quick mode 속도 개선 후보로 보기 어려움

### `mistral-developer-analyzer:latest` 1차 관찰

- planner/reporter 모두 JSON 추출은 가능했지만 planner 응답에는 JSON 외부 설명 텍스트가 섞임
- reporter quick 품질 점수는 5점이나, "비 오는 날"과 "비가 오지 않아"가 함께 나오는 등 설명 일부가 모순됨
- 세 작업 모두 `llama3.1:8b`보다 느림
- code generation은 `sol_at` 오타와 외부 CSV 파일 가정이 있어 가장 낮은 점수
- 이름은 분석 특화처럼 보이지만 현재 프롬프트 기준 quick/deep 기본 후보로 삼기에는 속도와 안정성이 아쉬움

### 단일 프롬프트 1차 결론

현재 측정에서는 `llama3.1:8b`가 세 생성 모델 중 가장 균형이 좋다.

| 기준 | 우세 모델 | 이유 |
|------|-----------|------|
| 속도 | `llama3.1:8b` | 세 작업 모두 가장 빠름 |
| JSON 안정성 | `llama3.1:8b`, `mistral:7b` | 둘 다 필수 JSON 성공 |
| reporter 품질 | `llama3.1:8b` | 품질 5점이면서 가장 빠름 |
| code generation | `llama3.1:8b` | 완벽하지는 않지만 상대적으로 가장 나음 |

따라서 다음 단계는 모델 교체보다 quick mode graph 최적화가 더 효과적일 가능성이 높다.

### E2E 결과

| 모델 | 모드 | 총 시간(초) | 완료 여부 | report_data | chart_data | 품질점수 | 메모 |
|------|------|-------------|-----------|-------------|------------|----------|------|
| `llama3.1:8b` | quick | 132.32 | ✅ | ✅ | ✅ | 5 | E2E_OK, confidence_level=high, 전체 흐름 완료 |
| `llama3.1:8b` | quick_optimized | 49.81 | ✅ | ✅ | ✅ | 5 | E2E_OK, planner/evaluator/code generation LLM 호출 축소 후 재측정 |
| `mistral:7b` | quick | 121.14 | ✅ | ✅ | ✅ | 4 | E2E_OK, confidence_level=high, 전체 시간은 더 짧지만 단일 reporter 품질/속도는 llama 대비 약점 |
| `mistral-developer-analyzer:latest` | quick | 106.61 | ✅ | ✅ | ✅ | 4 | E2E_OK, confidence_level=high, 총 시간은 가장 짧지만 단일 응답 품질/일관성 이슈 있음 |
| `llama3.1:8b` | deep | 149.75 | ✅ | ✅ | ✅ | 5 | E2E_OK, confidence_level=high, quick 대비 약 17.43초 증가 |
| `mistral:7b` | deep | 132.21 | ✅ | ✅ | ✅ | 4 | E2E_OK, confidence_level=high, llama deep 대비 약 17.54초 빠름 |
| `mistral-developer-analyzer:latest` | deep | 178.02 | ✅ | ✅ | ✅ | 4 | E2E_OK, confidence_level=high, deep에서는 세 모델 중 가장 느림 |

### `llama3.1:8b` E2E 관찰

- quick mode 전체 E2E는 성공
- 총 실행 시간은 132.32초
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- 단일 프롬프트 결과와 마찬가지로 품질/안정성은 좋지만, quick mode로 보기에는 실행 시간이 길다
- 다음 최적화에서는 모델 교체보다 quick graph의 LLM 호출 횟수 축소가 우선

#### deep mode

- deep mode 전체 E2E도 성공
- 총 실행 시간은 149.75초
- quick mode 대비 약 17.43초 증가
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- `llama3.1:8b`는 deep에서도 안정적으로 완료되므로 품질 기준 모델로 유지할 수 있음

#### quick mode 최적화 후

- quick mode graph 최적화 후 전체 E2E도 성공
- 총 실행 시간은 49.81초
- 기존 quick 132.32초 대비 약 82.51초 단축
- 실행 시간은 약 62.4% 감소
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- 최적화 내용은 quick에서 planner/evaluator/code generation LLM 호출을 줄이고 rule-based summary를 우선 사용한 것

### `mistral:7b` E2E 관찰

- quick mode 전체 E2E는 성공
- 총 실행 시간은 121.14초로 `llama3.1:8b` E2E보다 약 11.18초 빠름
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- 단일 프롬프트에서는 `llama3.1:8b`보다 느렸지만, E2E 총 시간은 더 짧게 측정됨
- 단일 reporter/code generation 품질 이슈를 고려하면 기본 모델 교체는 추가 반복 측정 후 결정하는 것이 안전

#### deep mode

- deep mode 전체 E2E도 성공
- 총 실행 시간은 132.21초
- `llama3.1:8b` deep 대비 약 17.54초 빠름
- quick mode 대비 약 11.07초 증가
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- 속도만 보면 deep에서도 유리하지만, 단일 프롬프트 품질 이슈가 있었으므로 최종 선택 전 리포트 내용 검수가 필요

### `mistral-developer-analyzer:latest` E2E 관찰

- quick mode 전체 E2E는 성공
- 총 실행 시간은 106.61초로 세 모델 중 가장 짧음
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- 단일 프롬프트에서는 가장 느렸지만 전체 E2E에서는 가장 빠르게 측정됨
- 다만 단일 테스트에서 JSON 외부 설명, 날씨 해석 모순, code generation 컬럼 오타가 있었으므로 품질 안정성은 추가 확인 필요

#### deep mode

- deep mode 전체 E2E도 성공
- 총 실행 시간은 178.02초
- quick mode 대비 약 71.41초 증가
- `llama3.1:8b` deep 대비 약 28.27초 느림
- `mistral:7b` deep 대비 약 45.81초 느림
- `report_data`, `chart_data` 모두 저장됨
- `confidence_level=high`
- quick에서는 가장 빨랐지만 deep에서는 가장 느리므로 deep 기본 모델 후보로는 우선순위가 낮아짐

### quick E2E 1차 결론

| 기준 | 우세 모델 | 이유 |
|------|-----------|------|
| E2E 총 시간 | `mistral-developer-analyzer:latest` | 106.61초로 가장 빠름 |
| 단일 reporter 품질/속도 | `llama3.1:8b` | 14.05초, 품질 5점 |
| 전체 안정성 | 세 모델 모두 통과 | quick E2E 기준 모두 `E2E_OK` |

현재 결과만 보면 E2E 속도는 `mistral-developer-analyzer:latest`가 가장 좋지만, 단일 프롬프트 품질과 일관성은 `llama3.1:8b`가 가장 안정적이다.
따라서 바로 모델을 교체하기보다는 각 모델별 quick E2E를 2~3회 반복해 평균 시간을 비교하고, 최종 리포트 품질을 사람이 확인한 뒤 결정하는 것이 안전하다.

### deep E2E 1차 결론

| 기준 | 우세 모델 | 이유 |
|------|-----------|------|
| E2E 총 시간 | `mistral:7b` | 132.21초로 가장 빠름 |
| 품질 기준 | `llama3.1:8b` | 단일 프롬프트와 E2E 모두 안정적이며 품질점수 5 |
| deep 부적합 후보 | `mistral-developer-analyzer:latest` | 178.02초로 가장 느리고 단일 프롬프트 품질 이슈가 있음 |

deep mode는 속도만 보면 `mistral:7b`가 가장 유리하고, 안정성과 품질 기준으로 보면 `llama3.1:8b`가 더 안전하다.
따라서 deep 기본 모델은 `llama3.1:8b`를 유지하되, 리포트 품질 검수에서 `mistral:7b`가 충분히 좋다면 deep 전용 경량 모델 후보로 검토할 수 있다.

### 발표용 시각화 자료

생성 위치: `benchmark_artifacts/`

| 파일 | 용도 |
|------|------|
| `benchmark_summary.csv` | 단일 프롬프트 벤치마크 원본 요약 |
| `benchmark_response_time.png` | 단일 프롬프트 응답 시간 비교 그래프 |
| `benchmark_quality_score.png` | 단일 프롬프트 품질 점수 비교 그래프 |
| `benchmark_e2e_summary.csv` | quick/deep E2E 벤치마크 원본 요약 |
| `benchmark_e2e_time.png` | quick/deep E2E 실행 시간 비교 그래프 |
| `benchmark_e2e_quality.png` | quick/deep E2E 품질 점수 비교 그래프 |

PPT에는 `benchmark_e2e_time.png`와 `benchmark_e2e_quality.png`를 우선 사용하고, 보조 근거로 단일 프롬프트 그래프를 추가하면 된다.

---

## 최종 모델 전략

### 1차 운영 결론

현재 단계에서는 기본 모델을 바로 교체하지 않고 `llama3.1:8b`를 유지한다.

이유:

1. 단일 프롬프트 벤치마크에서 reporter 품질 점수가 가장 높음
2. quick/deep E2E 모두 성공
3. JSON 생성 안정성과 리포트 일관성이 가장 좋음
4. 속도는 가장 빠르지 않지만 품질 기준 모델로 쓰기에 안전함

### 모드별 후보

| 용도 | 1차 추천 | 대안 | 판단 |
|------|----------|------|------|
| quick mode | `llama3.1:8b` 유지 | `mistral-developer-analyzer:latest` | developer-analyzer가 106.61초로 가장 빠르지만 단일 프롬프트 품질 이슈가 있어 즉시 교체는 보류 |
| deep mode | `llama3.1:8b` 유지 | `mistral:7b` | mistral이 132.21초로 가장 빠르지만 최종 리포트 품질 검수 후 전환 판단 |
| embedding | `embeddinggemma:latest` 유지 | `nomic-embed-text` | 생성 모델과 비교하지 않고 임베딩 전용 모델끼리 별도 비교 예정 |

### 모델별 역할 판단

| 모델 | 강점 | 약점 | 전략 |
|------|------|------|------|
| `llama3.1:8b` | 리포트 품질, JSON 안정성, quick/deep 모두 안정 통과 | 실행 시간이 상대적으로 김 | 기본 모델 유지 |
| `mistral:7b` | deep E2E에서 가장 빠름 | 단일 reporter/code generation 품질이 llama보다 약함 | deep 경량 후보로 보류 |
| `mistral-developer-analyzer:latest` | quick E2E에서 가장 빠름 | deep에서 가장 느리고 단일 프롬프트 일관성 이슈 있음 | quick 실험 후보, deep 후보 제외 |
| `embeddinggemma:latest` | Pinecone dimension 768과 일치, 현재 메모/RAG에서 동작 확인 | 다른 임베딩 전용 모델과 정식 비교는 아직 필요 | 메모/Pinecone 임베딩 전용 유지 |

임베딩 모델 추천과 향후 비교 계획은 `embedding_benchmark.md`에 별도로 정리했다.

### 발표용 결론 문장

```text
벤치마크 결과, E2E 속도만 보면 quick mode에서는 mistral-developer-analyzer,
deep mode에서는 mistral:7b가 유리했다.
하지만 리포트 품질, JSON 안정성, 전체 분석 일관성을 함께 고려하면
현재 운영 기본 모델은 llama3.1:8b를 유지하는 것이 가장 안전하다.
이후 최적화는 모델 교체보다 graph 단계의 LLM 호출 횟수 축소를 우선한다.
```

### 다음 최적화 방향

1. `llama3.1:8b`를 기본 모델로 유지
2. quick mode에서 planner/evaluator 호출을 줄이는 graph 최적화 진행
3. rule-based 분석 결과로 대체 가능한 단계는 LLM 호출 생략
4. 최적화 후 동일 E2E 벤치마크 재측정
5. 그래도 속도 개선이 부족하면 quick/deep 모델 분리 적용

### 모델 분리 적용 조건

아래 조건을 만족하면 모드별 모델 분리를 검토한다.

| 조건 | 적용 후보 |
|------|-----------|
| quick mode 평균 시간이 `llama3.1:8b`보다 20% 이상 빠르고 리포트 품질 문제가 없을 때 | `mistral-developer-analyzer:latest` |
| deep mode 평균 시간이 `llama3.1:8b`보다 15% 이상 빠르고 최종 리포트 품질이 충분할 때 | `mistral:7b` |
| JSON 파싱 실패 또는 리포트 내용 모순이 반복될 때 | 후보 제외 |

### 리포트 품질 검수 결과

검수 파일:

- `benchmark_artifacts/report_quality_review.csv`
- `benchmark_artifacts/report_quality_review.md`

검수 기준:

1. `summary`가 충분한 길이로 존재하는지
2. `analysis_details`에 요인, 영향, 설명이 포함되는지
3. `action_items`가 2개 이상이고 실행 가능한지
4. `chart_data`가 실제 숫자 시리즈를 포함하는지
5. JSON 실패나 비어 있는 리포트가 저장되지 않는지

초기 검수에서는 일부 E2E 리포트가 `E2E_OK`임에도 `summary="분석이 완료되었습니다."`, `analysis_details=[]`, `action_items=[]`로 저장되는 문제가 확인되었다.
이는 리포트 JSON 생성이 실패했을 때도 `report_data` 객체 자체는 존재해 E2E가 통과했기 때문이다.

보강 내용:

- reporter에서 LLM JSON 결과가 비어 있거나 형식이 부족하면 내부 매출 요약 기반 fallback 리포트를 생성
- fallback 리포트는 총매출, 일평균 매출, 피크 시간대, 상위 메뉴, 통계 요약, 실행방안을 포함
- quick mode 최적화 후 최신 리포트 `ca6a4d6a-0717-46fb-b8b6-765dde91555c`는 품질 검수 `5/5`, chart `OK`, issues `없음`

최신 quick 리포트 품질:

| 항목 | 결과 |
|------|------|
| 품질 점수 | 5/5 |
| chart_data | OK |
| analysis_details | 3개 |
| action_items | 3개 |
| issues | 없음 |

---

## 판단 기준

### quick mode 기본 모델 후보

우선순위:

1. JSON 성공률이 높음
2. reporter quick 응답이 빠름
3. 실행 방안이 충분히 구체적임

추천 기준:

```text
JSON 실패가 1회라도 반복되면 quick 기본 모델 후보에서 제외
속도가 2배 이상 느리면 품질이 확실히 좋을 때만 유지
```

### deep mode 기본 모델 후보

우선순위:

1. 리포트 품질이 높음
2. 데이터 기반 설명이 자연스러움
3. 허위 수치를 만들지 않음
4. JSON이 안정적임

추천 기준:

```text
품질 점수가 4점 이상이면 deep 후보
JSON 안정성이 낮으면 deep에서도 제외
```

---

## 벤치마크 후 다음 작업

1. deep mode 최신 리포트 품질 샘플 재검수
2. quick mode graph 최적화 결과를 기준으로 평균 E2E 시간 재측정
   - planner 규칙 기반 대체
   - evaluator 생략
   - reporter 1회 호출
3. 동일 조건으로 quick E2E 2~3회 추가 반복 측정
4. 속도 개선이 부족하면 `.env` 또는 설정 파일에 모델 분리
   - 예: `OLLAMA_QUICK_MODEL`
   - 예: `OLLAMA_DEEP_MODEL`
   - 예: `OLLAMA_EMBED_MODEL`
5. 모델 분리를 적용할 경우 `LLMService`에서 작업별 모델 선택 지원
