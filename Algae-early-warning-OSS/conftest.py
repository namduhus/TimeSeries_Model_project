"""pytest 부트스트랩 — OpenMP 런타임 충돌 회피.

macOS 에서 torch 와 lightgbm 이 각자 libomp 를 번들한다. 한 프로세스에서 두 라이브러리를
함께 학습에 쓰면(테스트가 전 모듈을 한 인터프리터에서 수집·실행) 두 OMP 런타임이 충돌해
segfault 가 난다. OMP 스레드를 1로 고정하면 충돌이 사라진다(테스트는 소규모라 속도 영향 없음).

env 는 libomp 로드 전에 설정해야 하므로, 어떤 무거운 import 보다 먼저 둔다.
CLI 파이프라인(python -m src.*)은 프로세스가 분리돼 영향받지 않는다.
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
