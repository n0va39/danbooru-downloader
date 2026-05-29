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
- 저장할 태그 항목 선택: Meta, Artist, Copyright, General
- 저장 순서: Meta -> Artist -> Copyright -> General
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

### 설정 파일

로컬 설정은 `config.json`에 저장된다. Danbooru API Key가 들어갈 수 있으므로 Git에는 올리지 않는다.

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
- Select tag categories: Meta, Artist, Copyright, General
- Saved tag order: Meta -> Artist -> Copyright -> General
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

### Config

Local settings are saved in `config.json`. It may contain a Danbooru API key, so it is ignored by Git.
