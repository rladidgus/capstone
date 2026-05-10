# ViewPoint 프로젝트 — Day 3 작업 정리

## 목표

Day 3의 핵심 목표는 백엔드 분석 파이프라인의 성능과 품질을 검증하고, 실제 서비스에 사용할 모델 전략을 결정하는 것이다.

진행한 작업은 크게 5가지다.

1. 생성 모델 벤치마크
2. quick mode 실행 시간 최적화
3. 리포트 품질 검수
4. 임베딩 모델 벤치마크
5. 다음 개발 우선순위 정리

---

## 1. 생성 모델 벤치마크

### 비교 대상

| 모델 | 역할 |
|------|------|
| `llama3.1:8b` | 현재 기본 생성 모델 |
| `mistral:7b` | 경량 생성 모델 후보 |
| `mistral-developer-analyzer:latest` | 분석 특화 생성 모델 후보 |

### 단일 프롬프트 벤치마크

비교 항목:

- planner quick
- reporter quick
- code generation

결과 요약:

| 기준 | 우세 모델 | 판단 |
|------|-----------|------|
| 단일 응답 속도 | `llama3.1:8b` | 세 작업 모두 가장 균형적 |
| JSON 안정성 | `llama3.1:8b`, `mistral:7b` | 필수 JSON 파싱 성공 |
| reporter 품질 | `llama3.1:8b` | 품질 5점, 속도도 가장 좋음 |
| code generation | `llama3.1:8b` | 완벽하진 않지만 상대적으로 안정적 |

### E2E 벤치마크

| 모델 | 모드 | 총 시간(초) | 완료 여부 | report_data | chart_data | 품질점수 | 메모 |
|------|------|-------------|-----------|-------------|------------|----------|------|
| `llama3.1:8b` | quick | 132.32 | ✅ | ✅ | ✅ | 5 | 최적화 전 |
| `llama3.1:8b` | quick_optimized | 49.81 | ✅ | ✅ | ✅ | 5 | quick graph 최적화 후 |
| `mistral:7b` | quick | 121.14 | ✅ | ✅ | ✅ | 4 | 속도는 빠르지만 품질 약점 |
| `mistral-developer-analyzer:latest` | quick | 106.61 | ✅ | ✅ | ✅ | 4 | quick에서 가장 빠르지만 일관성 이슈 |
| `llama3.1:8b` | deep | 149.75 | ✅ | ✅ | ✅ | 5 | 품질 기준 가장 안전 |
| `mistral:7b` | deep | 132.21 | ✅ | ✅ | ✅ | 4 | deep에서 가장 빠름 |
| `mistral-developer-analyzer:latest` | deep | 178.02 | ✅ | ✅ | ✅ | 4 | deep에서 가장 느림 |

### 생성 모델 결론

현재 운영 기본 생성 모델은 `llama3.1:8b`를 유지한다.

이유:

1. 단일 프롬프트 품질과 JSON 안정성이 가장 좋음
2. quick/deep E2E 모두 성공
3. 리포트 품질 기준에서 가장 안전함
4. quick graph 최적화 후 속도 문제도 크게 개선됨

---

## 2. quick mode 실행 시간 최적화

### 문제

최적화 전 quick mode도 여러 번 LLM을 호출했다.

기존 흐름:

1. planner에서 LLM 호출
2. code_interpreter에서 LLM 코드 생성
3. evaluator에서 LLM 호출
4. reporter에서 LLM 호출

quick mode의 목적은 빠른 요약인데, LLM 호출이 많아 전체 시간이 길어졌다.

### 수정 내용

| 파일 | 수정 내용 |
|------|-----------|
| `app/agent/planner.py` | quick mode에서 LLM 대신 규칙 기반 분석 계획 생성 |
| `app/tools/code_interpreter.py` | quick mode에서 LLM 코드 생성 생략, 규칙 기반 매출 요약 사용 |
| `app/agent/evaluator.py` | quick mode에서 LLM 충분성 평가 생략 |

### 최적화 결과

| 항목 | 시간 |
|------|------|
| 최적화 전 `llama3.1:8b` quick E2E | 132.32초 |
| 최적화 후 `llama3.1:8b` quick E2E | 49.81초 |
| 단축 시간 | 82.51초 |
| 감소율 | 약 62.4% |

핵심 원칙:

```text
계산은 코드가 하고, 설명은 LLM이 한다.
```

quick mode에서는 총매출, 일별 매출, 시간대별 매출, 인기 메뉴처럼 정해진 계산은 Python 코드가 처리하고, 마지막 리포트 설명만 LLM이 담당하도록 정리했다.

---

## 3. 리포트 품질 검수

### 검수 이유

E2E가 성공하더라도 실제 리포트 내용이 비어 있으면 서비스 품질은 실패다.

초기 검수에서 일부 리포트가 아래처럼 저장되는 문제가 발견되었다.

```text
summary: 분석이 완료되었습니다.
analysis_details: []
action_items: []
```

즉, `report_data` 객체는 존재해서 E2E는 통과했지만 실제 리포트 품질은 낮았다.

### 추가한 검수 스크립트

| 파일 | 역할 |
|------|------|
| `scripts/report_quality_review.py` | 최근 리포트의 품질 자동 검수 |
| `benchmark_artifacts/report_quality_review.csv` | 검수 결과 CSV |
| `benchmark_artifacts/report_quality_review.md` | 사람이 읽기 좋은 검수 결과 |

### 검수 기준

1. `summary`가 충분한 길이로 존재하는지
2. `analysis_details`에 요인, 영향, 설명이 포함되는지
3. `action_items`가 2개 이상이고 실행 가능한지
4. `chart_data`가 실제 숫자 시리즈를 포함하는지
5. 실패/빈 리포트가 저장되지 않는지

### 수정 내용

| 파일 | 수정 내용 |
|------|-----------|
| `app/agent/reporter.py` | LLM 리포트 생성 실패 시 내부 매출 요약 기반 fallback 리포트 생성 |

fallback 리포트 포함 내용:

- 총매출
- 일평균 매출
- 피크 시간대
- 상위 메뉴
- 통계 요약
- 실행방안 3개

### 최신 검수 결과

| 항목 | 결과 |
|------|------|
| 품질 점수 | 5/5 |
| chart_data | OK |
| analysis_details | 3개 |
| action_items | 3개 |
| issues | 없음 |

---

## 4. 임베딩 모델 벤치마크

### 비교 원칙

임베딩 모델은 생성 모델과 비교하지 않는다.

생성 모델은 보고서 작성/분석 문장 생성을 담당하고, 임베딩 모델은 메모/RAG 검색을 위해 텍스트를 벡터로 바꾸는 역할이다.
따라서 임베딩 품질은 임베딩 전용 모델끼리 비교했다.

### 비교 대상

| 모델 | 목적 |
|------|------|
| `embeddinggemma:latest` | 현재 기준 임베딩 모델 |
| `nomic-embed-text` | 가벼운 로컬 임베딩 후보 |
| `bge-m3` | 한국어/다국어 검색 품질 후보 |

### 비교 결과

| 모델 | dimension | 평균 시간 | Top-1 | Top-3 | MRR | Pinecone 호환 | 판단 |
|------|----------:|----------:|------:|------:|----:|---------------|------|
| `embeddinggemma:latest` | 768 | 0.148초 | 1.00 | 1.00 | 1.00 | 가능 | 유지 |
| `nomic-embed-text` | 768 | 0.070초 | 0.00 | 0.50 | 0.33 | 가능 | 제외 |
| `bge-m3` | 1024 | 0.225초 | 0.83 | 1.00 | 0.92 | 현재 index와 불일치 | 품질 후보 |

### 임베딩 모델 결론

현재 임베딩 모델은 `embeddinggemma:latest`를 유지한다.

이유:

1. 3개 후보 중 검색 품질이 가장 좋음
2. 현재 Pinecone index dimension 768과 일치
3. M1 Pro 16GB 환경에서 충분히 가볍게 운영 가능
4. `bge-m3`는 품질이 좋지만 1024차원이라 Pinecone index 재생성이 필요함

`bge-m3`는 추후 메모 검색 품질이 부족해질 때 1024차원 Pinecone index를 새로 만들고 재검토한다.

---

## 5. 최종 모델 전략

| 역할 | 최종 선택 | 이유 |
|------|-----------|------|
| 리포트 생성/분석 | `llama3.1:8b` | 품질, JSON 안정성, quick/deep E2E 안정성 |
| 메모 임베딩/RAG | `embeddinggemma:latest` | 검색 품질, Pinecone 768차원 호환성 |
| quick mode | `llama3.1:8b` + graph 최적화 | 49.81초까지 단축 |
| deep mode | `llama3.1:8b` 유지 | 품질 기준 가장 안전 |

발표용 결론:

```text
생성 모델은 llama3.1:8b를 유지하고, 임베딩 모델은 embeddinggemma:latest를 유지한다.
모델 교체보다 graph 최적화가 quick mode 성능 개선에 더 효과적이었다.
임베딩 모델은 bge-m3도 품질 후보였지만, 현재 Pinecone index와 dimension이 맞는 embeddinggemma가 운영상 가장 안전하다.
```

---

## 6. RAG E2E 및 deep mode 재검수

### RAG E2E 테스트

선택한 임베딩 모델 `embeddinggemma:latest`를 사용해 실제 메모/RAG 연결을 E2E로 검증했다.

검증 흐름:

1. 테스트 메모 생성
2. 메모 임베딩 생성
3. Pinecone upsert 확인
4. Pinecone 검색에서 관련 메모 조회 확인
5. 매출 CSV 업로드
6. deep mode 분석 실행
7. 최종 리포트에 RAG 메모 내용 반영 확인

최신 결과:

| 항목 | 결과 |
|------|------|
| embedding model | `embeddinggemma:latest` |
| generation model | `llama3.1:8b` |
| mode | `deep` |
| 실행 시간 | 148.70초 |
| Pinecone 검색 | 성공 |
| report_data | 생성됨 |
| chart_data | 생성됨 |
| RAG 반영 | 성공 |
| 최종 상태 | `RAG_E2E_OK` |

### RAG 중복 제거 보강

반복 테스트 과정에서 같은 내용의 테스트 메모가 여러 번 저장되면 리포트의 `경영 메모` 항목에 같은 문장이 중복 표시되는 문제가 있었다.

수정 내용:

| 파일 | 수정 내용 |
|------|-----------|
| `app/tools/rag_retriever.py` | Pinecone 검색 결과를 메모 본문 기준으로 중복 제거 |
| `app/agent/reporter.py` | fallback 리포트 문구가 현재 mode를 반영하도록 수정 |
| `scripts/report_quality_review.py` | `--mode`, `--query-contains`, `--prefix` 옵션 추가 |

### deep mode 최신 리포트 품질 재검수

최신 deep mode 리포트만 다시 검수했다.

| 항목 | 결과 |
|------|------|
| report_id | `1a61a607-a320-4b4c-bf3b-e64712ba29a7` |
| 품질 점수 | 5/5 |
| chart_data | OK |
| analysis_details | 4개 |
| action_items | 3개 |
| issues | 없음 |

결론:

```text
선택한 모델 조합(llama3.1:8b + embeddinggemma:latest)은 deep mode에서도 메모/RAG 검색과 리포트 반영이 정상 동작한다.
최신 리포트 품질 검수 결과도 5/5로 통과했으므로, 다음 단계는 프론트엔드 MVP 구현 또는 테스트 자동화로 넘어갈 수 있다.
```

---

## 7. 생성된 산출물

### 모델 벤치마크

| 파일 | 설명 |
|------|------|
| `benchmark.md` | 생성 모델 벤치마크 및 최종 전략 |
| `benchmark_artifacts/benchmark_summary.csv` | 단일 프롬프트 벤치마크 요약 |
| `benchmark_artifacts/benchmark_e2e_summary.csv` | E2E 벤치마크 요약 |
| `benchmark_artifacts/benchmark_e2e_time.png` | PPT용 E2E 시간 비교 그래프 |
| `benchmark_artifacts/benchmark_e2e_quality.png` | PPT용 E2E 품질 비교 그래프 |

### 리포트 품질 검수

| 파일 | 설명 |
|------|------|
| `scripts/report_quality_review.py` | 리포트 품질 검수 스크립트 |
| `benchmark_artifacts/report_quality_review.csv` | 리포트 품질 검수 결과 |
| `benchmark_artifacts/report_quality_review.md` | 리포트 품질 검수 상세 |
| `benchmark_artifacts/report_quality_review_deep_latest.csv` | 최신 deep mode 리포트 품질 검수 결과 |
| `benchmark_artifacts/report_quality_review_deep_latest.md` | 최신 deep mode 리포트 품질 검수 상세 |

### 임베딩 벤치마크

| 파일 | 설명 |
|------|------|
| `embedding_benchmark.md` | 임베딩 모델 비교 계획 및 결론 |
| `scripts/embedding_benchmark.py` | 임베딩 품질 테스트 스크립트 |
| `benchmark_artifacts/embedding_benchmark_summary.csv` | 임베딩 모델 요약 |
| `benchmark_artifacts/embedding_benchmark_details.csv` | 질의별 검색 결과 |
| `benchmark_artifacts/embedding_benchmark_results.md` | 사람이 읽기 좋은 임베딩 결과 |

---

## 8. 다음 작업

### 1순위 — 프론트엔드 MVP 구현

필수 화면:

1. 파일 업로드
2. 분석 요청
3. 리포트 조회
4. 차트 시각화
5. 메모 입력/조회

### 2순위 — 테스트 자동화

현재는 검증 스크립트 중심이다.
다음 단계에서는 `pytest` 기반 회귀 테스트로 편입하는 것이 좋다.

대상:

- `scripts/e2e_analysis_test.py`
- `scripts/code_interpreter_validation.py`
- `scripts/api_connector_validation.py`
- `scripts/report_quality_review.py`
- `scripts/embedding_benchmark.py`
- `scripts/rag_e2e_test.py`
