# 모델 평가 리포트 (F6+F7)

데이터셋 34,634행 × 피처 41 | 양성률 10.2% | seed 42

## 시간 일반화 (확장 윈도우 연도 분할, 평균)

| method | PR-AUC | Recall@P0.5 | ROC-AUC |
|---|---|---|---|
| LightGBM | 0.807 | 0.905 | 0.962 |
| persistence | 0.751 | 0.835 | 0.919 |
| 계절규칙 | 0.263 | 0.000 | 0.745 |


## 지점 일반화 (지점 GroupKFold, 평균)

| method | PR-AUC | Recall@P0.5 | ROC-AUC |
|---|---|---|---|
| LightGBM | 0.785 | 0.919 | 0.967 |
| persistence | 0.731 | 0.821 | 0.930 |
| 계절규칙 | 0.253 | 0.000 | 0.805 |


## 시간순 pooled OOF

- LightGBM PR-AUC **0.779** / persistence 0.735 / 계절 0.267
- LightGBM Recall@P0.5 **0.906** / persistence 0.811

그림: reports/figures/모델_pr_curve.png, 모델_yearly_prauc.png, 모델_feature_importance.png
