"""대화 에이전트(app/agent.py)의 보조 모듈 (에이전트 담당).

- messages.py   사용자에게 직접 보여 주는 고정 문장(4개 언어)과 출처 제목
- prompt.py     시스템 프롬프트. D 의 app/prompts.py 가 구현되면 그쪽으로 바꾼다
- plan_rules.py 일정 검증과 장소 이름 조회
- tools.py      일정 생성 도구, 조회 도구 묶음, 도구 호출 제한·기록 훅
- answer.py     모델 답변 검증([place:ID] 표식 치환)과 sources 조립
"""
