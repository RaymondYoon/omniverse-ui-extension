# Python 파일 상세 분석

## 📑 파일별 코드 요약

### 1. `ui_code/__init__.py` (1003줄)
**목적:** Omniverse Kit의 IExt 인터페이스 구현, 서버 모니터링, UI 이벤트 큐

**클래스:**
- `HttpPinger`: HTTP 핑 기반 서버 상태 감지
  - `start()`, `stop()` 메서드로 백그라운드 스레드 관리
  - 상태 변경 시 `on_change` 콜백 호출
  - 옵션: HTTP 4xx/5xx 오류를 alive로 처리 가능

- `PlatformExtension` (IExt):
  - `on_startup(ext_id)`: UI 초기화, 서버 연결, 폴링 시작
  - `on_shutdown()`: 정리 작업 (스레드 종료, 리소너 제거)
  - Viewport 조작기 상태 동기화
  - 화면 크기 변경 감지

**주요 기능:**
- Thread-safe UI 작업 큐 (`_ui_queue`)
- 실시간 AMR 로깅
- Network.json 자동 로드

---

### 2. `ui_code/main.py` (306줄)
**목적:** UI 레이아웃 정의 및 라이프사이클 관리

**클래스:**
- `UiLayoutBase`:
  - `on_startup(ext_id)`: 모든 UI 초기화
  - `on_shutdown()`: 창 정리
  - `_kill_window(title)`: 중복 창 방지
  - `on_server_alive(alive)`: 서버 연결 상태 처리

**UI 구조:**
```
┌─ TopBar ─────────────────────────┐
│ [Automes Logo] | [Meta Factory] │
├──────────────────────────────────┤
│ StatusPanel | [AMR Cards]        │
├──────────────────────────────────┤
│ [Container] [Mission] [Details]  │
├──────────────────────────────────┤
│ BottomBar [Control Buttons]      │
└──────────────────────────────────┘
```

**데이터 모델:**
- `m_amr_total`, `m_amr_working`, `m_amr_waiting`, `m_amr_charging`
- `m_pallet_total`, `m_pallet_offmap`, `m_pallet_stationary`, `m_pallet_inhandling`
- `m_mission_reserved`, `m_mission_inprogress`

---

### 3. `ui_code/client.py` (302줄)
**목적:** 백엔드 REST API 클라이언트

**클래스:**
- `DataType`: API 데이터 타입 상수
  ```python
  CONNECTION_INFO, AMR_INFO, CONTAINER_INFO, WORKING_INFO, 
  MISSION_INFO, RESERVATION_INFO, OPC_CONNECTION_CONTROL
  ```

- `DigitalTwinClient`:
  - Network.json에서 설정 로드 (IP, 포트, mapCode)
  - 주기적 폴링 (0.5초 간격, 조정 가능)
  - 콜백 시스템:
    - `on_alive_change(bool)`: 연결 상태 변화
    - `on_request(name, params)`: 요청 전송 전
    - `on_response(name, params, response)`: 응답 수신 후
    - `on_error(exception, name, params)`: 오류 발생 시
  - 자동 재연결 메커니즘

**메서드:**
- `start_polling()`: 폴링 스레드 시작
- `stop_polling()`: 폴링 중지
- `request(name, **params)`: 동기 요청 (timeout 사용)
- `add_on_request(fn)` 등: 콜백 등록

---

### 4. `ui_code/AMR/amr_control_panel.py` (443줄)
**목적:** AMR 선택 및 명령 전송 UI

**명령 매핑:**
```python
Move → ManualMove
Rack Move → ManualRackMove
Pause → AMRPause
Resume → AMRResume
Cancel → MissionCancel
```

**클래스:**
- `AMRControlPanel`:
  - 콤보박스 기반 AMR 선택
  - 명령 선택 콤보박스
  - 동적 파라미터 필드 (Container, Node, Mission)
  - 실시간 선택 업데이트 (Viewport 선택 감지)

**메서드:**
- `update_amr_list(items)`: 서버에서 받은 AMR 리스트 갱신
- `show(amr_id)`: UI 표시
- `_send_command()`: 선택된 명령 전송

---

### 5. `ui_code/AMR/amr_details_panel.py` (229줄)
**목적:** 선택된 AMR의 상세 정보 표시

**표시 정보:**
- AMR ID
- 상태 (색상 도트: 주황색 작업중, 파랑 대기, 초록 충전)
- 배터리 (프로그레스바, 색상 변화)
- Lift 상태 (Up/Down)
- Rack 정보
- 미션 코드
- 노드
- 위치 (X, Y)

**클래스:**
- `AMRPanel`:
  - `update(data)`: 데이터 갱신
  - `_sync_batt_color()`: 배터리 색상 동적 변경
  - 썸네일 이미지 로드

---

### 6. `ui_code/AMR/amr_pathfinder_panel.py` (704줄)
**목적:** 경로 계획 미니맵 시각화

**좌표계:**
- World: X(0~120), Y(-80~40)
- 화면: 마우스 기준 확대/축소, 팬(이동)

**상호작용:**
- 마우스 휠: 확대/축소 (1.1배 스텝, 기본값 1.0~3.0)
- 좌클릭 드래그: 팬
- 확대 중심: 커서 위치

**클래스:**
- `PathFinderPanel`:
  - 맵 JSON 로드 (노드, 엣지)
  - 로봇 위치 폴링 (1초 간격)
  - `_resolve_map_path()`: 맵 파일 자동 탐색
  - Django MAPF 서버 연동 (경로 계획)

**주요 메서드:**
- `show()`: UI 표시
- `update_robots(positions)`: 로봇 위치 갱신
- `set_robot_resolver(fn)`: 로봇 좌표 공급자 설정

---

### 7. `ui_code/Chatbot/chatbot_panel.py` (249줄)
**목적:** LLM 기반 챗봇 + 실시간 알림 UI

**클래스:**
- `ChatAdapter`: Django 백엔드 통신
  - `send(prompt, timeout)`: 프롬프트 전송
  - `warmup()`: LLM 워밍업

- `ChatbotPanel`:
  - 입력/출력 필드
  - SSE(Server-Sent Events) 알림 스트림
  - 알림 태그: LOW, OFFLINE, FAULT, WARN
  - "Reconnect Alerts" 버튼

**SSE 알림:**
```
Alert format: [TAG] Message
예: [OFFLINE] Robot R01 lost connection
```

---

### 8. `ui_code/Container/container_list_panel.py` (225줄)
**목적:** 컨테이너 상태 조회 및 필터링

**필터:**
- Model: All, LR, LF, AR, AC, AF, P
- Status: All, On Map, Off Map

**모델 매핑:**
```python
1: "LR", 2: "LF", 3: "AR", 4: "AC", 5: "AF", 6: "P"
```

**클래스:**
- `ContainerPanel`:
  - 콤보박스 기반 필터
  - 즉시 적용 (index 기반, 콜백 직접)
  - 컨테이너 카드 렌더링

**메서드:**
- `update_data(containers)`: 데이터 갱신
- `refresh()`: 화면 새로고침
- `_canon_model(raw)`: 모델 정규화

---

### 9. `ui_code/Mission/mission_panel.py` (211줄)
**목적:** 미션 상태 모니터링 및 제어

**상태 분류:**
- **Working** (주황): 진행 중
- **Waiting** (파란): 대기 중
- **Reserved** (초록): 예약됨

**클래스:**
- `MissionPanel`:
  - 상태별 섹션 (VStack)
  - 각 미션 행: mission_code, amr_id, node, process, status
  - Cancel 버튼 (행별)
  - Reset All 버튼 (전체 초기화)

**메서드:**
- `set_data_resolver(fn)`: 데이터 공급자 설정
- `update_data(working, waiting, reserved)`: 갱신
- `refresh()`: 화면 새로고침

---

### 10. `ui_code/ui/components/amr_card.py` (161줄)
**목적:** 재사용 가능한 AMR 카드 컴포넌트

**표시 정보:**
- AMR ID
- 상태 (Status)
- Lift 상태 (Up/Down)
- Rack 정보
- Working Type
- 배터리 (프로그레스바, 백분율 표시)
- 썸네일 이미지

**클래스:**
- `AmrCard`:
  - 부모 VStack에 자동 추가
  - `on_plus` 콜백 (+ 버튼 클릭)
  - 배터리 색상 자동 변경 (초록→파랑→빨강)

**메서드:**
- `update(data)`: 데이터 갱신
- `_handle_plus()`: + 버튼 처리

---

### 11. `ui_code/ui/utils/common.py` (30줄)
**목적:** 공용 유틸리티 함수

**함수:**
- `_fill()`: UI 전체 너비/높이 채우기
- `_file_uri(path)`: 파일 경로를 URI로 변환
- `_fmt_status(v)`: 상태 코드 → 텍스트 변환
  ```python
  1: "EXIT", 2: "OFFLINE", 3: "IDLE", 4: "INTASK",
  5: "CHARGING", 6: "UPDATING", 7: "EXCEPTION"
  ```
- `_fmt_lift(v)`: Lift 상태 포맷 (Up/Down)

**상수:**
- `ASSET_DIR`: `platform_ext/resource` 경로

---

### 12. `ui_code/ui/scene/amr_3d.py` (330줄)
**목적:** Omniverse USD 기반 3D 로봇 렌더링

**좌표 변환:**
- mm ↔ stage units (메터 기준)
- Z-up vs Y-up 자동 감지
- Tilt, Yaw 보정

**모션 파라미터:**
- 이동 속도: 300 mm/s (조정 가능)
- 회전 속도: 360 deg/s
- 정지 오차: 0.01 units

**클래스:**
- `Amr3D`:
  - `init(amr_usd_path)`: 프로토타입 로드
  - `set_config()`: 좌표 변환 파라미터 설정
  - `set_motion()`: 모션 파라미터 설정
  - `update_robot(rid, x, y, yaw)`: 실시간 위치 갱신
  - `clear_robot(rid)`: 로봇 제거

**캐시:**
- `_pos_cache`: 마지막 위치
- `_yaw_cache`: 마지막 회전
- `_targets`: 목표 위치

---

### 13. `ui_code/ui/scene/linecar.py` (474줄)
**목적:** 3D 자동차 모델 색상 지정 및 재료 바인딩

**색상 팔레트:**
```python
Black, Blue, Red, White, Yellow (5색)
```

**클래스:**
- (함수 기반, 클래스 없음)

**주요 함수:**
- `_random_color()`: 무작위 색상 선택
- `_get_shader_from_look(stage, look_path)`: 셰이더 찾기
- `_set_albedo_on_look(stage, look_path, rgb)`: 알베도 색상 설정
- `_colorize_car(stage, car_path, looks_names)`: 자동차 색상 지정
- `_safe_compute_bound_material(prim)`: 안전한 재료 바인딩 조회 (버전 호환성)

---

### 14. `ui_code/ui/sections/top_bar.py` (73줄)
**목적:** 상단 메뉴바 UI

**구성:**
- 왼쪽: Automes 로고 + URL (클릭 가능)
- 중앙: "Meta Factory" 제목
- 오른쪽: 온도(21°C), 습도(63%) 표시

**함수:**
- `build_top_bar(self)`: UI 구성
- `open_automes_link()`: 웹사이트 열기

---

### 15. `ui_code/ui/sections/amr_panel.py` (18줄)
**목적:** AMR 카드 목록 패널 (좌측 나열)

**구성:**
- 좌측: 고정 너비(170px) 스크롤 영역
- 우측: Spacer (여백)

**함수:**
- `build_amr_panel(self)`: UI 구성

---

### 16. `ui_code/ui/sections/status_panel.py` (201줄)
**목적:** 상태 패널 (도넛 차트, 통계)

**시각화:**
- 도넛 차트 (Working/Waiting/Charging 비율)
- 색상:
  - Working: 주황색 (255, 170, 0)
  - Waiting: 파란색 (0, 123, 255)
  - Charging: 초록색 (0, 204, 102)

**함수:**
- `build_status_panel(self)`: UI 구성
- `_draw_donut()`: 도넛 차트 렌더링 (NumPy 기반)

---

### 17. `ui_code/ui/sections/bottom_bar.py` (113줄)
**목적:** 하단 제어 바 (버튼)

**버튼:**
- "AMR Control": AMR 제어 패널 열기
- "Chatbot": 챗봇 패널 열기
- "Pathfinder": 경로 계획 미니맵 열기
- "Body Data": 바디라인 데이터 패널 열기

**함수:**
- `build_bottom_bar(self)`: UI 구성
- `_init_mode_state()`: 모드 상태 초기화
- `_open_*_panel()`: 각 패널 오픈 함수

---

### 18. `ui_code/ui/sections/body_data_panel.py` (134줄)
**목적:** 바디라인 데이터 모니터링 대시보드

**테이블 구성:**
- Station, Body ID, Status, Welding Quality (%), Total Weight (kg), Process Time (sec)

**샘플 데이터:**
```python
(B01, BODY-00123, In Progress, 98.4%, 835.2 kg, 42.8 sec)
...
```

**클래스:**
- `BodyDataPanel`:
  - `show()`: UI 표시
  - `_build_table()`: 테이블 생성

---

## 📊 의존성 그래프

```
__init__.py (IExt 진입점)
├─ client.py (REST 클라이언트)
│  └─ Network.json 읽기
├─ main.py (UI 레이아웃)
│  ├─ top_bar.py
│  ├─ amr_panel.py
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
└─ common.py (공용 유틸)
   ├─ all panels
   └─ status_panel.py
```

---

## 🔄 데이터 흐름

### 1. 초기화 흐름
```
Omniverse Kit Launch
  ↓
extension.toml 로드
  ↓
__init__.py IExt.on_startup()
  ↓
Network.json 읽기
  ↓
DigitalTwinClient 생성
  ↓
HttpPinger 시작 (서버 상태 감지)
  ↓
main.py UiLayoutBase 초기화
  ↓
모든 UI 패널 생성
  ↓
폴링 시작 (0.5초 간격)
```

### 2. 실시간 업데이트 흐름
```
서버 데이터 수신 (0.5초 주기)
  ↓
DigitalTwinClient 콜백 (on_response)
  ↓
UI 큐에 작업 추가 (_ui_queue)
  ↓
메인 스레드에서 처리
  ↓
UI 모델 업데이트
  ↓
화면 렌더링
```

### 3. 명령 전송 흐름
```
사용자 버튼 클릭
  ↓
AMRControlPanel.show() → _send_command()
  ↓
DigitalTwinClient.request(dataType, params)
  ↓
서버로 HTTP 요청 전송
  ↓
응답 수신 (on_response 콜백)
  ↓
UI 갱신 (결과 표시)
```

---

## 🛠️ 확장 방법

### 새로운 패널 추가
```python
# 1. 새 파일 생성: ui_code/MyFeature/my_panel.py
class MyPanel:
    def __init__(self):
        self._win = None
    
    def show(self):
        if self._win:
            self._win.visible = True
            return
        self._win = ui.Window("My Panel", width=500, height=400)
        with self._win.frame:
            with ui.VStack():
                ui.Label("My Content")
    
    def update(self, data):
        # 데이터 갱신 로직

# 2. bottom_bar.py에 버튼 추가
def _open_my_panel():
    if not hasattr(self, "_my_panel") or self._my_panel is None:
        self._my_panel = MyPanel()
    self._my_panel.show()

ui.Button("My Feature", clicked_fn=_open_my_panel)
```

### 새로운 API 엔드포인트 추가
```python
# client.py에 메서드 추가
def get_my_data(self):
    return self.request("GetMyData")

# __init__.py에서 사용
def on_my_data_updated(name, params, response):
    self._ui_queue.append(lambda: self._update_my_panel(response))

self._client.add_on_response(on_my_data_updated)
```

---

## 🐛 디버깅 팁

- **로그 확인:** Omniverse Kit Console 열기 (Ctrl+``)
- **UI 안 보임:** `_kill_window()`로 중복 창 삭제
- **서버 연결 실패:** Network.json 경로 확인, HttpPinger 상태 로그 확인
- **스레드 오류:** UI 접근은 반드시 `_ui_queue`를 통해 메인 스레드에서만
- **성능 저하:** 폴링 주기 확인 (client.py의 `interval` 파라미터)

