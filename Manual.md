# 업사이클링 대상 파일 선별 프로그램 실무 매뉴얼

이 문서는 일반 PC 사용자가 GitHub에서 프로그램을 내려받아 실행하고, 원천데이터와 라벨데이터를 매칭한 뒤 업사이클링 대상을 선별하는 전체 절차를 설명합니다.

## 1. 프로그램 개요

이 프로그램은 지정한 데이터 폴더를 검색하여 원천 파일과 JSON 라벨 파일을 자동으로 매칭합니다. 사용자는 이미지와 라벨을 확인한 뒤 필요한 항목을 선택하거나 제외할 수 있습니다.

- 원본 데이터는 이동하거나 수정하지 않습니다.
- `대상 선택 및 파일 복사`를 누른 파일만 선별 결과 폴더로 복사합니다.
- 선별 상태와 이력은 SQLite 데이터베이스에 저장됩니다.
- 프로그램은 PC 내부에서 Docker로 실행되며 기본적으로 외부에 공개되지 않습니다.

## 2. 실행 전 준비사항

다음 항목이 필요합니다.

- Windows 10/11 PC 또는 macOS
- Docker Desktop
- Git
- 최신 브라우저
- 원천데이터와 라벨데이터가 저장된 로컬 또는 외장 디스크
- 선별 결과와 프로그램 이력을 저장할 충분한 디스크 공간

Docker Desktop을 설치한 후 반드시 실행 상태로 두어야 합니다. Windows에서는 Docker Desktop이 WSL 2 기반 Linux 컨테이너 모드로 실행되어야 합니다.

## 3. 데이터 폴더 준비

데이터 최상위 폴더 아래에 원천데이터 폴더와 라벨데이터 폴더가 각각 있어야 합니다. 폴더 이름은 자유롭게 지정할 수 있습니다.

예시:

```text
datasets/
├── raw-root/                  # 원천데이터 폴더
│   ├── images/
│   └── objects/
└── labeled-root/             # 라벨데이터 폴더
    └── labels/
```

프로그램 운영용 폴더는 원본 데이터 폴더와 분리합니다. 이 폴더에는 선별 결과와 SQLite 이력이 저장되며, 도커를 종료해도 유지됩니다.

```text
prework-runtime/              # 도커 중지 시에도 유지되는 운영 폴더
├── selected/                 # 선별 결과
└── app-data/                 # SQLite 이력
```

## 4. GitHub에서 프로그램 받기

터미널을 열고 프로그램을 저장할 위치로 이동한 다음 아래 명령을 실행합니다.

```bash
git clone https://github.com/stage2soft/upcycling-prework.git
cd upcycling-prework
```

Git을 사용하기 어려운 경우 GitHub 저장소에서 `Code` → `Download ZIP`을 선택하여 압축을 해제합니다. 이후 터미널에서 압축을 해제한 `upcycling-prework` 폴더로 이동합니다.

현재 위치는 다음 명령으로 확인할 수 있습니다.

macOS/Linux:

```bash
pwd -P
```

Windows 명령 프롬프트(cmd):

```cmd
cd
```

## 5. 환경 설정

### 5.1 설정 파일 만들기

macOS/Linux:

```bash
cp .env.example .env
```

Windows 명령 프롬프트(cmd):

```cmd
copy .env.example .env
```

생성된 `.env` 파일을 메모장이나 코드 편집기로 엽니다.

### 5.2 macOS/Linux 경로 예시

```dotenv
DATA_ROOT_PATH=/Volumes/Crucial X10_05_06
SELECTED_DATA_PATH=/Users/username/prework-runtime/selected
APP_DATA_PATH=/Users/username/prework-runtime/app-data
PREWORK_FRONTEND_PORT=18081
PREWORK_BACKEND_PORT=18000
```

일반적인 내부 디스크 경로는 다음과 같이 설정할 수 있습니다.

```dotenv
DATA_ROOT_PATH=/Users/username/datasets
```

### 5.3 Windows 경로 예시

Windows 경로도 역슬래시(`\`) 대신 슬래시(`/`)를 사용합니다.

```dotenv
DATA_ROOT_PATH=D:/datasets
SELECTED_DATA_PATH=C:/Users/username/prework-runtime/selected
APP_DATA_PATH=C:/Users/username/prework-runtime/app-data
PREWORK_FRONTEND_PORT=18081
PREWORK_BACKEND_PORT=18000
```

경로에 공백이 있어도 백슬래시로 처리하지 않습니다.

```dotenv
# 올바른 예
DATA_ROOT_PATH=D:/Company Data/datasets

# 잘못된 예
DATA_ROOT_PATH=D:/Company\ Data/datasets
```

### 5.4 환경 변수 의미

| 환경 변수 | 설명 | 권한 |
|---|---|---|
| `DATA_ROOT_PATH` | 원천데이터와 라벨데이터를 포함한 최상위 폴더 | 읽기 전용 |
| `SELECTED_DATA_PATH` | 선택한 파일이 복사되는 폴더 | 읽기/쓰기 |
| `APP_DATA_PATH` | 선별 이력 데이터베이스가 저장되는 폴더 | 읽기/쓰기 |
| `PREWORK_FRONTEND_PORT` | 사용자 화면 접속 포트 | 기본값 `18081` |
| `PREWORK_BACKEND_PORT` | Backend 및 API 문서 포트 | 기본값 `18000` |

`DATA_ROOT_PATH`, `SELECTED_DATA_PATH`, `APP_DATA_PATH`에는 모두 PC의 절대 경로를 입력해야 합니다.

### 5.5 운영 폴더 만들기

macOS/Linux:

```bash
mkdir -p "/Users/username/prework-runtime/selected"
mkdir -p "/Users/username/prework-runtime/app-data"
```

Windows 명령 프롬프트(cmd):

```cmd
mkdir "C:\Users\username\prework-runtime\selected"
mkdir "C:\Users\username\prework-runtime\app-data"
```

명령의 경로는 `.env`에 입력한 실제 경로로 변경합니다.

## 6. 프로그램 실행

Docker Desktop이 실행 중인지 확인한 뒤 `upcycling-prework` 폴더에서 다음 명령을 실행합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml up -d --build
```

최초 실행 시 Docker 이미지를 내려받고 프로그램을 빌드하므로 몇 분 정도 걸릴 수 있습니다. 완료 상태는 다음 명령으로 확인합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml ps
```

정상 상태 예시:

```text
backend    Up ... (healthy)
frontend   Up ...
```

브라우저에서 다음 주소로 접속합니다.

- 프로그램 화면: <http://localhost:18081>
- Backend 상태 확인: <http://localhost:18000/health>

`.env`에서 포트를 변경했다면 변경한 포트로 접속합니다.

## 7. 최초 데이터 설정

1. 화면 상단의 `Volumes`를 클릭합니다.
2. 데이터 루트, 선별 결과, 애플리케이션 데이터가 모두 `사용 가능`인지 확인합니다.
3. 창을 닫고 좌측 `데이터 및 매칭 설정`으로 이동합니다.
4. `원천 데이터 폴더`를 눌러 `DATA_ROOT_PATH` 아래의 원천 폴더를 선택합니다.
5. `라벨 데이터 폴더`를 눌러 `DATA_ROOT_PATH` 아래의 라벨 폴더를 선택합니다.
6. 매칭 방식을 선택합니다.
7. `어노테이션 방식`에서 라벨 형식에 맞는 렌더링 방식을 선택합니다.
8. `설정 저장 및 재스캔`을 클릭합니다.

`썸네일 폴더 (최상위)`를 선택하면 해당 폴더 아래에서 원천데이터의 상대 하위 경로를 따라 썸네일을 찾습니다. 예를 들어 원천 파일이 `region-a/images/scene.png`이면 썸네일 폴더의 `region-a/images/scene.*`를 사용합니다. 썸네일이 없고 원천 파일이 이미지인 경우 화면에서 후보를 선택할 때 JPEG 썸네일을 앱 데이터 폴더에 비동기로 생성합니다. 생성 중에는 썸네일 카드에 진행 표시가 나타납니다.

원천 폴더와 라벨 폴더는 서로 다른 폴더를 선택해야 합니다. PC의 절대 경로를 화면에 직접 입력하는 것이 아니라 `DATA_ROOT_PATH` 아래에서 폴더를 찾아 선택합니다.

## 8. 매칭 방식 선택

### 8.1 파일명(stem)

원천 파일과 라벨 JSON의 확장자를 제외한 파일명이 같을 때 사용합니다.

```text
scene_001.png
scene_001.pcd
scene_001.json
```

위 파일들은 `scene_001`이라는 하나의 후보로 매칭됩니다. 일반적으로 파일명이 같은 데이터셋에서는 이 방식을 사용합니다.

### 8.2 JSON 참조키

라벨 JSON 내부에 원천 파일명이 기록되어 있을 때 사용합니다. `JSON dot path`에 원천 파일 경로가 저장된 필드명을 입력합니다.

예시 JSON:

```json
{
  "image": {
    "file_name": "scene_001.png"
  }
}
```

이 경우 `JSON dot path`에는 다음 값을 입력합니다.

```text
image.file_name
```

키 이름이 `data_key`라면 `data_key`를 입력합니다. 문자열 배열로 여러 원천 파일을 참조하는 형식도 사용할 수 있습니다.

## 9. 어노테이션 방식 선택

`데이터 및 매칭 설정`의 `어노테이션 방식`은 중앙 뷰어가 라벨 JSON을 해석하는 기준입니다.

| 방식 | 용도 |
|---|---|
| `bbox_2d` | 이미지 평면의 사각형 바운딩 박스 |
| `bbox_3d` | 위치, 크기, 회전 정보를 가진 3D cuboid. 원천 이미지가 있으면 이미지에 투영하고, 없으면 XY top view로 표시 |
| `polygon` | 객체의 다각형 좌표 |
| `segmentation` | segmentation 좌표를 다각형 오버레이로 표시 |

선택한 방식과 일치하지 않는 geometry는 자동으로 다른 방식으로 해석하지 않습니다. 방식을 변경한 뒤 `설정 저장 및 재스캔`을 누르면 다음 후보를 열 때 선택한 방식이 적용됩니다.

## 10. 화면 구성

<img width="1797" height="1239" alt="업사이클링 대상 파일 선별 프로그램 화면" src="https://github.com/user-attachments/assets/eac98bcb-6219-47cb-8173-cafe9dbe0777" />

- 상단: 볼륨 상태, 재스캔, Excel 다운로드
- 좌측: 데이터 설정, 필터, 선별 후보 목록
- 중앙: 원천 이미지와 라벨 오버레이
- 우측: 후보 상세 정보, 파일 목록, 선택 및 제외 버튼

상단 요약 영역에서 전체 후보, 검토 대기, 선택 완료, 제외 건수를 확인할 수 있습니다.

## 11. 후보 상태 확인

### 매칭 상태

| 상태 | 의미 | 사용자 조치 |
|---|---|---|
| `매칭` | 원천 파일과 라벨 파일이 정상 연결됨 | 내용을 확인한 뒤 선택 또는 제외 |
| `미매칭` | 대응하는 원천 또는 라벨 파일이 없음 | 파일명과 폴더 구성을 확인 |
| `충돌` | 같은 키에 여러 후보가 있어 하나를 결정할 수 없음 | 중복 파일명과 경로를 확인 |
| `오류` | JSON 파싱 또는 파일 접근에 실패함 | 우측 오류 메시지와 파일을 확인 |

### 선별 상태

| 상태 | 의미 |
|---|---|
| `대기` | 아직 결정하지 않은 후보 |
| `선택` | 선별 결과 폴더로 복사가 완료된 후보 |
| `제외` | 업사이클링 대상에서 제외한 후보 |
| `복사 실패` | 파일 복사 중 오류가 발생한 후보 |

좌측 필터에서 선별 상태와 매칭 상태를 조합하거나 파일명·매칭 키로 검색할 수 있습니다.

## 11. 후보 검토 및 선별

1. 좌측 후보 목록에서 항목을 선택합니다.
2. 중앙 화면에서 이미지와 라벨 오버레이를 확인합니다.
3. 복수 원천 파일이 있으면 중앙의 파일 목록에서 대표 이미지를 전환합니다.
4. 우측의 원천 파일 또는 라벨 파일을 눌러 개별 미리보기를 확인합니다.
5. 업사이클링 대상이면 `대상 선택 및 파일 복사`를 누릅니다.
6. 대상이 아니면 `제외`를 누릅니다.

`대상 선택 및 파일 복사`를 누르면 원본은 그대로 유지되고 선택한 파일만 `SELECTED_DATA_PATH`로 복사됩니다. 원본의 상대 폴더 구조도 그대로 보존됩니다.

제외한 후보를 다시 검토하려면 해당 후보를 선택한 뒤 `대기로 복구`를 누릅니다.

### 같은 파일이 이미 있을 때

선별 결과 폴더에 같은 경로의 파일이 있으면 덮어쓰기 확인 창이 표시됩니다.

- 기존 파일을 유지하려면 `취소`를 누릅니다.
- 기존 파일을 교체해도 되는지 확인한 후에만 `덮어쓰기`를 누릅니다.

## 12. 재스캔

원천 또는 라벨 파일을 추가·수정한 경우 화면 상단의 `재스캔`을 누릅니다. 같은 파일 묶음은 중복 후보로 생성되지 않으며 이미 선택 완료된 항목도 다시 선택 대상으로 등록되지 않습니다.

## 13. Excel 결과 다운로드

화면 상단의 `Excel 다운로드`를 누르면 현재 선별 결과가 `.xlsx` 파일로 저장됩니다.

- `선별 결과` 시트: 후보별 선별 상태와 파일 경로
- `파일 목록` 시트: 후보에 포함된 개별 파일 정보

다운로드 파일은 브라우저의 기본 다운로드 폴더에 저장됩니다.

## 14. 프로그램 종료 및 재실행

프로그램을 종료해도 선별 결과와 이력은 삭제되지 않습니다.

종료:

```bash
docker compose --env-file .env -f prework.compose.yaml down
```

재실행:

```bash
docker compose --env-file .env -f prework.compose.yaml up -d
```

상태 확인:

```bash
docker compose --env-file .env -f prework.compose.yaml ps
```

> `docker compose down -v`는 사용하지 마십시오. 볼륨 구성에 따라 운영 데이터가 삭제될 수 있습니다.

## 15. 프로그램 업데이트

Git으로 내려받은 경우 다음 명령을 실행합니다.

```bash
git pull --ff-only
docker compose --env-file .env -f prework.compose.yaml up -d --build
```

ZIP으로 내려받은 경우 새 ZIP을 별도 폴더에 압축 해제하고, 기존 `.env`의 설정값을 새 폴더의 `.env`에 적용한 뒤 실행합니다. `SELECTED_DATA_PATH`와 `APP_DATA_PATH`는 기존과 같은 경로를 사용해야 선별 결과와 이력이 유지됩니다.

## 16. 데이터 백업

다음 두 폴더를 정기적으로 백업합니다.

- `SELECTED_DATA_PATH`: 선별 완료 파일
- `APP_DATA_PATH`: SQLite 선별 이력

안전한 백업을 위해 프로그램을 종료한 후 두 폴더를 다른 디스크에 복사합니다. 원본 데이터는 `DATA_ROOT_PATH`에서 별도로 관리합니다.

## 17. 문제 해결

### Docker 명령을 찾을 수 없음

Docker Desktop이 설치되어 있고 실행 중인지 확인합니다. 설치 직후에는 터미널을 닫았다가 다시 열어야 할 수 있습니다.

### `permission denied` 또는 `/host_mnt` 마운트 오류

1. `.env`의 실제 폴더가 PC에 존재하는지 확인합니다.
2. 경로 공백 앞에 백슬래시(`\`)를 붙이지 않았는지 확인합니다.
3. macOS에서는 Docker Desktop이 외장 디스크에 접근할 수 있도록 시스템 및 Docker Desktop의 파일 공유 권한을 확인합니다.
4. Windows에서는 해당 드라이브가 Docker Desktop과 공유 가능한 로컬 드라이브인지 확인합니다.
5. 설정을 수정한 후 컨테이너를 다시 생성합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml up -d --force-recreate
```

Compose가 해석한 실제 경로는 다음 명령으로 확인합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml config
```

### 수정한 `.env`가 반영되지 않음

먼저 현재 터미널이 올바른 프로젝트 폴더에 있는지 확인합니다. 같은 이름의 다운로드본이 여러 개 있으면 다른 `.env`를 사용할 수 있습니다.

macOS/Linux에서는 현재 셸의 환경변수가 `.env`보다 우선할 수 있습니다.

```bash
unset DATA_ROOT_PATH SELECTED_DATA_PATH APP_DATA_PATH
docker compose --env-file .env -f prework.compose.yaml up -d --force-recreate
```

Windows 명령 프롬프트(cmd):

```cmd
set "DATA_ROOT_PATH="
set "SELECTED_DATA_PATH="
set "APP_DATA_PATH="
docker compose --env-file .env -f prework.compose.yaml up -d --force-recreate
```

### Backend가 `healthy` 상태가 되지 않음

로그를 확인합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml logs --tail=200 backend
```

대부분 경로가 존재하지 않거나 `APP_DATA_PATH`에 쓰기 권한이 없을 때 발생합니다.

### 화면이 열리지 않음

컨테이너 상태와 포트 사용 여부를 확인합니다.

```bash
docker compose --env-file .env -f prework.compose.yaml ps
```

기본 포트가 다른 프로그램에서 사용 중이면 `.env`의 포트를 변경한 뒤 다시 실행합니다.

```dotenv
PREWORK_FRONTEND_PORT=18082
PREWORK_BACKEND_PORT=18002
```

이 경우 접속 주소는 `http://localhost:18082`입니다.

### 후보가 표시되지 않음

- 원천데이터 폴더와 라벨데이터 폴더를 서로 다르게 선택했는지 확인합니다.
- 선택한 폴더가 `DATA_ROOT_PATH` 바로 아래 또는 그 하위에 있는지 확인합니다.
- 파일명 매칭 규칙 또는 JSON 참조키가 데이터 형식과 일치하는지 확인합니다.
- `재스캔`을 누른 뒤 매칭 상태 필터를 `전체`로 변경합니다.

## 18. 안전 수칙

- `.env`에는 PC의 로컬 경로가 포함되므로 GitHub에 업로드하지 않습니다.
- `APP_DATA_PATH`와 `SELECTED_DATA_PATH`를 임시 폴더로 지정하지 않습니다.
- 외장 디스크를 분리하기 전에 프로그램을 종료합니다.
- 파일 덮어쓰기는 충돌 목록을 확인한 후 진행합니다.
- 운영 중인 `.env`, 선별 결과 폴더, 애플리케이션 데이터 폴더를 임의로 삭제하지 않습니다.
