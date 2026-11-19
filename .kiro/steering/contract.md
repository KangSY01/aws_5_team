---
inclusion: always
---

# 인터페이스 약속

API 형식의 원본은 `docs/api-contract.md`와 `backend/app/models/`(Pydantic 모델)입니다. 이 문서는 그 파일을 불러오기만 하고 형식을 따로 정의하지 않습니다.

#[[file:docs/api-contract.md]]

## 작업할 때 지킬 것
- 요청·응답 필드는 `backend/app/models/plan.py`, `backend/app/models/api.py`의 모델과 같아야 합니다. 프론트엔드도 같은 필드 이름을 씁니다.
- 위 세 곳(`docs/api-contract.md`, `backend/app/models/`, `backend/app/data/` 샘플)은 공용 파일입니다. 뼈대 담당자 리뷰를 거친 PR로 함께 바꿉니다.
- 계약에 없는 엔드포인트(예: 메뉴판 사진 번역, 한국어 음성)가 필요하면 코드를 먼저 만들지 말고 계약 변경 PR을 먼저 올립니다.
- 시각은 시간대를 포함한 ISO 8601(`2026-11-21T10:00:00+09:00`), 날짜는 `YYYY-MM-DD`입니다.
- 장소 ID는 `backend/app/data/places.json`의 kebab-case 값(예: `haeundae-beach`)만 씁니다.
- `Issue.detail`은 개발자용 한국어 설명입니다. 사용자에게 보여 줄 문장은 에이전트 답변이나 프론트엔드 번역 사전에서 만듭니다.
