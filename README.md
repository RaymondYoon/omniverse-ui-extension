# Omniverse UI Extension

Omniverse Kit 기반의 사용자 정의 UI 확장 기능입니다.  
AMR(Autonomous Mobile Robot) 디지털 트윈 및 상태 모니터링을 위해 제작되었습니다.

---

## 📂 프로젝트 구조
```
platform_ext/
├─ resource/ # 이미지 및 리소스
├─ ui_code/ # UI 관련 코드
│ ├─ Container/ # 컨테이너 관리 패널
│ ├─ Mission/ # 미션 패널
│ ├─ client.py # API 클라이언트
│ ├─ main.py # UI 레이아웃 및 로직
│ └─ init.py # 초기화 스크립트
├─ extension.toml # Omniverse Extension 설정
└─ .gitignore
```

---

## ⚙️ 주요 기능
- Omniverse Kit 환경에서 동작하는 **커스텀 UI 제공**
- AMR 및 컨테이너 상태 **실시간 모니터링**
- REST API 연동을 통한 **서버 데이터 통신**
- 확장 가능한 구조로 **Mission/Container 패널 관리**

---

## 🛠️ 기술 스택
- **Language**: Python 3.x  
- **Framework**: NVIDIA Omniverse Kit SDK  
- **UI**: `omni.ui`, `omni.ext`  
- **Version Control**: Git + GitHub  

---

## 🚀 실행 방법
1. Omniverse Kit 설치  
2. `platform_ext` 디렉토리를 Omniverse Extensions 경로에 복사  
3. `extension.toml` 등록 후 Kit 실행  
4. Extension Manager에서 활성화  

---

## 📌 앞으로의 계획
- UI 개선 (로그 뷰어, 필터링 기능 추가)  
- AMR 미션 상태 시각화 기능 강화  
- 확장성 고려한 코드 구조화  

---

## ✨ 작성자
**RaymondYoon (윤준상)**  
- Backend & Digital Twin Developer  
- Email: yoonjunsang@naver.com  
- GitHub: [RaymondYoon](https://github.com/RaymondYoon)
