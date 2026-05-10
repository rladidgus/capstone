# 임베딩 모델 품질 테스트 결과

nomic-embed-text는 검색용 권장 prefix(`search_document:`, `search_query:`)를 적용해 측정했다.

## 요약

| model | dimension | avg latency | top1 | top3 | MRR |
|---|---:|---:|---:|---:|---:|
| `embeddinggemma:latest` | 768 | 0.148s | 1.00 | 1.00 | 1.00 |
| `nomic-embed-text` | 768 | 0.070s | 0.00 | 0.50 | 0.33 |
| `bge-m3` | 1024 | 0.225s | 0.83 | 1.00 | 0.92 |

## 질의별 검색 결과

### `embeddinggemma:latest`

| query | expected | top1 | rank | top3 |
|---|---|---|---:|---|
| 날씨 때문에 잘 팔린 메뉴가 있었어? | `memo_weather` | `memo_weather` | 1 | memo_weather, memo_price_resistance, memo_lunch_inventory |
| 점심 피크 때 부족했던 상품을 확인하고 싶어 | `memo_lunch_inventory` | `memo_lunch_inventory` | 1 | memo_lunch_inventory, memo_delivery_complaint, memo_price_resistance |
| 쿠폰을 보낸 뒤 재방문 효과가 있었는지 찾아줘 | `memo_coupon_revisit` | `memo_coupon_revisit` | 1 | memo_coupon_revisit, memo_price_resistance, memo_weekend_staff |
| 배달 고객 불만 원인이 뭐였지? | `memo_delivery_complaint` | `memo_delivery_complaint` | 1 | memo_delivery_complaint, memo_lunch_inventory, memo_coupon_revisit |
| 주말에 직원 배치를 늘린 효과가 있었나? | `memo_weekend_staff` | `memo_weekend_staff` | 1 | memo_weekend_staff, memo_coupon_revisit, memo_price_resistance |
| 가격을 올린 뒤 고객 반응이 어땠는지 찾아줘 | `memo_price_resistance` | `memo_price_resistance` | 1 | memo_price_resistance, memo_coupon_revisit, memo_lunch_inventory |

### `nomic-embed-text`

| query | expected | top1 | rank | top3 |
|---|---|---|---:|---|
| 날씨 때문에 잘 팔린 메뉴가 있었어? | `memo_weather` | `memo_coupon_revisit` | 3 | memo_coupon_revisit, memo_delivery_complaint, memo_weather |
| 점심 피크 때 부족했던 상품을 확인하고 싶어 | `memo_lunch_inventory` | `memo_delivery_complaint` | 4 | memo_delivery_complaint, memo_coupon_revisit, memo_weather |
| 쿠폰을 보낸 뒤 재방문 효과가 있었는지 찾아줘 | `memo_coupon_revisit` | `memo_delivery_complaint` | 2 | memo_delivery_complaint, memo_coupon_revisit, memo_weather |
| 배달 고객 불만 원인이 뭐였지? | `memo_delivery_complaint` | `memo_coupon_revisit` | 2 | memo_coupon_revisit, memo_delivery_complaint, memo_weather |
| 주말에 직원 배치를 늘린 효과가 있었나? | `memo_weekend_staff` | `memo_coupon_revisit` | 5 | memo_coupon_revisit, memo_delivery_complaint, memo_weather |
| 가격을 올린 뒤 고객 반응이 어땠는지 찾아줘 | `memo_price_resistance` | `memo_delivery_complaint` | 6 | memo_delivery_complaint, memo_coupon_revisit, memo_weather |

### `bge-m3`

| query | expected | top1 | rank | top3 |
|---|---|---|---:|---|
| 날씨 때문에 잘 팔린 메뉴가 있었어? | `memo_weather` | `memo_weather` | 1 | memo_weather, memo_delivery_complaint, memo_price_resistance |
| 점심 피크 때 부족했던 상품을 확인하고 싶어 | `memo_lunch_inventory` | `memo_lunch_inventory` | 1 | memo_lunch_inventory, memo_delivery_complaint, memo_weekend_staff |
| 쿠폰을 보낸 뒤 재방문 효과가 있었는지 찾아줘 | `memo_coupon_revisit` | `memo_coupon_revisit` | 1 | memo_coupon_revisit, memo_weekend_staff, memo_delivery_complaint |
| 배달 고객 불만 원인이 뭐였지? | `memo_delivery_complaint` | `memo_delivery_complaint` | 1 | memo_delivery_complaint, memo_lunch_inventory, memo_price_resistance |
| 주말에 직원 배치를 늘린 효과가 있었나? | `memo_weekend_staff` | `memo_weekend_staff` | 1 | memo_weekend_staff, memo_coupon_revisit, memo_weather |
| 가격을 올린 뒤 고객 반응이 어땠는지 찾아줘 | `memo_price_resistance` | `memo_coupon_revisit` | 2 | memo_coupon_revisit, memo_price_resistance, memo_weekend_staff |
