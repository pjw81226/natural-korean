#!/usr/bin/env python3
"""check.py 회귀 테스트.

tests/cases.json의 문장을 하나씩 검사해서, 걸려야 하는 문장이 걸리고
걸리면 안 되는 문장이 안 걸리는지 확인한다. 외부 패키지가 필요 없다.

사용법: python3 tests/run_tests.py

cases.json 항목의 모양:
  {"genre": "ui", "text": "정말로 삭제하시겠습니까?", "expect": ["UI 번역투"]}
  {"genre": "general", "text": "회의가 있었다.", "expect": []}
  {"genre": "report", "heading": "정확도는 어떻게 측정했나", "expect": ["제목 종결"]}

expect가 비어 있으면 한 건도 걸리면 안 된다는 뜻이다.
expect에 분류 이름이 있으면 그 분류가 모두 잡혀야 한다 (다른 분류가 더 잡히는 것은 괜찮다).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 개인 패턴(local/patterns.json)이 테스트 결과를 바꾸지 않게 끈다.
os.environ["NATURAL_KOREAN_NO_LOCAL"] = "1"

_spec = importlib.util.spec_from_file_location("check", ROOT / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def main() -> int:
    cases = json.loads((ROOT / "tests" / "cases.json").read_text(encoding="utf-8"))
    failed = 0
    for number, case in enumerate(cases, 1):
        genre = case.get("genre", "general")
        if "heading" in case:
            text = case["heading"]
            hits = check.heading_hits(text, genre)
        else:
            text = case["text"]
            hits = check.text_hits(text, genre)
        labels = [label for label, _ in hits]
        expect = case["expect"]

        if expect:
            missing = [e for e in expect if not any(label.startswith(e) for label in labels)]
            ok = not missing
            message = f"잡혀야 할 분류가 안 잡혔다: {missing} (잡힌 것: {labels})"
        else:
            ok = not labels
            message = f"걸리면 안 되는 문장이 걸렸다: {hits}"

        if not ok:
            failed += 1
            print(f"FAIL #{number} [{genre}] {text}\n     {message}")

    print(f"{len(cases) - failed}/{len(cases)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
