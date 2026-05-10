# ViewPoint 임베딩 모델 벤치마크

## 목적

임베딩 모델은 리포트 생성 모델과 비교하지 않는다.

생성 모델(`llama3.1:8b`, `mistral:7b`, `mistral-developer-analyzer:latest`)은 보고서 작성과 분석 문장 생성을 위한 모델이고, 임베딩 모델은 메모/RAG 검색을 위해 텍스트를 벡터로 바꾸는 모델이다.
따라서 임베딩 품질은 임베딩 전용 모델끼리 비교해야 한다.

이 문서는 MacBook M1 Pro, RAM 16GB, SSD 512GB 환경에서 ViewPoint 메모/RAG에 적합한 임베딩 모델 후보를 정리하고, 이후 실제 비교 테스트를 진행하기 위한 기준이다.

## 현재 상태

| 항목 | 현재 값 |
|------|---------|
| 사용 중 임베딩 모델 | `embeddinggemma:latest` |
| Pinecone index dimension | 768 |
| 사용 목적 | 경영 메모 임베딩, RAG 검색 |
| 현재 판단 | 유지 가능, 추가 임베딩 모델과 비교 필요 |

기존에 생성 모델과 함께 임베딩 엔드포인트를 호출한 결과는 정식 임베딩 모델 비교로 보지 않는다.
해당 테스트는 생성 모델을 임베딩 용도로 쓰는 것이 적절하지 않다는 호환성 확인에 가까웠으므로, 최종 임베딩 벤치마크 결과에서는 제외한다.

## M1 Pro 16GB 기준 비교 후보

생성 모델을 3개 비교한 것처럼 임베딩도 3개 후보로 맞춘다.
이번 비교 후보는 현재 사용 모델 1개, 가벼운 후보 1개, 한국어/다국어 품질 후보 1개로 구성한다.

### 1. `embeddinggemma:latest`

현재 기준 모델.

장점:

- 이미 설치되어 있고 동작 확인됨
- 현재 Pinecone index dimension 768과 맞음
- 메모 생성/검색용으로 가볍게 운영 가능
- M1 Pro 16GB 환경에서 부담이 작음

단점:

- 다른 임베딩 전용 모델과의 실제 품질 비교는 아직 부족함

역할:

- 현재 프로젝트 기본 임베딩 모델
- 비교 기준선

### 2. `nomic-embed-text`

가벼운 로컬 임베딩 후보.

장점:

- Ollama에서 임베딩 전용 모델로 제공됨
- 모델 크기가 작아 M1 Pro 16GB 환경에서 부담이 적음
- 설치/테스트 비용이 낮아 비교 후보로 적합

단점:

- 한국어 경영 메모 검색 품질은 직접 테스트 필요
- Pinecone dimension이 현재 index와 다를 수 있으므로 설치 후 확인 필요

역할:

- 속도와 가벼움 기준 비교 후보

설치 후보:

```bash
ollama pull nomic-embed-text
```

### 3. `bge-m3`

한국어/다국어 의미 검색 품질 후보.

장점:

- 다국어 검색에 강한 계열
- 한국어 메모 검색 품질 비교 대상으로 의미 있음
- 긴 문서 검색까지 고려할 때 후보가 될 수 있음

단점:

- `embeddinggemma`, `nomic-embed-text`보다 무거울 수 있음
- M1 Pro 16GB에서 동작은 가능해도 대량 메모 처리 시 속도 확인 필요
- Pinecone dimension 확인 후 index 재설계가 필요할 수 있음

역할:

- 한국어 검색 품질 기준 비교 후보

설치 후보:

```bash
ollama pull bge-m3
```

## 추천 비교 순서

M1 Pro 16GB, SSD 512GB 환경에서는 아래 3개만 비교한다.

1. `embeddinggemma:latest` 기준 성능 재측정
2. `nomic-embed-text` 설치 후 속도/품질 비교
3. `bge-m3` 설치 후 한국어 검색 품질 비교
4. 가장 좋은 모델의 dimension에 맞춰 Pinecone index 유지 또는 재생성 결정

## 비교 기준

| 기준 | 설명 |
|------|------|
| dimension | Pinecone index dimension과 맞는지 |
| 평균 임베딩 시간 | 메모 저장/검색 속도 |
| Top-1 Accuracy | 가장 관련 있는 메모를 1위로 찾는지 |
| Top-3 Accuracy | 관련 메모가 상위 3개 안에 있는지 |
| MRR | 정답 메모가 얼마나 높은 순위에 나오는지 |
| 한국어 의미 검색 | 표현이 달라도 같은 의미를 잘 찾는지 |
| 저장 공간 | SSD 512GB 환경에서 부담이 적은지 |

## 실행 명령

현재 모델만 테스트:

```bash
conda run -n capstone python scripts/embedding_benchmark.py --models embeddinggemma:latest
```

임베딩 전용 후보 비교:

```bash
conda run -n capstone python scripts/embedding_benchmark.py \
  --models embeddinggemma:latest nomic-embed-text bge-m3
```

주의:

- 비교 전에 해당 모델을 `ollama pull`로 설치해야 한다.
- 새 모델의 embedding dimension이 현재 Pinecone index와 다르면 기존 index에 바로 upsert할 수 없다.
- dimension이 다르면 테스트는 로컬 코사인 유사도 기준으로 먼저 진행하고, 최종 선택 후 Pinecone index를 새로 만들지 결정한다.

## 현재 결론

### 3개 임베딩 후보 테스트 결과

`nomic-embed-text`와 `bge-m3`를 설치한 뒤 `embeddinggemma:latest`와 같은 데이터셋으로 비교했다.
`nomic-embed-text`는 검색용 권장 prefix인 `search_document:`, `search_query:`를 적용해 다시 측정했다.

| 모델 | dimension | 평균 임베딩 시간 | Top-1 | Top-3 | MRR | Pinecone 호환 | 판단 |
|------|----------:|----------------:|------:|------:|----:|---------------|------|
| `embeddinggemma:latest` | 768 | 0.148초 | 1.00 | 1.00 | 1.00 | 가능 | 유지 |
| `nomic-embed-text` | 768 | 0.070초 | 0.00 | 0.50 | 0.33 | 가능 | 제외 |
| `bge-m3` | 1024 | 0.225초 | 0.83 | 1.00 | 0.92 | 현재 index와 불일치 | 품질 후보 |

해석:

- `nomic-embed-text`는 속도는 더 빠름
- dimension은 768로 현재 Pinecone index와 호환 가능
- 하지만 한국어 경영 메모 검색에서 기대 메모를 1위로 찾지 못함
- Top-3도 0.50으로 낮아 현재 서비스 기본 임베딩 모델로는 부적합
- `bge-m3`는 검색 품질이 좋고 Top-3는 1.00이지만, dimension이 1024라 현재 Pinecone index 768과 맞지 않음
- `bge-m3`를 적용하려면 1024차원 Pinecone index를 새로 만들고 기존 메모를 재임베딩해야 함

### 현재 결론

현재 시점에서는 `embeddinggemma:latest`를 유지한다.

이유:

1. 이미 설치되어 있음
2. 현재 Pinecone index dimension 768과 맞음
3. 3개 후보 중 한국어 경영 메모 검색 점수가 가장 높음
4. M1 Pro 16GB 환경에서 충분히 가볍게 운영 가능
5. 메모/RAG 기능 안정화 단계에서는 `embeddinggemma:latest` 유지가 안전

`bge-m3`는 품질 후보로 남겨둘 수 있지만, 현재 프로젝트에서는 Pinecone index dimension 변경 비용이 있다.
따라서 당장은 `embeddinggemma:latest`를 유지하고, 추후 메모 검색 품질이 부족해질 때 `bge-m3`용 1024차원 index를 별도로 만들어 재검토한다.
