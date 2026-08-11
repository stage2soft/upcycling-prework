# 업사이클링 대상 파일 선별 프로그램

## 1. 목적

매니저가 로컬 데이터셋의 복수 원천데이터와 라벨링데이터를 자동 매칭하고, 미리보기 가능한 원천 이미지가 있으면 라벨과 함께 렌더링해 검토한 뒤 업사이클링 대상을 선별하는 독립 실행형 도구입니다.

프로덕션 `api`와 `frontend`에 구현된 파일 매핑, JSON 라벨 파싱, 이미지/BBox 렌더링 방식을 참고하되 다음 특성에 맞게 별도 구현합니다.

- 인증 없이 로컬 Docker 환경에서 실행
- SQLite 데이터베이스를 사용하고 호스트 볼륨에 영속화
- 마운트된 데이터셋 디렉터리만 읽고 쓰기
- 선별 이력과 파일 식별자를 저장해 중복 선별 방지
- 선별 완료 파일을 원본 유지 상태로 지정된 출력 디렉터리에 복사

## 2. 범위

### 포함

- 원천데이터 및 라벨링데이터 디렉터리 탐색
- 파일명 또는 JSON 필드값 기반 자동 매칭
- 매칭 성공·실패·충돌 결과 확인
- 원천 이미지가 포함된 경우 라벨 오버레이 렌더링
- 이미지 외 오브젝트 파일을 포함한 복수 원천데이터 묶음 관리
- 대상 선택·제외 및 선택 취소
- 선택 파일 복사와 SQLite 이력 저장
- 상태·검색 조건별 후보 목록 조회
- 선별 결과 엑셀 다운로드
- Docker Compose 기반 실행과 데이터 영속화

### 제외

- 로그인, 사용자 및 역할 관리
- 프로젝트·작업자 배정·검수 워크플로
- NAS 브라우저 전체 기능
- 원격 스토리지 및 클라우드 업로드
- 프로덕션 데이터베이스 연동

## 3. 기술 구성

### Backend

- Python 3.13
- FastAPI
- SQLAlchemy 2.x
- SQLite3
- Pydantic Settings
- Uvicorn

### Frontend

- Vue 3 Composition API
- TypeScript
- Vite
- Vuetify 3

### Runtime

- Docker Compose
- 기본 접속 주소
  - Frontend: `http://localhost:18081`
  - Backend API: `http://localhost:18000`
  - OpenAPI: `http://localhost:18000/docs`

## 4. 디렉터리 및 볼륨

원천데이터와 라벨데이터를 함께 포함하는 최상위 폴더 하나만 컨테이너에 마운트합니다. 실제 원천·라벨 하위 폴더는 프로그램의 `데이터 및 매칭 설정`에서 탐색하고 선택하며 SQLite에 상대 경로로 저장합니다.

원천·라벨 입력 폴더는 `/raw`, `/label` 또는 특정 이름으로 고정하지 않습니다. 최초 실행 시 두 폴더는 미선택 상태이며, 매니저가 마운트된 `데이터 루트` 최상위에서 각각 독립적으로 선택해야 스캔할 수 있습니다.

| 용도 | 환경 변수 | 컨테이너 기본 경로 | 권한 |
|---|---|---|---|
| 통합 데이터 최상위 폴더 | `DATA_ROOT_PATH` | `/data/root` | 읽기 전용 |
| 선별 결과 | `SELECTED_DATA_PATH` | `/data/selected` | 읽기/쓰기 |
| SQLite/애플리케이션 데이터 | `APP_DATA_PATH` | `/app/data` | 읽기/쓰기 |

Compose는 위 호스트 경로를 Backend 환경 변수에도 함께 전달합니다. `Volumes` 팝업에서 각 볼륨의 호스트 경로와 컨테이너 경로를 구분해 확인할 수 있습니다.

권장 호스트 구조는 원천·라벨 볼륨과 애플리케이션 출력·DB 볼륨을 분리합니다.

```text
host-datasets/                   # DATA_ROOT_PATH로 마운트할 최상위 폴더
├── raw-root/                    # 프로그램에서 원천 폴더로 선택
│   ├── region-a/images/
│   └── region-a/objects/
└── labeled-root/                # 프로그램에서 라벨 폴더로 선택
    └── region-a/labels/

prework-runtime/                 # 별도 위치 또는 별도 볼륨
├── selected/
└── app-data/
    └── prework.db
```

`host-datasets` 하나를 마운트하고 `raw-root`, `labeled-root`는 프로그램에서 선택합니다. `selected`와 `app-data`는 각각 별도 bind mount 또는 named volume으로 마운트하여 데이터 루트 교체와 무관하게 선별 결과와 DB가 유지되도록 합니다.

예를 들어 호스트의 `raw-root/region-a/images/scene.png`는 컨테이너에서 `/data/root/raw-root/region-a/images/scene.png`로 보입니다. 프로그램에서 `raw-root`를 원천 폴더로 선택하면 원본을 유지하면서 그 폴더 기준 상대 경로를 그대로 보존하여 복사합니다.

```text
selected/
├── raw-root/
│   ├── region-a/images/scene.png
│   └── region-a/objects/scene.pcd
└── labeled-root/
    └── region-a/labels/scene.json
```

선별 결과에는 `selection_id` 폴더나 `raw/`, `labeled/` 같은 인위적인 그룹 폴더를 추가하지 않습니다. `selected` 아래의 경로는 `DATA_ROOT_PATH` 기준 원본 상대 경로와 완전히 같으며, 매니저가 선택한 원천·라벨 폴더의 상위 구조도 그대로 유지합니다. 같은 경로의 파일이 이미 존재하면 즉시 덮어쓰지 않고, 충돌 경로를 표시한 후 매니저에게 덮어쓸지 확인합니다.

## 5. 지원 파일

### 원천데이터

- 원천데이터는 이미지 한 개로 제한하지 않으며 하나의 라벨이 복수 원천 파일을 참조할 수 있습니다.
- 이미지 미리보기 지원: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`
- 오브젝트·센서 파일 예시: `.pcd`, `.ply`, `.obj`, `.bin`, `.las`, `.laz`, `.npy`
- 그 밖의 일반 파일도 매칭·목록 표시·복사 대상에 포함할 수 있으며, 브라우저 미리보기를 지원하지 않으면 파일 정보만 표시합니다.

### 라벨링데이터

- `.json`

탐색은 각 마운트 상위 폴더 이하를 재귀적으로 수행합니다. 숨김 파일, 심볼릭 링크, 임시 파일은 기본적으로 제외합니다.

## 6. 파일 매칭 규칙

매칭 설정은 SQLite에 저장하며 다음 스캔부터 재사용합니다.

### 6.1 파일명 매칭 `file_name`

- 원천 파일과 라벨 JSON의 파일명에서 확장자를 제거한 stem을 비교합니다.
- 비교 시 영문 대소문자를 구분하지 않습니다.
- 같은 stem을 가진 이미지·오브젝트·센서 파일은 하나의 원천데이터 묶음으로 매칭합니다.
- 예시: `scene_001.png` + `scene_001.pcd` ↔ `scene_001.json`
- 라벨 파일의 상대 상위 경로와 대응하는 원천 상대 상위 경로를 우선 비교하고, 경로 기준으로 결정할 수 없을 때 전체 마운트에서 stem을 비교합니다.
- 서로 다른 원천 디렉터리에 동일한 stem 묶음이 여럿 존재해 단일 묶음을 결정할 수 없으면 `conflict`로 처리합니다.

### 6.2 JSON 참조키 매칭 `json_ref_key`

- 라벨 JSON에서 설정한 dot path의 문자열 또는 문자열 배열 값을 읽습니다.
- 예시 키: `data_key`, `image.file_name`, `annotation.raw_file`
- 단일 문자열은 원천 1개 이상을 대표하는 참조로, 문자열 배열은 복수 원천 참조로 처리합니다.
- 각 JSON 값이 경로이면 마운트 루트 기준 상대 경로 일치를 우선하고, 일치하지 않으면 마지막 파일명과 stem 순서로 비교합니다.
- 배열의 참조 순서는 저장하며 중복 참조는 제거합니다.
- 모든 참조가 정확히 원천 파일 또는 원천 묶음에 대응해야 `matched`입니다.
- 참조 중 하나라도 누락되면 `unmatched`, 하나의 참조가 서로 다른 원천 경로 여러 개에 대응하면 `conflict`로 처리합니다.
- 키 누락, 값 타입 오류, JSON 파싱 오류는 `error`로 기록합니다.

복수 참조 예시:

```json
{
  "source_files": [
    "region-a/images/scene_001.png",
    "region-a/objects/scene_001.pcd",
    "region-a/sensors/scene_001.bin"
  ]
}
```

이 경우 `json_ref_key`는 `source_files`로 설정하며 세 원천 파일 전체가 하나의 선별 후보에 포함됩니다.

### 6.3 매칭 상태

| 상태 | 의미 |
|---|---|
| `matched` | 원천 1개 이상과 라벨 1개가 정상 매칭됨 |
| `unmatched` | 대응 파일을 찾지 못함 |
| `conflict` | 동일 키에 원천 또는 라벨 후보가 여러 개 존재함 |
| `error` | JSON 파싱, 파일 접근 등의 오류 발생 |

스캔은 파일을 이동하지 않습니다. 기존 후보는 경로와 fingerprint를 기준으로 갱신하고, 이미 `selected` 상태인 항목은 다시 후보로 등록하지 않습니다.

## 7. 선별 상태와 처리 흐름

### 7.1 후보 상태

| 상태 | 설명 |
|---|---|
| `pending` | 검토 대기 |
| `selected` | 업사이클링 대상으로 선택 및 복사 완료 |
| `rejected` | 대상에서 제외 |
| `move_failed` | 선택했으나 파일 복사 실패(호환성을 위해 기존 상태 코드 유지) |

### 7.2 선별 처리

1. 매니저가 `matched` 후보를 선택합니다.
2. Backend가 묶음에 포함된 모든 원천 파일 및 라벨 파일의 존재 여부와 경로 안전성을 다시 검증합니다.
3. 출력 디렉터리 충돌 여부를 확인합니다.
4. 같은 경로의 파일이 있으면 충돌 목록을 보여주고 덮어쓰기 여부를 확인합니다.
5. 모든 원천 파일을 `selected/{DATA_ROOT_PATH 기준 원본 상대 경로}`로 복사합니다.
6. 라벨 파일도 동일한 경로 규칙으로 복사합니다.
7. 묶음의 모든 파일 복사가 성공한 경우에만 상태를 `selected`로 확정합니다.
8. 복사 도중 실패하면 이번 요청에서 생성한 파일을 제거합니다. 덮어쓰기 중이었다면 임시 백업으로 기존 파일을 복원하고, 원본은 그대로 유지한 뒤 상태를 `move_failed`로 기록합니다.

`rejected`는 파일을 복사하지 않습니다. `selected` 완료 후에도 원본은 유지되며 UI 미리보기는 선별 결과 복사본을 우선 사용합니다.

## 8. 중복 방지

후보 묶음마다 다음 값을 이용해 fingerprint를 생성합니다. 원천 파일 항목은 상대 경로로 정렬한 후 결합하여 파일 탐색 순서가 달라도 같은 fingerprint가 생성되도록 합니다.

```text
sha256(sorted(raw_relative_path + raw_size + raw_mtime ...) + label_relative_path + label_size + label_mtime)
```

- fingerprint는 데이터베이스에서 unique로 관리합니다.
- 같은 복수 원천·라벨 묶음을 반복 스캔해도 후보가 중복 생성되지 않습니다.
- 이미 선택 완료된 fingerprint는 다시 선별할 수 없습니다.
- 파일 내용이나 수정 시간이 바뀌면 새 버전 후보로 인식할 수 있습니다.

## 9. 라벨 렌더링

Frontend는 후보의 복수 원천 파일 중 미리보기 가능한 대표 이미지를 선택해 SVG 오버레이를 표시합니다. 프로덕션의 다음 구현 방식을 참고합니다.

- `frontend/src/components/labeling/ImageViewer.vue`
- `frontend/src/components/labeling/SourceRenderingViewer.vue`
- `frontend/src/components/labeling/sourceLabelAdapters.ts`

대표 이미지는 JSON 참조 배열 순서상 첫 번째 이미지 파일을 우선하고, 없으면 원천 묶음의 상대 경로 정렬상 첫 번째 이미지 파일을 사용합니다. 이미지가 없는 오브젝트 전용 묶음은 파일 목록과 메타데이터를 표시하며 선별은 계속할 수 있습니다.

초기 지원 라벨 어댑터 우선순위:

1. `objects[].annotation.position + rotation_quaternion + size` 3D cuboid 형식
2. `data_key + objects[].annotation` 중첩 polygon 형식
3. `objects[].bbox` 형식 (`[x, y, width, height]`)
4. COCO 계열 `annotations[].bbox` 형식

3D cuboid는 quaternion으로 yaw 회전을 계산하고 XY 평면 Top View의 회전 BBox로 렌더링합니다. 원천 이미지는 메인 화면에 유지하고 Top View를 우측 하단 오버레이로 함께 표시합니다. 별도 calibration 정보가 없으면 카메라 좌표축과 수평 FOV 90°를 가정한 pinhole 모델로 이미지 위에도 2D BBox를 투영하며, 라벨 `meta.size`와 이미지 해상도가 다르면 로딩된 원천 이미지의 실제 해상도를 우선합니다.

예시 우선 지원 형식:

```json
{
  "data_key": "L20220908_132432_45.png",
  "objects": [
    {
      "class_name": "No Parking Area",
      "annotation": [[[{ "x": 3894, "y": 1117 }, { "x": 3896, "y": 1125 }]]],
      "properties": {
        "property_name": "No Parking Area Property",
        "option_name": "occupied by other objects"
      }
    }
  ],
  "meta": {
    "size": { "width": 4032, "height": 3040 }
  }
}
```

렌더러 요구사항:

- 이미지 로딩 및 라벨 JSON 로딩 오류 표시
- 복수 원천 파일 목록과 파일 유형 표시 및 대표 이미지 전환
- 브라우저에서 렌더링할 수 없는 오브젝트 파일의 경로·크기·수정 시간 표시
- 이미지 크기 또는 라벨 `meta.size`를 SVG viewBox로 사용
- polygon과 bbox 표시
- BBox 색상 변경
- 마우스 휠 확대/축소와 드래그 이동
- 객체 클릭 시 클래스명, 속성, 좌표 정보 표시
- 지원하지 않는 라벨 형식은 이미지 원본과 오류 메시지를 표시하고 선별 판단은 가능하게 유지

## 10. 데이터 모델

### `app_settings`

- `id`
- `mapping_strategy`: `file_name | json_ref_key`
- `json_ref_key`
- `raw_relative_path`: `DATA_ROOT_PATH` 기준 선택한 원천 폴더
- `labeled_relative_path`: `DATA_ROOT_PATH` 기준 선택한 라벨 폴더
- `created_at`, `updated_at`

### `selection_candidates`

- `id`
- `fingerprint` (unique)
- `match_key`
- `match_status`
- `selection_status`
- `error_message`
- `created_at`, `updated_at`, `decided_at`

### `selection_candidate_files`

- `id`
- `candidate_id` (FK)
- `file_group`: `raw | labeled`
- `reference_order`: JSON 복수 참조 순서 또는 파일명 묶음 정렬 순서
- `original_relative_path`: 각 마운트 상위 폴더 기준 상대 경로
- `selected_relative_path`: `SELECTED_DATA_PATH` 기준 복사 후 상대 경로
- `extension`
- `size`
- `mtime`
- `is_previewable_image`

후보 1개는 `raw` 파일 1개 이상과 `labeled` JSON 파일 1개를 가집니다. 파일별 레코드를 분리하여 복수 원천 참조와 원본 상위 폴더 구조 보존을 명시적으로 관리합니다.

SQLite 파일은 `APP_DATA_PATH/prework.db`에 저장하며 컨테이너 재시작·재생성 후에도 유지되어야 합니다.

## 11. Backend API

기본 prefix: `/api`

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/health` | 상태 확인 |
| `GET` | `/api/settings` | 매칭 설정 조회 |
| `PUT` | `/api/settings` | 매칭 설정 저장 |
| `GET` | `/api/directories` | 데이터 루트 이하 폴더 탐색 |
| `GET` | `/api/volumes` | Volume 마운트 및 선택 폴더 상태 조회 |
| `POST` | `/api/scan` | 볼륨 재탐색 및 매칭 결과 갱신 |
| `GET` | `/api/candidates` | 후보 목록 조회 및 페이지네이션 |
| `GET` | `/api/candidates/{id}` | 후보 상세 및 라벨 JSON 조회 |
| `POST` | `/api/candidates/{id}/decision` | `selected` 또는 `rejected` 결정 |
| `POST` | `/api/candidates/{id}/reset` | `rejected` 항목을 `pending`으로 복구 |
| `GET` | `/api/files/{group}` | 미리보기 파일 스트리밍 (`raw`, `labeled`, `selected`) |
| `GET` | `/api/selections/export.xlsx` | 선별 결과 Excel(`.xlsx`) 다운로드 |

### 후보 목록 필터

- `selection_status`: `pending | selected | rejected | move_failed`
- `match_status`: `matched | unmatched | conflict | error`
- `search`: 파일명 또는 매칭 키
- `page`, `page_size`

### 주요 응답 원칙

- 목록 응답은 `results`, `count`, `page`, `page_size`, `total_pages`를 포함합니다.
- 파일 시스템 오류는 사용자 메시지와 내부 오류 코드를 분리합니다.
- API 응답에 호스트 절대 경로를 노출하지 않고 상대 경로만 반환합니다.

### Excel 반출 형식

워크북은 최소 두 시트를 포함합니다.

- `선별 결과`: 후보별 한 행
  - selection ID, 매칭 키, 매칭 방식, 선별 상태, 원천 파일 수, 원천 상대 경로 목록, 라벨 상대 경로, 결정 일시
- `파일 목록`: 후보에 포함된 파일별 한 행
  - selection ID, 파일 그룹, 참조 순서, 원본 상대 경로, 복사 후 상대 경로, 확장자, 크기, 수정 시간

복수 원천 경로는 `선별 결과` 시트에서 줄바꿈으로 표현하고, 자동 필터·헤더 고정·적정 열 너비를 적용합니다.

## 12. Frontend 화면

단일 선별 워크스페이스로 구성합니다.

### 상단 도구 영역

- Volume 마운트 현황 버튼
- 재스캔 버튼 및 진행 상태
- 선별 결과 Excel 다운로드
- 전체·대기·선택·제외 건수 요약

### 좌측 후보 목록

- `선별 후보` 아래에 상시 표시되는 데이터 및 매칭 설정
- `DATA_ROOT_PATH` 기준 원천·라벨 폴더 선택, 매칭 방식 및 JSON 참조키 저장 후 즉시 재스캔
- 상태 필터
- 매칭 상태 필터
- 파일명 검색
- 서버 페이지네이션
- 매칭 상태 및 선별 상태 표시
- 이미 선택된 항목의 중복 선택 비활성화

### 중앙 렌더링 뷰어

- 복수 원천 파일 목록, 대표 이미지와 라벨 overlay
- 확대/축소, 드래그 이동, 화면 맞춤
- BBox 색상 설정
- 객체 선택 및 정보 overlay
- 원천/라벨 로딩 오류 알림

### 우측 상세 및 결정 영역

- 모든 원천 파일·라벨 파일의 상대 경로
- 원천 파일과 라벨 파일 클릭 시 이미지·JSON 미리보기 팝업
- 이미지가 아닌 원천 파일도 UTF-8 또는 CP949 텍스트로 해석 가능하면 최대 512KB까지 텍스트 뷰어로 표시
- 매칭 키와 매칭 방식
- 파일별 유형, 크기 및 수정 시간
- JSON 원문 보기
- `대상 선택`, `제외`, `제외 취소` 버튼
- 파일 복사 성공·실패 결과 표시

## 13. 안전 조건

- API가 접근 가능한 경로는 설정된 세 개 데이터 루트 하위로 제한합니다.
- `..`, 절대 경로, 심볼릭 링크를 통한 루트 이탈을 거부합니다.
- 출력 파일을 임의로 덮어쓰지 않습니다.
- 선별 결정 API는 같은 요청이 반복되어도 파일을 다시 복사하지 않는 idempotent 동작을 보장합니다.
- SQLite 쓰기와 파일 복사 순서를 관리하고 실패 상태를 기록합니다.
- 로컬 전용 도구이므로 Docker 포트는 기본적으로 `127.0.0.1`에만 바인딩합니다.

## 14. Docker Compose 요구사항

`prework.compose.yaml`은 다음 서비스를 정의합니다.

- `backend`
  - 통합 데이터 최상위 폴더, 선별 결과, SQLite용 애플리케이션 데이터의 세 볼륨을 각각 마운트
  - `/health` healthcheck
  - `${PREWORK_BACKEND_PORT:-18000}:8000`
- `frontend`
  - 정적 SPA 제공
  - `/api` 요청을 backend로 reverse proxy
  - backend healthcheck 이후 시작
  - `${PREWORK_FRONTEND_PORT:-18081}:80`

### 14.1 GitHub에서 내려받아 실행

실행 PC에는 Git, Docker Engine, Docker Compose가 설치되어 있어야 합니다. 다음 GitHub 저장소를 복제한 뒤 저장소 루트에서 실행합니다.

```bash
git clone https://github.com/stage2soft/upcycling-prework.git
cd upcycling-prework
```

예제 설정을 복사한 뒤 호스트 경로와 포트를 저장소 루트의 `.env`에 설정합니다. `.env`는 Git 추적 대상에서 제외되어 있습니다.

```bash
cp .env.example .env
```

```dotenv
DATA_ROOT_PATH=/absolute/path/datasets
SELECTED_DATA_PATH=/absolute/path/prework-runtime/selected
APP_DATA_PATH=/absolute/path/prework-runtime/app-data
PREWORK_FRONTEND_PORT=18081
PREWORK_BACKEND_PORT=18000
```

출력 및 애플리케이션 데이터 폴더를 먼저 생성합니다.

```bash
mkdir -p /absolute/path/prework-runtime/selected
mkdir -p /absolute/path/prework-runtime/app-data
```

GitHub에서 받은 소스로 이미지를 빌드하고 서비스를 시작합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml up -d --build
docker compose --env-file .env -f prework.compose.yaml ps
```

정상 상태가 확인되면 `http://localhost:18081`에 접속합니다. Backend 상태는 `http://localhost:18000/health`, API 문서는 `http://localhost:18000/docs`에서 확인할 수 있습니다. 최초 접속 후 좌측 `데이터 및 매칭 설정`에서 `DATA_ROOT_PATH` 이하의 원천데이터 폴더와 라벨데이터 폴더를 각각 선택합니다.

기본 포트가 이미 사용 중이면 실행 시 변경할 수 있습니다.

```bash
PREWORK_FRONTEND_PORT=18082 PREWORK_BACKEND_PORT=18002 \
docker compose --env-file .env -f prework.compose.yaml up -d --build
```

종료:

```bash
docker compose --env-file .env -f prework.compose.yaml down
```

`down -v`는 SQLite 영속 데이터 삭제 가능성이 있으므로 사용하지 않습니다.

### 14.2 GitHub 변경사항으로 업데이트

운영 데이터를 보존한 상태에서 소스를 갱신합니다.

```bash
cd upcycling-prework
git pull --ff-only
docker compose --env-file .env -f prework.compose.yaml up -d --build
```

`SELECTED_DATA_PATH`와 `APP_DATA_PATH`가 기존 호스트 폴더를 계속 가리키면 업데이트 후에도 선별 파일과 SQLite 이력이 유지됩니다.

GitHub에는 애플리케이션 소스와 Compose 설정만 저장합니다. `.env`, 원천·라벨 데이터, 선별 결과 및 SQLite 운영 데이터는 저장소 외부에 유지합니다.

## 15. 프로덕션 구현 참조 범위

| 기능 | 참조 파일 |
|---|---|
| 파일명/JSON 키 매칭 | `api/app/routers/nas.py` |
| 파일 매칭 모델 | `api/app/models/dataset.py`의 `DatasetFileLink` |
| 매핑 설정 UI | `frontend/src/components/AutoMatchSettingsDrawer.vue` |
| 업로드/매칭 결과 UI | `frontend/src/views/DataUploadView.vue` |
| 이미지 및 BBox 뷰어 | `frontend/src/components/labeling/ImageViewer.vue` |
| 라벨 fallback 어댑터 | `frontend/src/components/labeling/sourceLabelAdapters.ts` |

프로덕션 코드를 그대로 의존하지 않고 prework 내부에 필요한 최소 기능을 독립적으로 구현합니다.

## 16. 완료 기준

- [x] `docker compose up --build` 실행 구성이 제공된다.
- [x] SQLite 파일이 호스트 볼륨에 생성되고 재시작 후 데이터가 유지된다.
- [x] 파일명 매칭과 JSON 참조키 매칭이 각각 동작한다.
- [x] 매칭 성공·실패·충돌 건수를 확인할 수 있다.
- [x] 복수 원천 참조가 하나의 후보 묶음으로 매칭된다.
- [x] 대표 원천 이미지가 있으면 라벨 overlay를 확인할 수 있고, 이미지 외 오브젝트 파일도 목록에서 확인할 수 있다.
- [x] 선택 시 원본을 유지하고 모든 원천·라벨 파일이 선택 폴더 기준 상대 경로를 유지해 출력 위치로 복사된다.
- [x] 동일 파일 묶음을 다시 스캔해도 중복 후보가 생성되지 않는다.
- [x] 선택·제외 상태별 목록 필터와 서버 페이지네이션이 동작한다.
- [x] 선별 결과를 Excel(`.xlsx`)로 다운로드할 수 있다.
- [x] 경로 이탈과 기존 파일 덮어쓰기가 차단된다.
- [x] Backend 자동 테스트와 Frontend 프로덕션 빌드가 통과한다.

## 17. 테스트 범위

### Backend

- 파일명 매칭 성공/미매칭/충돌
- JSON dot path 단일·복수 참조 매칭 및 파싱 오류
- fingerprint 중복 방지
- 복수 파일 복사, 상위 폴더 구조 보존 및 실패 출력 rollback
- 경로 traversal 차단
- 후보 필터 및 페이지네이션
- Excel 다운로드 및 워크북 컬럼 검증

### Frontend

- 매칭 설정 저장 및 재스캔
- 후보 선택과 상세 로딩
- 이미지/JSON 로딩 오류 표시
- 지원 라벨 형식별 overlay 렌더링
- 선택·제외·복구 후 목록 갱신
- Excel 다운로드
