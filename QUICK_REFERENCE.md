# Quick Reference Guide (빠른 참조)

## 🎯 자주 찾는 것들

### Q1. 서버 연결 설정을 변경하려면?
📁 **파일:** `platform_ext/config/Network.json`
```json
{
  "opServerIP": "127.0.0.1",        // ← 백엔드 서버 IP 변경
  "opServerPort": 49000,             // ← 포트 변경
  "https": false,                    // ← HTTPS 사용
  "baseUrl": "http://127.0.0.1:49000/",  // ← 또는 직접 URL 지정
  "mapCode": "GBFTT"                 // ← 맵 파일 코드
}
```

### Q2. 새로운 AMR 명령을 추가하려면?
**파일:** `ui_code/AMR/amr_control_panel.py`
```python
# 1. 명령 목록에 추가 (줄 6-7)
_COMMANDS = ["Move", "Rack Move", "Pause", "Resume", "Cancel", "MyNewCommand"]

# 2. dataType 매핑 추가 (줄 8-13)
_DATATYPE_MAP = {
    "Move":       "ManualMove",
    "Rack Move":  "ManualRackMove",
    "Pause":      "AMRPause",
    "Resume":     "AMRResume",
    "Cancel":     "MissionCancel",
    "MyNewCommand": "MyDataType",  # ← 추가
}

# 3. 파라미터 필드 추가 (선택사항, show() 메서드에서)
```

### Q3. 새로운 패널을 추가하려면?
**단계:**
1. `ui_code/{Module}/` 폴더 생성
2. `my_panel.py` 작성
   ```python
   import omni.ui as ui
   
   class MyPanel:
       def __init__(self):
           self._win = None
       
       def show(self):
           if self._win:
               self._win.visible = True
               return
           self._win = ui.Window("My Panel", width=500, height=400)
           with self._win.frame:
               ui.Label("Hello World")
   ```
3. `bottom_bar.py`에 버튼 추가
   ```python
   def _open_my_panel():
       if not hasattr(self, "_my_panel"):
           self._my_panel = MyPanel()
       self._my_panel.show()
   
   ui.Button("My Feature", clicked_fn=_open_my_panel)
   ```

### Q4. 로봇 좌표 변환 기준을 변경하려면?
**파일:** `ui_code/ui/scene/amr_3d.py`
```python
# __init__() 메서드의 파라미터 (줄 21-27)
self._TILT_X_DEG = 0.0      # X축 기울기 (degree)
self._YAW_SIGN   = +1.0     # 회전 방향 부호 (+1 또는 -1)
self._YAW_OFFSET = 0.0      # 회전 오프셋 (degree)
self._SIGN_V     = +1.0     # V(Y) 방향 부호
self._SCALE_CORR = 1.0      # 스케일 보정값
self._OFFSET_U   = 0.0      # U(X) 오프셋
self._OFFSET_V   = 0.0      # V(Y) 오프셋

# 또는 set_config() 메서드 호출
amr_3d.set_config(
    tilt_x=90.0,
    yaw_sign=-1.0,
    scale_corr=1.5
)
```

### Q5. 화면 레이아웃을 변경하려면?
**상단바:** `ui_code/ui/sections/top_bar.py` (높이: 120px)
**좌측 패널:** `ui_code/ui/sections/amr_panel.py` (너비: 170px)
**우측 패널:** `ui_code/ui/sections/status_panel.py` (너비: 350px)
**하단바:** `ui_code/ui/sections/bottom_bar.py` (높이: 60px)

예) 좌측 패널 너비 변경:
```python
# amr_panel.py, 줄 15
with ui.VStack(width=170):  # ← 이 값 변경
```

### Q6. 상태 코드를 추가하려면?
**파일:** `ui_code/ui/utils/common.py`
```python
_STATUS_MAP = {
    1: "EXIT", 2: "OFFLINE", 3: "IDLE", 4: "INTASK",
    5: "CHARGING", 6: "UPDATING", 7: "EXCEPTION",
    8: "MY_STATUS",  # ← 추가
}
```

### Q7. 폴링 주기를 변경하려면?
**파일:** `ui_code/client.py`
```python
def __init__(self, ..., interval: float = 0.5):  # ← 기본값 0.5초
    self._interval = max(0.05, float(interval))   # 최소: 0.05초
```

또는 `__init__.py`에서:
```python
self._client = DigitalTwinClient(interval=1.0)  # 1초로 변경
```

### Q8. 색상을 변경하려면?
**ABGR 포맷 사용:**
- `0xFFFFFFFF`: 흰색
- `0xFF0000FF`: 빨간색
- `0xFF00FF00`: 녹색
- `0xFFFFFF00`: 파란색
- `0xFF00AAFF`: 주황색
- `0xFF00CC66`: 초록색

예) `ui_code/ui/sections/top_bar.py`
```python
ui.Label("Title", style={"color": 0xFF0000FF})  # 빨간색
```

### Q9. 폰트를 변경하려면?
**파일:** `ui_code/ui/sections/body_data_panel.py`
```python
# 한글 폰트 (기본)
self.font_bold = "${fonts}/static/NotoSansKR-Bold.ttf"
self.font_regular = "${fonts}/static/NotoSansKR-Regular.ttf"

# 시스템 폰트로 변경
self.font_bold = "${app}/resources/fonts/OpenSans-SemiBold.ttf"
self.font_regular = "${app}/resources/fonts/OpenSans-Regular.ttf"
```

### Q10. 맵 파일을 변경하려면?
**파일:** `platform_ext/config/Network.json`
```json
{
  "mapCode": "E_Comp"  // ← GBFTT에서 E_Comp로 변경
}
```

또는 직접 경로 지정 (`ui_code/AMR/amr_pathfinder_panel.py`):
```python
PathFinderPanel(map_json_path="/path/to/my_map.json")
```

---

## 📚 함수 참조

### UI 헬퍼 함수 (common.py)

| 함수 | 입력 | 출력 | 설명 |
|------|------|------|------|
| `_fill()` | - | ui.Fraction(1) | 전체 너비/높이 채우기 |
| `_file_uri(path)` | Path | str | 파일 경로 → URI 변환 |
| `_fmt_status(v)` | int/str | str | 상태 코드 → 텍스트 |
| `_fmt_lift(v)` | bool/int | str | Lift 상태 → Up/Down |

### REST API (client.py)

| 메서드 | 설명 | 예시 |
|--------|------|------|
| `start_polling()` | 폴링 시작 | `client.start_polling()` |
| `stop_polling()` | 폴링 중지 | `client.stop_polling()` |
| `request(name, **params)` | 동기 요청 | `client.request("GetAMRInfo")` |
| `add_on_alive_change(fn)` | 연결 상태 콜백 등록 | `client.add_on_alive_change(lambda alive: ...)` |
| `add_on_response(fn)` | 응답 콜백 등록 | `client.add_on_response(lambda n,p,r: ...)` |
| `add_on_error(fn)` | 에러 콜백 등록 | `client.add_on_error(lambda e,n,p: ...)` |

### 3D 렌더링 (amr_3d.py)

| 메서드 | 설명 |
|--------|------|
| `init(amr_usd_path)` | USD 모델 로드 및 초기화 |
| `set_config(**kwargs)` | 좌표 변환 파라미터 설정 |
| `set_motion(**kwargs)` | 모션 파라미터 설정 (속도, 정지 오차) |
| `update_robot(rid, x, y, yaw)` | 로봇 위치/회전 업데이트 |
| `clear_robot(rid)` | 로봇 제거 |
| `update()` | 프레임 업데이트 (자동 호출) |

---

## 🔄 일반적인 작업

### 작업 1: 새로운 서버 API 통합

**Step 1:** `client.py`에 메서드 추가
```python
def get_my_data(self):
    """내 데이터 조회"""
    return self.request("GetMyData")
```

**Step 2:** `__init__.py`에서 콜백 등록
```python
def _on_response(name, params, response):
    if name == "GetMyData":
        self._ui_queue.append(lambda: self._update_my_panel(response))

self._client.add_on_response(_on_response)
```

**Step 3:** 패널에서 사용
```python
data = self._client.get_my_data()
self.update(data)
```

### 작업 2: 실시간 데이터 폴링

```python
# 1. 데이터 수신 후 모델 업데이트
def _on_response(name, params, response):
    if name == "AMRInfo":
        for amr_id, amr_data in response.items():
            self._amr_latest[amr_id] = amr_data

# 2. UI에서 데이터 표시
for amr_id, data in self._amr_latest.items():
    status = _fmt_status(data.get("status"))
    battery = data.get("battery", 0.0)
    # UI 업데이트
```

### 작업 3: 백그라운드 스레드 안전하게 사용

```python
# ❌ 잘못된 방법 (UI 스레드가 아님)
def _thread_func():
    self.m_model.set_value("value")  # 💥 오류!

# ✅ 올바른 방법
def _thread_func():
    self._ui_queue.append(
        lambda: self.m_model.set_value("value")
    )

# UI 큐 처리 (메인 스레드에서)
while self._ui_queue:
    fn = self._ui_queue.popleft()
    fn()
```

### 작업 4: 색상에 따른 상태 표시

```python
def _get_status_color(status: str) -> int:
    if status == "INTASK":
        return 0xFF00AAFF  # 주황
    elif status == "WAITING":
        return 0xFF007BFF  # 파랑
    elif status == "CHARGING":
        return 0xFF00CC66  # 초록
    else:
        return 0xFFFFFFFF  # 흰색

ui.Label("●", style={"color": _get_status_color("INTASK")})
```

### 작업 5: 동적 UI 요소 추가/제거

```python
# VStack에 동적으로 아이템 추가
with self._v_stack:
    for item in items:
        ui.Label(item["name"])

# 기존 아이템 제거 후 재렌더링
self._v_stack.clear_children()  # 또는
# 부모 Frame 전체 삭제 후 재구성
self._frame.clear_children()
```

---

## 🐛 일반적인 오류 및 해결

| 오류 | 원인 | 해결 |
|------|------|------|
| "FileNotFoundError: Network.json" | 경로 잘못됨 | `c:\omniverse_exts\platform_ext\config\Network.json` 확인 |
| "ConnectionError" | 서버 연결 실패 | Network.json의 IP/포트 확인, 방화벽 확인 |
| "ModuleNotFoundError: requests" | 라이브러리 미설치 | `pip install requests` 또는 extension.toml 확인 |
| UI 창이 안 보임 | 중복 창 존재 | `_kill_window()` 메서드로 기존 창 삭제 |
| 폰트가 깨짐 | 폰트 파일 없음 | `platform_ext/fonts/static/` 확인, fallback 폰트 사용 |
| 3D 모델 안 보임 | USD 파일 로드 실패 | `AMR.usd` 경로 확인, 파일 손상 체크 |
| 폴링이 안 됨 | 스레드 미시작 | `client.start_polling()` 호출 확인 |
| UI 업데이트 안 됨 | 메인 스레드 접근 오류 | `_ui_queue`를 통해 접근 |

---

## 📞 디버깅 팁

### Omniverse Console 출력 확인
```python
import carb
carb.log_info(f"[MyPlugin] Debug message: {var}")
carb.log_warn(f"[MyPlugin] Warning: {var}")
carb.log_error(f"[MyPlugin] Error: {var}")
```

### 네트워크 요청 로깅
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# client.py에서 자동 로깅됨
```

### UI 성능 모니터링
```python
import time
start = time.time()
# ... UI 작업 ...
elapsed = time.time() - start
carb.log_info(f"UI update took {elapsed:.3f}s")
```

### 데이터 구조 검증
```python
import json
carb.log_info(f"AMR Data: {json.dumps(self._amr_latest, indent=2)}")
```

---

## 🚀 배포 체크리스트

- [ ] Network.json 설정 확인 (IP, 포트, mapCode)
- [ ] extension.toml 버전 업데이트
- [ ] 모든 import 경로 확인
- [ ] 폰트/이미지 리소스 포함
- [ ] Python 파일 문법 검사
- [ ] 주석/문서 업데이트
- [ ] 보안: 민감 정보 제거 (예: Network.json)
- [ ] 불필요한 캐시 파일 제거 (`__pycache__`, `.pyc`)
- [ ] 최종 테스트

---

## 📖 추가 리소스

- **Omniverse Kit Documentation:** https://docs.omniverse.nvidia.com/kit/docs/
- **Omni.UI Tutorial:** https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/
- **USD Documentation:** https://graphics.pixar.com/usd/docs/
- **Python Requests Library:** https://docs.python-requests.org/

