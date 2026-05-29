# Danbooru Downloader

Danbooru API 기반 이미지 다운로더다. 검색, 2차 태그 필터링, 레이팅 필터, 태그 `.txt` 저장을 지원한다.

## 한국어

### 주요 기능

- Danbooru 태그 검색
- 2차 필터링: API 검색 후 받은 태그 데이터에서 처리
- `-tag` 제외 조건
- `tag1|tag2` OR 조건
- 레이팅 선택: General, Sensitive, Questionable, Explicit
- 파일명 규칙: ID만, 태그+ID, 원본 이름
- 태그 `.txt` 동시 저장
- 저장할 태그 항목 선택: Meta, Artist, Character, Copyright, General
- 태그 항목 드래그 정렬
- 저장 태그의 `_`를 공백으로 변환
- GUI 언어 전환: 한국어 / English
- `pythonw.exe` 기반 무콘솔 실행

### 설치

uv 설치:

```bat
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

의존성 설치:

```bat
uv sync
```

### 다운로드 방법

Git을 사용할 수 있으면 저장소를 클론한다.

```bat
git clone https://github.com/n0va39/danbooru-downloader.git
cd danbooru-downloader
uv sync
run_gui.vbs
```

Git을 모르면 압축파일로 받아도 된다.

1. GitHub 저장소 페이지에서 `Code` 버튼을 누른다.
2. `Download ZIP`을 누른다.
3. ZIP 파일을 원하는 위치에 압축 해제한다.
4. 압축 해제한 폴더에서 우클릭 후 터미널을 연다.
5. 아래 명령어를 실행한다.

```bat
uv sync
run_gui.vbs
```

### 실행

콘솔 없이 실행:

```bat
run_gui.vbs
```

배치 실행:

```bat
run_gui.bat
```

바탕화면 바로가기 생성:

```bat
create_shortcut.bat
```

### 필터 예시

포함 태그:

```text
1girl solo long_hair
```

2차 필터:

```text
-comic -chibi cat_ears|dog_ears
```

의미:

- `comic`, `chibi` 태그가 있으면 제외
- `cat_ears` 또는 `dog_ears` 중 하나는 포함해야 함

## English

### Overview

Danbooru Downloader is a GUI image downloader built on the Danbooru API. It supports search, local secondary tag filtering, rating filters, and optional `.txt` tag sidecar files.

### Features

- Danbooru tag search
- Secondary filtering after API results are received
- `-tag` exclusion
- `tag1|tag2` OR matching
- Rating selection: General, Sensitive, Questionable, Explicit
- Filename rules: ID only, Tags + ID, Original name
- Save tag `.txt` files
- Select tag categories: Meta, Artist, Character, Copyright, General
- Drag tag categories to change saved order
- Replace `_` with spaces in saved tags
- GUI language switch: Korean / English
- Console-free launch through `pythonw.exe`

### Install

Install uv:

```bat
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install dependencies:

```bat
uv sync
```

### Download

If Git is installed, clone the repository.

```bat
git clone https://github.com/n0va39/danbooru-downloader.git
cd danbooru-downloader
uv sync
run_gui.vbs
```

If you do not use Git, download the ZIP file.

1. Open the GitHub repository page.
2. Click `Code`.
3. Click `Download ZIP`.
4. Extract the ZIP file.
5. Open a terminal in the extracted folder.
6. Run these commands.

```bat
uv sync
run_gui.vbs
```

### Run

Run without a console window:

```bat
run_gui.vbs
```

Run with the batch launcher:

```bat
run_gui.bat
```

Create a desktop shortcut:

```bat
create_shortcut.bat
```

### Filter Example

Include tags:

```text
1girl solo long_hair
```

Secondary filter:

```text
-comic -chibi cat_ears|dog_ears
```

Meaning:

- Exclude posts that contain `comic` or `chibi`
- Require either `cat_ears` or `dog_ears`
