"""확장3 딥러닝 — 테이블형 신경망(MLP, FT-Transformer)으로 GBDT와 공정 비교.

LightGBM과 **동일한 피처 X**를 입력으로 쓰는 두 모델을 제공한다:
- MLP: 정규화된 다층 퍼셉트론(딥러닝 하한 베이스라인)
- FTTransformer: 피처 토큰화 + 셀프어텐션(테이블형 DL 대표, Gorishniy et al. 2021)

누수 통제(§8.3): 임퓨터·스케일러·범주 인코딩은 **각 폴드의 (inner) train 에서만 fit**.
                LightGBM은 스케일 불필요했으나 신경망은 필수라, 전체 fit 은 즉시 누수.
재현성: 시드 고정 + float32. MPS(Apple Silicon)/CPU 자동 선택.
        MPS 는 부동소수점 결정성이 약하므로 게시·리포트 최종 수치는 CPU 권장.
"""

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn as nn
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

from src.modeling import CATEGORICAL, SEED, _inner_time_val


def get_device(prefer: str = "auto") -> torch.device:
    """prefer: 'cpu' | 'mps' | 'auto'(MPS 있으면 MPS)."""
    if prefer != "cpu" and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# --- 폴드 내 전처리 (train 에서만 fit → 누수 없음) ---
def _fit_transform_num(X, num_cols: list[str], fit_idx: np.ndarray) -> np.ndarray:
    # keep_empty_features: train 에 전부 결측인 컬럼도 0으로 유지(컬럼 수 고정 → 모델 입력차원 불변)
    imp = SimpleImputer(strategy="mean", keep_empty_features=True).fit(X.iloc[fit_idx][num_cols])
    sc = StandardScaler().fit(imp.transform(X.iloc[fit_idx][num_cols]))
    return sc.transform(imp.transform(X[num_cols])).astype("float32")


def _fit_transform_cats(X, cat_cols: list[str], fit_idx: np.ndarray):
    """train 범주로 int 코드 매핑(미지 범주 → 0). 반환: (코드행렬, 각 컬럼 카디널리티)."""
    codes, cards = [], []
    for c in cat_cols:
        cats = X.iloc[fit_idx][c].astype("string").dropna().unique()
        m = {v: i + 1 for i, v in enumerate(cats)}          # 0 = unknown
        codes.append(X[c].astype("string").map(m).fillna(0).astype("int64").to_numpy())
        cards.append(len(cats) + 1)
    mat = np.stack(codes, axis=1) if codes else np.zeros((len(X), 0), dtype="int64")
    return mat, cards


# --- 모델 ---
class MLP(nn.Module):
    def __init__(self, n_num, cards, emb_dim=8, hidden=(128, 64), dropout=0.2):
        super().__init__()
        self.embs = nn.ModuleList([nn.Embedding(c, emb_dim) for c in cards])
        dim = n_num + emb_dim * len(cards)
        layers = []
        for h in hidden:
            layers += [nn.Linear(dim, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(dropout)]
            dim = h
        layers.append(nn.Linear(dim, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, xn, xc):
        e = [emb(xc[:, i]) for i, emb in enumerate(self.embs)]
        x = torch.cat([xn, *e], dim=1) if e else xn
        return self.net(x).squeeze(1)


class GEGLU(nn.Module):
    """게이트 FFN — GELU(a)*b. FT-Transformer 의 피드포워드(평범한 MLP-FFN 대체)."""

    def __init__(self, d, hidden, dropout):
        super().__init__()
        self.lin1 = nn.Linear(d, hidden * 2)   # 절반은 값, 절반은 게이트
        self.lin2 = nn.Linear(hidden, d)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        a, b = self.lin1(x).chunk(2, dim=-1)
        return self.lin2(self.drop(torch.nn.functional.gelu(a) * b))


class FTBlock(nn.Module):
    """Pre-Norm 트랜스포머 블록 — 어텐션 + GEGLU FFN. 첫 블록은 첫 LayerNorm 생략(원논문)."""

    def __init__(self, d, n_heads, dropout, first):
        super().__init__()
        self.norm_attn = nn.Identity() if first else nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, n_heads, dropout=dropout, batch_first=True)
        self.norm_ffn = nn.LayerNorm(d)
        self.ffn = GEGLU(d, int(d * 4 / 3), dropout)
        self.res_drop = nn.Dropout(dropout)

    def forward(self, x):
        h = self.norm_attn(x)                                          # Pre-Norm
        x = x + self.res_drop(self.attn(h, h, h, need_weights=False)[0])
        x = x + self.res_drop(self.ffn(self.norm_ffn(x)))
        return x


class FTTransformer(nn.Module):
    """FT-Transformer(Gorishniy et al. 2021)의 충실한 컴팩트 구현.

    피처 토큰화(수치=선형, 범주=임베딩) + [CLS] + Pre-Norm 트랜스포머(GEGLU FFN).
    """

    def __init__(self, n_num, cards, d_token=32, n_blocks=3, n_heads=4, dropout=0.2):
        super().__init__()
        self.num_w = nn.Parameter(torch.randn(n_num, d_token) * 0.02)
        self.num_b = nn.Parameter(torch.zeros(n_num, d_token))
        self.cat_embs = nn.ModuleList([nn.Embedding(c, d_token) for c in cards])
        self.cls = nn.Parameter(torch.randn(1, 1, d_token) * 0.02)
        self.blocks = nn.ModuleList(
            [FTBlock(d_token, n_heads, dropout, first=(i == 0)) for i in range(n_blocks)]
        )
        self.head = nn.Sequential(nn.LayerNorm(d_token), nn.ReLU(), nn.Linear(d_token, 1))

    def forward(self, xn, xc):
        b = xn.shape[0]
        tokens = [xn.unsqueeze(-1) * self.num_w + self.num_b]          # (B, n_num, d)
        tokens += [emb(xc[:, i]).unsqueeze(1) for i, emb in enumerate(self.cat_embs)]
        x = torch.cat([self.cls.expand(b, -1, -1), *tokens], dim=1)
        for blk in self.blocks:
            x = blk(x)
        return self.head(x[:, 0]).squeeze(1)


def _train(model, Xn, Xc, y, tr, val, device, pos_weight,
           epochs=100, patience=12, lr=5e-4, bs=256, weight_decay=1e-2):
    """학습 + 조기종료. 선택 기준은 **inner val 의 PR-AUC**(목표지표 정렬), LR 은 warmup+cosine.

    하이퍼파라미터·조기종료 모두 inner val 로만 결정 → 테스트 폴드 비관측(공정 비교 유지).
    """
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], device=device))
    Xn_t = torch.as_tensor(Xn, device=device)
    Xc_t = torch.as_tensor(Xc, dtype=torch.long, device=device)
    y_t = torch.as_tensor(np.asarray(y, dtype="float32"), device=device)
    tr_t = torch.as_tensor(tr, dtype=torch.long, device=device)
    val_t = torch.as_tensor(val, dtype=torch.long, device=device)
    y_val = np.asarray(y)[val]
    val_two_class = len(np.unique(y_val)) > 1        # PR-AUC 는 양·음성 둘 다 필요

    n_batches = max(1, (len(tr_t) + bs - 1) // bs)
    total_steps = epochs * n_batches
    warmup = max(1, int(0.1 * total_steps))
    def lr_scale(step):                              # warmup 선형 상승 → cosine 감쇠
        if step < warmup:
            return step / warmup
        prog = (step - warmup) / max(1, total_steps - warmup)
        return 0.5 * (1 + math.cos(math.pi * prog))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_scale)

    best_score, best_state, bad = -float("inf"), None, 0
    for _ in range(epochs):
        model.train()
        perm = torch.randperm(len(tr_t), device=device)
        for i in range(0, len(tr_t), bs):
            idx = tr_t[perm[i:i + bs]]
            if len(idx) < 2:                          # BatchNorm 은 배치 1 불가
                continue
            opt.zero_grad()
            loss = lossf(model(Xn_t[idx], Xc_t[idx]), y_t[idx])
            loss.backward()
            opt.step()
            sched.step()
        model.eval()
        with torch.no_grad():
            vlogit = model(Xn_t[val_t], Xc_t[val_t])
        if val_two_class:                             # 목표지표(PR-AUC)로 조기종료
            score = average_precision_score(y_val, torch.sigmoid(vlogit).cpu().numpy())
        else:                                         # 단일클래스 폴드 대비: 손실로 대체
            score = -lossf(vlogit, y_t[val_t]).item()
        if score > best_score + 1e-4:
            best_score, bad = score, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state:
        model.load_state_dict(best_state)
    return model


def train_predict_dl(ds, X, y, tr, te, model_type: str, device, seed: int = SEED) -> np.ndarray:
    """한 폴드: 전처리 fit(inner train) → 학습(early stop on inner val) → te 초과확률 예측."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    num_cols = [c for c in X.columns if c not in CATEGORICAL]
    cat_cols = [c for c in CATEGORICAL if c in X.columns]
    itr, ival = _inner_time_val(ds["date"].to_numpy(), tr)

    Xn = _fit_transform_num(X, num_cols, itr)
    Xc, cards = _fit_transform_cats(X, cat_cols, itr)
    pos = max(int(y[itr].sum()), 1)
    pos_weight = (len(itr) - pos) / pos

    model_cls = MLP if model_type == "mlp" else FTTransformer
    model = model_cls(len(num_cols), cards)
    model = _train(model, Xn, Xc, y, itr, ival, device, pos_weight)

    model.eval()
    with torch.no_grad():
        Xn_t = torch.as_tensor(Xn, device=device)
        Xc_t = torch.as_tensor(Xc, dtype=torch.long, device=device)
        te_t = torch.as_tensor(te, dtype=torch.long, device=device)
        p = torch.sigmoid(model(Xn_t[te_t], Xc_t[te_t])).cpu().numpy()
    return p
