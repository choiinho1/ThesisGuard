# Evaluation

LangSmith 골든셋에서 다음 지표를 기록한다.

- Evidence Classification Accuracy
- Thesis Change Detection Accuracy
- Tool Selection Accuracy
- Citation Groundedness
- Contradiction Detection Recall

`metrics.py`의 순수 함수는 외부 서비스 없이 단위 테스트할 수 있으며, LangSmith evaluator 콜백에서 그대로
호출할 수 있다. 실제 데이터셋 ID와 API 키는 환경변수로 관리하고 저장소에 커밋하지 않는다.
