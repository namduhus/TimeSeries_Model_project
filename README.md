# 시계열 모델 프로젝트 모음

## TimesFM 실행

TimesFM 2.x는 Python 3.10 이상이 필요합니다. 이 폴더에서는 `uv`를 기준으로 실행합니다.

```bash
uv sync
uv run python examples/timesfm_demo.py
```

첫 실행 시 `google/timesfm-2.5-200m-pytorch` 모델을 Hugging Face에서 내려받습니다.

실행 결과:

- `outputs/timesfm_demo_forecast.csv`
- `outputs/timesfm_demo_forecast.png`
