# 라이선스 점검 리포트 (F10, §13)

**생성 명령:** `uv run pip-licenses --format=markdown`

**결론:** 프로젝트 라이선스 **MIT** 채택에 충돌 없음. 강한 카피레프트(GPL/AGPL/LGPL) **없음**.

## 프로젝트 라이선스 선정 근거
- OSI 승인 permissive 라이선스 채택(§9, §13). 단순·광범위 호환의 **MIT** 선택.
- (대안 Apache-2.0: 명시적 특허 라이선스가 필요하면 고려 가능)

## 런타임 의존성 라이선스
| 패키지 | 버전 | 라이선스 | 분류 |
|---|---|---|---|
| requests | 2.34.2 | Apache-2.0 | permissive |
| pandas | 3.0.3 | BSD-3-Clause | permissive |
| numpy | 2.5.0 | BSD-3-Clause 외 | permissive |
| scipy | 1.18.0 | BSD-3-Clause | permissive |
| scikit-learn | 1.9.0 | BSD-3-Clause | permissive |
| python-dotenv | 1.2.2 | BSD-3-Clause | permissive |
| lightgbm | 4.6.0 | MIT | permissive |
| openpyxl | 3.1.5 | MIT | permissive |
| matplotlib | 3.11.0 | PSF (BSD 호환) | permissive |

## 카피레프트 점검
- 전체 설치 패키지 스캔에서 **GPL/AGPL/LGPL 없음**.
- `certifi`(MPL-2.0, requests 전이 의존): MPL은 **파일 단위 약한 카피레프트**로, 해당 파일을
  수정할 때만 공개 의무가 발생한다. 우리는 **수정 없이 전이 사용**하므로 MIT 배포와 양립.

## 데이터 라이선스
- 조류경보제·물환경 자료: 공공데이터(공공누리 **제1유형 출처표시**). 출처 표기 필요.
- 기상청 ASOS: 공공데이터/기상자료 이용 약관 준수.
- **원자료는 저장소에 포함하지 않는다**(재배포 리스크 회피). 취득 스크립트로 재생성. (data/ gitignore)

## 산출물
- `LICENSE`(MIT), `THIRD_PARTY_NOTICES`, 본 리포트.
- 개발 의존성(pytest·nbconvert·ipykernel·pip-licenses)은 배포물에 포함되지 않음.
