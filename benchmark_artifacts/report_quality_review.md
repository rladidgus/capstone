# 리포트 품질 검수 결과

## 요약

| report_id | mode | score | chart | details | actions | issues |
|---|---:|---:|---|---:|---:|---|
| `ca6a4d6a-0717-46fb-b8b6-765dde91555c` | quick | 5/5 | OK | 3 | 3 | 없음 |
| `69af02bb-38e0-4939-bb00-68d3100fad0d` | quick | 4/5 | OK | 3 | 3 | analysis_details[3] 설명이 짧음 |
| `29657131-58b9-4f9a-ada5-d2b849fa04e9` | quick | 2/5 | OK | 0 | 0 | summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만 |
| `e810a3ae-f0f5-49a7-b3b7-f89801c33712` | deep | 2/5 | OK | 0 | 0 | summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만 |
| `ee8d461a-4cc0-46cf-a00a-cf2304d9ec83` | deep | 5/5 | OK | 2 | 5 | 없음 |
| `a388ecc7-ec33-432e-a77a-a7e9da2d4f96` | deep | 2/5 | OK | 0 | 0 | summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만 |
| `1b9b7976-17c0-4dc8-ad96-6cd06ff680ef` | quick | 2/5 | OK | 0 | 0 | summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만 |
| `1fa98bbd-ffd9-497b-b23b-4ab1c45d20f0` | quick | 5/5 | OK | 1 | 3 | 없음 |

## 샘플 본문

### quick - 5/5

- report_id: `ca6a4d6a-0717-46fb-b8b6-765dde91555c`
- confidence: `high`
- issues: 없음

**Summary**

업로드된 매출 데이터 기준 총매출은 792,730원, 일평균 매출은 113,247원입니다. 12시와 샌드위치를 중심으로 매출 패턴을 우선 점검하는 것이 좋습니다.

**Analysis Details**

- 내부 매출 패턴 / 중립: 기간 내 매출은 총 792,730원이며, 일평균은 113,247원입니다. quick mode에서는 검증된 계산 로직으로 일별/시간대별 매출과 상위 메뉴를 요약했습니다.
- 시간대와 메뉴 구성 / 중립: 매출이 집중되는 시간대는 12시로 확인되며, 샌드위치를 중심으로 피크 시간 운영과 재고 준비를 조정할 수 있습니다.
- 통계 분석 결과 / 중립: 매출 추세 변화율: -10.87%. 이 값은 업로드된 매출 데이터에서 계산된 보조 지표이며, 기간 내 매출 흐름을 판단할 때 내부 매출 패턴과 함께 참고해야 합니다.

**Action Items**

- 12시 전후 인력 배치와 조리/준비 수량을 우선 조정하세요.
- 샌드위치와 함께 구매되는 메뉴를 묶어 세트 또는 추천 메뉴로 노출하세요.
- 일별 매출이 낮은 날짜를 기준으로 할인, 쿠폰, 재방문 메시지 발송 효과를 비교하세요.

### quick - 4/5

- report_id: `69af02bb-38e0-4939-bb00-68d3100fad0d`
- confidence: `high`
- issues: analysis_details[3] 설명이 짧음

**Summary**

업로드된 매출 데이터 기준 총매출은 792,730원, 일평균 매출은 113,247원입니다. 12시와 샌드위치를 중심으로 매출 패턴을 우선 점검하는 것이 좋습니다.

**Analysis Details**

- 내부 매출 패턴 / 중립: 기간 내 매출은 총 792,730원이며, 일평균은 113,247원입니다. quick mode에서는 검증된 계산 로직으로 일별/시간대별 매출과 상위 메뉴를 요약했습니다.
- 시간대와 메뉴 구성 / 중립: 매출이 집중되는 시간대는 12시로 확인되며, 샌드위치를 중심으로 피크 시간 운영과 재고 준비를 조정할 수 있습니다.
- 통계 분석 결과 / 중립: 매출 추세 변화율: -10.87%

**Action Items**

- 12시 전후 인력 배치와 조리/준비 수량을 우선 조정하세요.
- 샌드위치와 함께 구매되는 메뉴를 묶어 세트 또는 추천 메뉴로 노출하세요.
- 일별 매출이 낮은 날짜를 기준으로 할인, 쿠폰, 재방문 메시지 발송 효과를 비교하세요.

### quick - 2/5

- report_id: `29657131-58b9-4f9a-ada5-d2b849fa04e9`
- confidence: `high`
- issues: summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만

**Summary**

분석이 완료되었습니다.

**Analysis Details**


**Action Items**


### deep - 2/5

- report_id: `e810a3ae-f0f5-49a7-b3b7-f89801c33712`
- confidence: `high`
- issues: summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만

**Summary**

분석이 완료되었습니다.

**Analysis Details**


**Action Items**


### deep - 5/5

- report_id: `ee8d461a-4cc0-46cf-a00a-cf2304d9ec83`
- confidence: `high`
- issues: 없음

**Summary**

전체 요약: 전체 매출이 10.87% 감소하였으며, 이는 2022년 3월부터 발생한 매출 추세 변화로 인해 발생한 것으로 보입니다.

**Analysis Details**

- 전체 매출 / 부정적: 전체 매출이 10.87% 감소하였으며, 이는 2022년 3월부터 발생한 매출 추세 변화로 인해 발생한 것으로 보입니다. 이는 가장 중요한 요인으로 판단됩니다. 이 변화는 전체 매출에 긍정적인 영향을 미치지 않고 있으며, 이로 인해 기업의 경영 수익이 감소할 수 있습니다.
- 2022년 3월 이후 매출 추세 변화 / 부정적: 2022년 3월부터 발생한 매출 추세 변화는 전체 매출에 부정적인 영향을 미치고 있습니다. 이는 가장 중요한 요인으로 판단됩니다. 이 변화는 전체 매출에 긍정적인 영향을 미치지 않고 있으며, 이로 인해 기업의 경영 수익이 감소할 수 있습니다.

**Action Items**

- 1. 매출 추세 변화 분석을 통해 원인 파악: 매출 추세 변화를 분석하여 원인을 파악하고, 이를 기업의 경영 전략에 반영하세요.
- 2. 마케팅 전략 수정: 매출 추세 변화를 고려하여 마케팅 전략을 수정하고, 이를 통해 매출을 증대시키는 데 노력하세요.
- 3. 제품 및 서비스 개선: 제품 및 서비스를 개선하여 고객의 요구를 충족하고, 이를 통해 매출을 증대시키는 데 노력하세요.
- 4. 경영 수익 증대 방안 수립: 경영 수익을 증대시키기 위한 방안을 수립하고, 이를 통해 기업의 경영 수익을 증대시키는 데 노력하세요.
- 5. 경영 수익 분석 및 예측: 경영 수익을 분석하고, 이를 통해 기업의 경영 수익을 예측하고, 이를 통해 기업의 경영 수익을 증대시키는 데 노력하세요.

### deep - 2/5

- report_id: `a388ecc7-ec33-432e-a77a-a7e9da2d4f96`
- confidence: `high`
- issues: summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만

**Summary**

분석이 완료되었습니다.

**Analysis Details**


**Action Items**


### quick - 2/5

- report_id: `1b9b7976-17c0-4dc8-ad96-6cd06ff680ef`
- confidence: `high`
- issues: summary가 너무 짧거나 없음; analysis_details가 없음; action_items가 2개 미만

**Summary**

분석이 완료되었습니다.

**Analysis Details**


**Action Items**


### quick - 5/5

- report_id: `1fa98bbd-ffd9-497b-b23b-4ab1c45d20f0`
- confidence: `high`
- issues: 없음

**Summary**

매출이 10.87% 감소한 것으로 보이며, 주요 요인으로는 가까운 시간 내에 잠재적인 소비자 수익 감소가 있을 수 있습니다.

**Analysis Details**

- 소비자 수익 감소 / 부정적: 가까운 시간 내에 잠재적인 소비자 수익 감소가 있을 수 있습니다.

**Action Items**

- 고객 유치 및 유지 전략 수립
- 제품 및 서비스 가격 조정 및 할인 캠페인 진행
- 고객 서비스 강화 및 고객 만족도 향상
