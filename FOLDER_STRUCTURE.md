# 폴더 구조 및 파일 목록

## 📂 전체 디렉토리 구조

```
c:\omniverse_exts\
│
├── .idea/                              # IDE 설정 (PyCharm, VSCode)
├── .thumbs/                            # 미디어 썸네일 캐시
├── AMR.usd                             # 3D 모델 프로토타입 (로봇)
├── KMP_600i.fbx                        # 자동차 3D 모델
│
└── platform_ext/                       # 🔑 메인 Omniverse 확장
    │
    ├── .git/                           # Git 저장소
    ├── extension.toml                  # 📋 확장 설정 (의존성, 리소스)
    ├── README.md                       # 프로젝트 문서
    ├── SHA256                          # 체크섬 파일
    │
    ├── config/
    │   └── Network.json                # 🔌 서버 연결 설정
    │
    ├── fonts/
    │   ├── OFL.txt                     # 오픈 폰트 라이선스
    │   ├── README.txt                  # 폰트 설명
    │   └── static/
    │       ├── NotoSansKR-Bold.ttf     # 한글 폰트 (굵음)
    │       └── NotoSansKR-Regular.ttf  # 한글 폰트 (일반)
    │
    ├── PNG/                            # 리소스 이미지 파일들
    │   ├── AMR.PNG                     # AMR 로봇 이미지
    │   ├── amr.PNG                     # 작은 크기 AMR 이미지
    │   └── ... (기타 이미지)
    │
    ├── resource/
    │   ├── map_GBFTT_GBFTT_1pf.json    # 경로 계획 맵 데이터 (노드/엣지)
    │   └── map_E_Comp_E_Comp_1pf.json  # (선택사항) 다른 맵 데이터
    │
    └── ui_code/                        # 🎨 Python 코드 (메인)
        │
        ├── __init__.py                 # ✅ IExt 진입점, HTTP 핑어, 이벤트 루프
        ├── main.py                     # 📐 UI 레이아웃 & 라이프사이클
        ├── client.py                   # 🌐 REST API 클라이언트
        │
        ├── AMR/                        # 🤖 자율주행로봇 제어 모듈
        │   ├── __init__.py             # (빈 파일 또는 패키지 초기화)
        │   ├── amr_control_panel.py    # ✏️ AMR 선택 및 명령 전송
        │   ├── amr_details_panel.py    # 📊 AMR 상세 정보 표시
        │   ├── amr_pathfinder_panel.py # 🗺️ 경로 계획 미니맵
        │   ├── map_GBFTT_GBFTT_1pf.json # (캐시된 맵 데이터)
        │   └── __pycache__/            # 바이트코드 캐시
        │
        ├── Chatbot/                    # 💬 챗봇 / LLM 통합
        │   ├── __init__.py
        │   ├── chatbot_panel.py        # 챗봇 UI + SSE 알림
        │   └── __pycache__/
        │
        ├── Container/                  # 📦 컨테이너 관리
        │   ├── __init__.py
        │   ├── container_list_panel.py # 컨테이너 목록 & 필터링
        │   └── __pycache__/
        │
        ├── Mission/                    # ✈️ 미션 모니터링
        │   ├── __init__.py
        │   ├── mission_panel.py        # 미션 상태 표시 (working/waiting/reserved)
        │   └── __pycache__/
        │
        ├── ui/                         # 🎨 UI 컴포넌트 계층
        │   │
        │   ├── components/             # 재사용 가능한 컴포넌트
        │   │   ├── __init__.py
        │   │   ├── amr_card.py         # 🎴 AMR 카드 (상태, 배터리, 사진)
        │   │   └── __pycache__/
        │   │
        │   ├── scene/                  # 3D 렌더링 & 시각화
        │   │   ├── __init__.py
        │   │   ├── amr_3d.py           # 🎭 Omniverse USD 기반 로봇 표시
        │   │   ├── linecar.py          # 🚗 자동차 모델 색상 지정
        │   │   └── __pycache__/
        │   │
        │   ├── sections/               # 화면 구성 섹션
        │   │   ├── __init__.py
        │   │   ├── top_bar.py          # 🔝 상단 메뉴바
        │   │   ├── amr_panel.py        # 📱 AMR 카드 목록
        │   │   ├── status_panel.py     # 📈 상태 패널 (도넛 차트)
        │   │   ├── bottom_bar.py       # 🔽 하단 제어 바
        │   │   ├── body_data_panel.py  # 🏭 바디라인 데이터 대시보드
        │   │   └── __pycache__/
        │   │
        │   ├── utils/                  # 공용 유틸리티
        │   │   ├── __init__.py
        │   │   ├── common.py           # 🛠️ 헬퍼 함수 (포맷, 경로, 색상)
        │   │   └── __pycache__/
        │   │
        │   └── __pycache__/            # UI 캐시
        │
        └── __pycache__/                # 메인 캐시
```

---

## 📋 전체 파일 목록

### 루트 파일
| 파일 | 크기(예) | 설명 |
|------|---------|------|
| `extension.toml` | 0.5KB | 확장 설정, 의존성, 리소스 경로 |
| `README.md` | ~1KB | 프로젝트 문서 |
| `SHA256` | 0.1KB | 체크섬 |

### 설정 및 리소스
| 경로 | 파일 | 설명 |
|------|------|------|
| `config/` | `Network.json` | 서버 IP, 포트, mapCode 설정 |
| `fonts/static/` | `NotoSansKR-*.ttf` | 한글 폰트 |
| `PNG/` | `AMR.PNG`, `amr.PNG` | 로봇 이미지 |
| `resource/` | `map_*.json` | 맵 데이터 (노드, 엣지, 장애물) |

### Python 코드 파일

#### 코어 (ui_code/)
| 파일 | 줄 | 목적 |
|------|----|----|
| `__init__.py` | 1003 | IExt 구현, HTTP 핑어, UI 큐 |
| `main.py` | 306 | UI 레이아웃, 라이프사이클 |
| `client.py` | 302 | REST API 클라이언트 |

#### AMR 제어 (ui_code/AMR/)
| 파일 | 줄 | 목적 |
|------|----|----|
| `amr_control_panel.py` | 443 | AMR 선택, 명령 전송 (Move/Pause/Cancel) |
| `amr_details_panel.py` | 229 | AMR 상세 정보 (배터리, 상태, 미션) |
| `amr_pathfinder_panel.py` | 704 | 경로 계획 미니맵 (UI + HTTP) |

#### 기타 모듈
| 폴더 | 파일 | 줄 | 목적 |
|------|------|----|----|
| `Chatbot/` | `chatbot_panel.py` | 249 | 챗봇 UI + SSE 알림 |
| `Container/` | `container_list_panel.py` | 225 | 컨테이너 목록, 필터링 |
| `Mission/` | `mission_panel.py` | 211 | 미션 상태 (working/waiting/reserved) |

#### UI 컴포넌트 (ui_code/ui/)
| 폴더 | 파일 | 줄 | 목적 |
|------|------|----|----|
| `components/` | `amr_card.py` | 161 | AMR 카드 컴포넌트 |
| `scene/` | `amr_3d.py` | 330 | Omniverse USD 3D 렌더링 |
| `scene/` | `linecar.py` | 474 | 자동차 색상 지정, 재료 바인딩 |
| `sections/` | `top_bar.py` | 73 | 상단 메뉴바 |
| `sections/` | `amr_panel.py` | 18 | AMR 카드 목록 |
| `sections/` | `status_panel.py` | 201 | 상태 도넛 차트 |
| `sections/` | `bottom_bar.py` | 113 | 하단 제어 바 |
| `sections/` | `body_data_panel.py` | 134 | 바디라인 데이터 대시보드 |
| `utils/` | `common.py` | 30 | 공용 헬퍼 함수 |

---

## 📊 코드 통계

### 총 줄 수
```
ui_code/__init__.py:              1,003줄
ui_code/AMR/amr_pathfinder_panel.py:  704줄
ui_code/AMR/amr_control_panel.py:    443줄
ui_code/ui/scene/linecar.py:         474줄
ui_code/ui/scene/amr_3d.py:          330줄
ui_code/main.py:                     306줄
ui_code/client.py:                   302줄
ui_code/Chatbot/chatbot_panel.py:    249줄
ui_code/Container/container_list_panel.py: 225줄
ui_code/Mission/mission_panel.py:    211줄
ui_code/ui/sections/status_panel.py: 201줄
ui_code/AMR/amr_details_panel.py:    229줄
ui_code/ui/sections/body_data_panel.py: 134줄
ui_code/ui/sections/bottom_bar.py:   113줄
ui_code/ui/components/amr_card.py:   161줄
ui_code/ui/sections/top_bar.py:       73줄
ui_code/ui/sections/amr_panel.py:     18줄
ui_code/ui/utils/common.py:           30줄
───────────────────────────────
총계: ~5,700줄
```

### 의존성
```
Omniverse Kit (omni.ui, omni.usd, carb)
requests (REST API)
NumPy (도넛 차트 렌더링)
```

---

## 🔑 주요 설정 파일

### `Network.json` (서버 연결)
```json
{
  "opServerIP": "127.0.0.1",
  "opServerPort": 49000,
  "https": false,
  "baseUrl": "http://127.0.0.1:49000/",
  "mapCode": "GBFTT"
}
```

**설정 항목:**
- `opServerIP`: 백엔드 서버 IP
- `opServerPort`: 백엔드 서버 포트
- `https`: HTTPS 사용 여부
- `baseUrl`: (선택) 기본 URL 수동 지정
- `mapCode`: 맵 파일 코드 (map_{code}_{code}_1pf.json)

### `extension.toml` (확장 설정)
```toml
[package]
title = "Platform UI"
version = "1.0.0"
description = "Simple test extension for UI in Omniverse Kit"
category = "Custom"

[dependencies]
"omni.ui" = {}
"omni.kit.uiapp" = {}
"omni.kit.pipapi" = {}

[python.pipapi]
use_online_index = true
requirements = ["requests>=2.31,<3"]
modules = ["requests"]

[python]
[[python.module]]
name = "ui_code"

[[resources]]
name = "fonts"
path = "fonts"
```

**설정 항목:**
- `[package]`: 확장 메타데이터
- `[dependencies]`: 의존 Omniverse 모듈
- `[python.pipapi]`: pip 패키지 관리
- `[python.module]`: Python 모듈 등록
- `[[resources]]`: 리소스 경로 (폰트, 이미지)

---

## 📦 리소스 파일

### 이미지 (PNG/)
- `AMR.PNG`: 큰 크기 로봇 이미지 (AMR Details 패널)
- `amr.PNG`: 작은 크기 로봇 이미지 (카드 썸네일)

### 폰트 (fonts/static/)
- `NotoSansKR-Bold.ttf`: 굵은 한글 폰트
- `NotoSansKR-Regular.ttf`: 일반 한글 폰트

### 맵 데이터 (resource/)
- `map_GBFTT_GBFTT_1pf.json`: GBFTT 맵 (기본)
  ```json
  {
    "nodes": [
      {"x": 0, "y": 0, "name": "N1"},
      {"x": 10, "y": 5, "name": "N2"},
      ...
    ],
    "edges": [
      {"from": "N1", "to": "N2"},
      ...
    ]
  }
  ```

---

## 📱 화면 구성

```
┌──────────────────────────────────────────────────┐
│ Top Bar (top_bar.py)                             │
│ [Automes Logo] [Meta Factory] [Temp/Humidity]    │
├──────────────────┬──────────────────────────────┤
│ Status Panel     │ AMR Cards List               │
│ (status_panel)   │ (amr_card.py)                │
│ - Donut Chart    │ - Card 1: R01                │
│ - Total/Working  │ - Card 2: R02                │
│ - Waiting/Charge │ - Card 3: ...                │
├──────────────────┼──────────────────────────────┤
│ Container List   │ Mission Panel                │
│ (container)      │ (mission_panel.py)           │
│ - Model Filter   │ - Working: 5                 │
│ - Status Filter   │ - Waiting: 3                │
│ - List Items     │ - Reserved: 2                │
├──────────────────┼──────────────────────────────┤
│ Bottom Bar (bottom_bar.py)                       │
│ [AMR Control] [Chatbot] [Pathfinder] [BodyData] │
└──────────────────────────────────────────────────┘

분리된 Floating Windows:
├─ AMR Details (amr_details_panel.py)
├─ AMR Control (amr_control_panel.py)
├─ Pathfinder (amr_pathfinder_panel.py)
├─ Chatbot (chatbot_panel.py)
└─ Body Data (body_data_panel.py)
```

---

## 🔄 모듈 상호작용

```
┌─────────────────────────────────────────────────┐
│ Omniverse Kit (메인 이벤트 루프)                  │
├─────────────────────────────────────────────────┤
│ IExt.__init__.py                                │
│ ├─ HttpPinger (서버 상태 감지)                    │
│ ├─ DigitalTwinClient (REST 폴링)                 │
│ └─ UI Queue (thread-safe 작업 처리)              │
├─────────────────────────────────────────────────┤
│ main.py (UiLayoutBase)                          │
│ ├─ top_bar.py                                  │
│ ├─ amr_panel.py (AMR 카드 목록)                 │
│ ├─ status_panel.py (도넛 차트)                  │
│ ├─ bottom_bar.py (버튼)                         │
│ │  ├─ amr_control_panel.py                     │
│ │  ├─ chatbot_panel.py                         │
│ │  ├─ amr_pathfinder_panel.py                  │
│ │  └─ body_data_panel.py                       │
│ ├─ amr_details_panel.py                        │
│ ├─ container_list_panel.py                     │
│ ├─ mission_panel.py                            │
│ ├─ amr_3d.py (3D 렌더링)                        │
│ └─ linecar.py (색상 지정)                       │
├─────────────────────────────────────────────────┤
│ common.py (공용 유틸)                            │
├─────────────────────────────────────────────────┤
│ 백엔드 서버 (Django/REST API)                   │
│ Network.json로 연결                             │
└─────────────────────────────────────────────────┘
```

---

## 🚀 파일 로딩 순서

```
1. Omniverse Kit 시작
2. extension.toml 파싱
   ├─ 의존성 로드 (omni.ui, omni.kit.uiapp)
   ├─ Python 모듈 등록 (ui_code)
   └─ 리소스 경로 설정 (fonts/)
3. __init__.py → PlatformExtension 클래스 인스턴스화
4. on_startup(ext_id) 호출
   ├─ HttpPinger 시작
   ├─ DigitalTwinClient 초기화
   ├─ main.py UiLayoutBase 초기화
   ├─ 폴링 스레드 시작 (0.5초 주기)
   └─ UI 레이아웃 구성
5. 메인 이벤트 루프 진입
   ├─ 데이터 폴링 (백그라운드)
   ├─ UI 콜백 처리
   └─ 렌더링
```

---

## 📝 파일 상호 참조

### Import 관계
```
__init__.py
├─ client.py (DigitalTwinClient)
├─ main.py (UiLayoutBase)
│  ├─ top_bar.py
│  ├─ amr_panel.py (amr_card.py)
│  ├─ status_panel.py
│  ├─ bottom_bar.py
│  │  ├─ amr_control_panel.py
│  │  ├─ chatbot_panel.py
│  │  ├─ amr_pathfinder_panel.py
│  │  └─ body_data_panel.py
│  ├─ amr_details_panel.py
│  ├─ container_list_panel.py
│  ├─ mission_panel.py
│  ├─ amr_3d.py
│  └─ linecar.py
└─ common.py (모든 UI 파일에서 import)
```

### 데이터 흐름
```
Network.json (설정)
    ↓
client.py (로드 및 REST 요청)
    ↓
__init__.py (콜백 처리)
    ↓
main.py (UI 모델 업데이트)
    ↓
각 패널 (화면 렌더링)
```

---

## 🔐 보안 고려사항

1. **Network.json:** 민감한 서버 정보 포함
   - 버전 관리에서 제외 권장 (.gitignore)
   - 배포 시 환경변수로 관리

2. **API 인증:** 현재 미구현
   - 추가 시: client.py의 headers에 토큰 추가

3. **SSL/TLS:** https 옵션 지원
   - extension.toml의 requests 버전 확인 (인증서 검증)

