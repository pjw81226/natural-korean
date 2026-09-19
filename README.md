# natural-korean

A Claude Code skill that removes translationese and AI-sounding phrasing from Korean writing.

한국어 글에서 번역투, 영어 직역, AI 말투를 걸러내는 Claude Code 스킬입니다.
목표는 읽는 사람이 처음부터 한국어로 쓴 글이라고 느끼게 하는 것입니다.

## 들어가며

AI가 문서를 작성하면 대개 티가 납니다. 이런 글을 읽으면 "영혼"이 없다는 느낌을 받습니다.
읽긴 읽는데 무슨 말인지 이해가 잘 되지 않고 불쾌감이 듭니다.

이 스킬은 제가 지금까지 AI로 문서 작업을 하면서 직접 교정한 부분을 예시로 넣어 놓고,
이후 문서에서는 AI가 같은 실수를 반복하지 않도록 만들었습니다.

## AI 말투의 예시

아래는 AI가 쓴 글에서 볼 수 있는 몇 가지 예시입니다.

- 보고서나 웹페이지 제목을 `어떤 걸 모아보나`, `함께 알아볼까요?`처럼 대화하듯 작성합니다.
- `모아보다`, `짚어보다`, `풀어내다`, `담아내다`처럼 동사를 덧붙여 씁니다. `설치 방법을 설명했습니다`라고 하면 될 말을 `설치 방법을 쉽게 풀어냈습니다`라고 늘입니다.
- 쉽게 설명하려다가 뜻이 달라집니다. `재측정했다`를 `다시 찬찬히 들여다봤다`로 바꾸는 식입니다.
- 간단한 기능에도 거창한 의미를 붙입니다. 알림 기능을 설명하면서 `단순한 알림을 넘어 일상의 새로운 기준을 제시합니다`라고 씁니다.
- `당신의 생산성을 새로운 차원으로 이끕니다`처럼 영어 광고를 옮긴 듯한 표현을 씁니다.
- 실제로 한 일을 두루뭉술하게 씁니다. `의견을 하나로 엮었습니다`라고 해서는 의견을 분류했다는 건지, 합의했다는 건지 알 수 없습니다.
- 짧은 글에도 도입과 요약을 붙여 같은 내용을 반복합니다. 문단 길이와 끝맺음도 비슷합니다.
- 이모지와 굵은 글씨로 문장마다 강조합니다.
- 원문에 없던 교훈을 붙입니다. `발표를 망쳐서 팀원들 얼굴을 보기 민망했다`를 `실패를 발판 삼아 팀워크의 중요성을 배웠다`로 바꿉니다.

## 설치

```bash
git clone https://github.com/pjw81226/natural-korean.git ~/.claude/skills/natural-korean
```

프로젝트별 설치 경로는 `.claude/skills/natural-korean`입니다.

업데이트:

```bash
git -C ~/.claude/skills/natural-korean pull
```

## 사용법

Claude Code에서 `/natural-korean`과 수정할 파일을 지정합니다.

```text
/natural-korean README.md
```

## 검사 스크립트

스킬 설치 폴더에서 실행합니다.

```bash
python3 check.py 문서.md
python3 check.py --genre report 보고서.md
python3 check.py --genre ui 문구.txt
python3 check.py ko.json
```

`--strict` 옵션을 사용하면 검사 결과가 있을 때 종료 코드 1을 반환합니다.

## 사용자 규칙

```bash
cp -r local.example local
```

| 파일 | 용도 |
|---|---|
| `local/RULES.md` | 추가 교정 규칙 |
| `local/patterns.json` | 검사 패턴과 예외 문자(`allow_chars`) 설정 |

`local/`은 Git 추적 대상에서 제외됩니다.

## 기여

규칙 제안과 오류 제보는 [이슈](https://github.com/pjw81226/natural-korean/issues)에 남겨 주세요.
PR 작성 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다.

## 라이선스

[MIT](LICENSE)
