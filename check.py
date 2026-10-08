#!/usr/bin/env python3
"""한국어 글의 번역투, 영어 직역, AI 말투를 기계로 검사한다.

사용법:
  python3 check.py <파일...>                  공통 검사 (SKILL.md 1~3절)
  python3 check.py --genre report <파일...>   공통 + 보고서와 공식 문서 (4절)
  python3 check.py --genre ui <파일...>       공통 + UI 문구 (5절)
  python3 check.py <번역파일.json...>         JSON은 값만 꺼내 UI 모드로 검사
  python3 check.py --strict <파일...>         한 건이라도 걸리면 종료 코드 1

기계로 확실히 잡을 수 있는 것만 본다.
무생물 주어, 피동 남발, 영어식 어순 같은 구조 번역투(SKILL.md 1-3)와 글의 짜임(3-3)은
기계로 안 잡힌다. 0건이어도 사람이 한 번 읽어야 한다.

개인이나 팀 전용 패턴은 이 파일 옆의 local/patterns.json에 둔다 (local.example/ 참고).
"""
import json
import os
import re
import sys
from pathlib import Path

GENRES = ("general", "report", "ui")

# 3-4. 문장부호
BANNED_CHARS = {
    "·": "가운뎃점. 쉼표나 슬래시로",
    "§": "section sign. '5절'처럼",
    "—": "em대시. 쉼표나 마침표로",
    "–": "en대시. 물결표(~)나 '에서'로",
}

# 1. 번역투
TRANSLATIONESE = [
    # 1-1. 조사와 연결 표현
    (r"에 대(?:해|한)\b", "~에 대해 → ~를/~을"),
    (r"을 통(?:해|한)\b|를 통(?:해|한)\b", "~을 통해 → ~로"),
    (r"(?<![앞뒤안밖위옆])에 있어(?!야)", "~에 있어 → ~에서/~할 때"),
    (r"로 인(?:해|한)\b|으로 인(?:해|한)\b", "~로 인해 → ~때문에"),
    (r"에 의(?:해|한)\b", "~에 의해 → 능동태로"),
    (r"되어지|보여지|불려지|쓰여지", "이중피동"),
    (r"것으로 (?:보인다|보입니다|판단된다|판단됩니다)", "~것으로 보인다 → 단정 또는 '추정합니다'"),
    (r"(?:[가-힣]{2,}의 ){2,}[가-힣]{2,}", "명사 연쇄 3개 이상"),
    (r"(?:로|으로)부터", "from 직역 → ~에서, ~에게서"),
    (r"에도 불구하고", "despite 직역 → ~지만, ~는데도"),
    (r"함으로써", "by -ing 직역 → ~해서, ~하면"),
    (r"기 위(?:해|하여|한)", "in order to 직역 남발 → ~하려면, ~하도록"),
    (r"(?:을|를) 위한 ", "B for A 직역 → 'A를 위한 B'는 'A B'로 붙여 쓴다"),
    (r"에 기반(?:하|한|해)", "based on 직역 → ~를 바탕으로, ~에 따라"),
    # 1-2. 영어 품사가 그대로 남은 말
    (r"성공적으로", "successfully 직역 → 지운다. '~했습니다'가 이미 성공을 말한다"),
    (r"당신|귀하", "you 직역 → 주어를 생략한다. 소유는 '내' 또는 생략"),
    (r"(?<![가-힣])(?:하나의|한 개의) ", "a/an 직역 → 지운다 ('하나로 합친다'는 뜻이면 둔다)"),
    (r"(?:파일|항목|설정|데이터|결과|옵션|메시지|값|키|노드|문서|이미지|기능|변경 ?사항|요청|오류|세션"
     r"|버전|폴더|프로젝트|모델|도구|변수|단계|필드|컴포넌트|링크|목록|레코드|테이블|이벤트)들",
     "복수 -s 직역 → '들'을 뺀다"),
    (r"각각의 ", "each 직역 → ~마다, ~별"),
    (r"(?:^|\s)보다 (?:나은|좋은|빠른|빠르게|쉬운|쉽게|정확한|정확하게|많은|적은|큰|작은|높은|낮은|안전한|효율적)",
     "more 직역 → 더"),
    (r"중 하나(?:입니다|이다|다(?=[\s.,]|$)|인 |로 )", "one of 직역 → 단정하거나 '손꼽히는'"),
    (r"고 있는 중", "be -ing 직역 → ~하는 중, ~하고 있다"),
    (r"(?:^|\s)(?:만약|만일) ", "if 직역 → '~면'으로 충분하다"),
]

# 받침이 ㄹ인 음절 전부. '~할 필요가 있다', '~할까'처럼 관형형 어미를 잡을 때 쓴다.
_RIEUL_FINAL = "".join(chr(0xAC00 + i * 28 + 8) for i in range(19 * 21))

# 대과거 '~했었다'. 받침 ㅆ 음절 뒤의 '었'을 잡되 '있었다'는 정상 과거라 뺀다.
_SS_FINAL = "".join(chr(0xAC00 + i * 28 + 20) for i in range(19 * 21)).replace("있", "")
TRANSLATIONESE.append(
    (rf"[{_SS_FINAL}]었(?:다|습니다|어요|던|는데|지만)", "대과거 직역 → ~했다")
)

# 2-1. 개념 직역 (경고만, 문맥에 따라 정당할 수 있음)
CALQUE = [
    (r"(?:지연|분포|응답 ?시간|레이턴시)[^.]{0,12}꼬리|꼬리[^.]{0,8}(?:지연|분포|요청|구간)",
     "tail 직역 → 극단값, 지연이 큰 소수 요청"),
    (r"천장을 (?:치|쳤)", "ceiling 직역 → 포화"),
    (r"뒤에 숨(?:습니다|는다|어)", "hidden behind 직역"),
    (r"튑니다|튀는 값", "spike 직역 → 급증"),
    (r"묻힙니다|묻힌다", "buried 직역 → 가려집니다"),
    (r"(?:학습|개발|성장|데이터|디지털|혁신|AI|도입|전환)의? 여정", "journey 직역 → 과정"),
    (r"(?:AI|기술|시장|경쟁|산업|생태계)의? 지형", "landscape 직역 → 판도, 현황"),
    (r"(?:가능성|잠재력|가치|성장)을 (?:잠금 해제|열어 ?(?:줍|준|주))", "unlock 직역 → ~할 수 있게 된다"),
    (r"힘을 실어", "empower 직역 → ~할 수 있게 한다"),
    (r"레버리지(?:하|한|해|를)|지렛대로 삼", "leverage 직역 → 쓴다, 활용한다"),
    (r"페인 ?포인트|고충점", "pain point 직역 → 불편, 어려움"),
    (r"딥 ?다이브", "deep dive 직역 → 자세히 본다"),
    (r"낮게 달린 (?:열매|과일)", "low-hanging fruit 직역 → 쉽게 얻을 수 있는 성과"),
    (r"같은 페이지에", "on the same page 직역 → 서로 같게 이해한다"),
    (r"하루의 끝에", "at the end of the day 직역 → 결국"),
    (r"앞으로 나아가(?:며|면서)", "moving forward 직역 → 앞으로"),
]

# 2-2, 2-3. 구문 직역과 사동 오용
CALQUE_SYNTAX = [
    # 한글은 음절이 합성 문자라 어미까지 넣으면 '하'가 '한다' 안에서 안 잡힌다.
    # 그래서 어간까지만 쓴다.
    (r"(?:을|를) 가능하게", "enable 직역 → ~할 수 있다"),
    (r"(?:을|를) 필요로", "require 직역 → ~가 필요하다"),
    (r"(?:을|를) 보장", "ensure 직역 → 확실히 한다"),
    (r"에 기여", "contribute 직역 → ~를 돕는다"),
    (r"에 초점을 맞", "focus on 직역 → ~를 중심으로"),
    (r"(?:로서|으로서)의 역할", "serve as 직역 → ~ 역할을 한다"),
    (r"이는 .{1,30}(?:을|를) 의미", "this means 직역 → 즉, ~다"),
    (r"가지고 있", "have 직역 → 있다"),
    (r"에 있어서", "~において 직역 → ~에서, ~할 때"),
    (r"에 대한 접근", "approach to 직역 → ~를 다루는 방법"),
    (r"(?:향상|개선|감소|완화|최소화|증가|단축|확대|안정화)시(?:켜|키|킨|킬|켰|킵|킴)",
     "사동 오용 → ~하다"),
    (rf"[{_RIEUL_FINAL}] 필요가 있", "need to 직역 → ~해야 한다"),
    (r"는 것이 (?:필요|중요|가능|좋)", "it is ~ to 직역 → ~해야 한다, ~하면 좋다"),
    (r"(?:을|를) 허용|도록 허용", "allow 직역 → ~할 수 있다"),
    (r"(?:을|를) (?:야기|초래)", "cause 직역 → ~가 생긴다, ~하게 된다"),
    (r"뿐만 아니라", "not only A but also B 직역 → A도 B도"),
    (r"인지 아닌지", "whether or not 직역 → ~인지"),
    (r"는 경향이 있", "tend to 직역 → 대개 ~한다"),
    (r"라는 사실", "the fact that 직역 → ~라는 점, 또는 풀어 쓴다"),
    (r"(?<![가-힣])담(?:는|아|았|고|긴|겨)", "담다 → 보낸다, 알린다 (contain, include 직역)"),
]

# 3-1. 상투구
CLICHE = [
    (r"단순히\s*[^.,]{1,20}(?:가|이)\s*아니라|단순(?:한|히) [^.,]{1,20}(?:을|를) 넘어",
     "없는 대조를 만든 구문 → 뒤쪽만 남긴다"),
    (r"라\s*할 수 있|라고\s*볼 수 있", "~라 할 수 있다 → 단정한다"),
    (r"는 점에서 의미가 있", "의미의 내용이 비었다"),
    (r"주목할 만|눈여겨볼 만", "판단을 독자에게 미룬다"),
    (r"결국 중요한 것은|무엇보다도", "강조어가 강조를 대신한다"),
    (r"궁극적으로|나아가\s", "접착제 부사 → 지운다"),
    (r"의 열쇠|의 관건|게임 체인저", "비유가 내용을 대신한다"),
    (r"새로운 지평|패러다임 전환|한 단계 도약", "과장 상투구"),
    (r"실질적인|유의미한|차별화된|혁신적인|강력한|원활한|매끄러운|획기적", "형용사가 근거를 대신한다 → 수치나 사실로"),
    (r"다양한|여러 가지|일련의", "개수를 숨긴다 → 실제 개수로"),
    (r"바로 이 지점에서|여기서 중요한 것은", "극적 전환 흉내 → 지운다"),
    (r"[가-힣]야말로", "강조 어미 남용"),
]

# 3-3. 글의 짜임에서 나는 AI 말투 가운데 기계로 잡히는 것
AI_TONE = [
    (r"(?:좋은|훌륭한|날카로운) 질문|물론입니다|물론이죠", "서두 맞장구 → 지우고 본론부터"),
    (r"도움이 되(?:셨|었)(?:기를|길|으면)|궁금한 (?:점|사항|것)이 있으(?:시면|면)|언제든(?:지)? (?:말씀|문의|질문)",
     "맺음 인사 → 지운다"),
    (r"(?:^|\s)(?:요약하자면|요약하면|정리하자면|정리하면|결론적으로|한마디로 말해)",
     "되풀이 요약 → 새 정보가 없으면 지운다"),
    (r"살펴보겠습니다|알아보겠습니다|알아보도록 하겠습니다|살펴보도록 하겠습니다", "예고문 → 예고 없이 바로 쓴다"),
    (r"(?<!말씀)(?<!말씀 )드리겠습니다|실 수 있습니다", "과한 존대 → ~하겠습니다, ~할 수 있습니다"),
    # 3-9. ㄹ이 빠지는 동사의 현재형
    # 한 글자 어간(들다, 늘다, 열다 ...)이 홀로 설 때와 만든다만 잡는다. 흔든다, 시든다는 두지 않는다.
    (r"(?:^|\s)(?:는|든|연|건|판|논|분|민|끈|돈|던|튼)다(?=[\s.,)]|$)|만든다(?=[\s.,)]|$)",
     "ㄹ이 빠진 현재형(는다, 든다, 연다, 만든다) → 많아진다, 증가한다, 생성한다"),
    (r"(?<![가마하오])늘(?:다|어|었|고|면|지|게|수록)", "늘다 → 많아지다, 커지다, 증가하다 (늘리다는 그대로)"),
    (r"(?:요금|비용)이 (?:더 )?커(?:진|지|졌|져)", "요금이 커진다 → 요금이 증가한다"),
    # 3-4. 문장 중간에 값을 감싼 따옴표
    (r'["“][^"”\n]{1,20}["”](?:으로|로|만|을|를|이|가|은|는|에)(?=[\s.,]|$)',
     '문장 중간 따옴표 → 풀어서 쓴다 ("완료"로 바꾼다 → 상태를 완료로 바꾼다)'),
    # 3-6. 동사를 덧붙여 늘인 표현. '모아 보관', '모아 보고'는 잡지 않는다.
    (r"(?:모아|짚어)\s?(?:보(?:다|았|겠|는|면|며|자|세)|봤|봅니다|본다|보자)"
     r"|(?:풀어|담아)\s?(?:내(?:다|었|겠|는|면|며|서)|냈|냅니다|낸다|낸)",
     "동사를 덧붙여 늘인 표현(모아보다, 짚어보다, 풀어내다, 담아내다) → 정리하다, 검토하다, 설명하다, 기록하다"),
]

# 3-2. 물음표 없는 의문형 종결. 자문자답 화법.
# 물음표가 붙은 진짜 인용 질문(FAQ, 인터뷰)은 잡지 않는다.
_END = r"(?=[\s.,)\]<]|$)"
INTERROGATIVE = re.compile(
    # '~나 보다', '~나 싶다'는 추측을 나타내는 평서문이라 뺀다.
    rf"(?:했|였|었|았|왔|갔|봤|줬|났|졌|쳤|겼|렀|썼|눴|췄|겠|되)나(?!\s?(?:보|싶)){_END}"
    # '하나'는 수사(둘 중 하나)와 겹치므로 의문사가 앞에 있을 때만 잡는다.
    rf"|(?:어떻게|무엇을|뭘|왜|언제|어디서|얼마나) [^.?]{{0,20}}하나{_END}"
    rf"|(?:[{_RIEUL_FINAL}]까|는가|은가|느냐|더냐){_END}"
)

# 4. 보고서와 공식 문서. report 모드에서만 본다.
COLLOQUIAL = [
    (r"쟀습니다|재니\b|다시 재|잰 값|잴 수", "측정 계열 → 측정했습니다/재측정"),
    (r"뒀습니다|뺐습니다|넣었습니다|쌓았습니다", "배치/제외/추가/진행으로"),
    (r"갈렸|몰렸|무너졌", "나뉘었/편중됐/급락했으로"),
    (r"처음에는", "이전 상태면 → 기존에는"),
    (r"(서버|클라우드)(로|에) (올렸|올라가|올립니다|보냈|보내)", "전송 → 전송했습니다/전송됩니다"),
    (r"끌어올렸|끌어올리", "수치 → 높였습니다/개선했습니다"),
    (r"우리 (데이터|모델|서비스|앱|검증셋)", "1인칭 소유 → 자체 구축한/이 서비스"),
    (r"(?:객체|물체|얼굴|강아지|고양이|동물|차량)(?:를|을) (?:찾|잡)(?:아|고|았|습|는)", "검출 → 검출하다"),
    (r"눈으로 (확인|검수|잡|판정)", "→ 육안으로/직접"),
    (r"들어가 있(습니다|는|다)", "탑재 → 탑재되어 있다"),
    (r"갈라 (봤|보)", "→ 분리 검증"),
    (r"\d+번 (학습|실험|수행)", "횟수 → N회"),
    (r"(학습|실험)을 돌(렸|리)", "→ 수행/학습했다"),
    (r"헷갈리는", "→ 오인하는"),
    (r"만으로는 부족해", "→ 만으로는 충분하지 않아"),
    (r"(?<![가-힣])근데|그러니까", "구어 연결어 → 그런데/즉"),
    (r"(하고|되고|이고)[^.。]{2,40}(하고|되고|이고)[^.。]{2,40}(합니다|했습니다|입니다)",
     "~하고 ~하고 나열 → 명사형이나 문장 분리"),
    # 4-3. 은어와 억지 한자어
    (r"삽질|노가다|땜빵|땜질", "은어 → 시행착오/수작업/임시 조치"),
    (r"(?:서버|프로세스|앱|서비스|프로그램)(?:가|는|이) (?:죽|뻗)", "은어 → 중단됐다, 응답하지 않았다"),
    (r"(?:오류|에러|버그)(?:가|는) 터", "은어 → 발생했다"),
    (r"날려 ?먹|(?:데이터|파일|기록|로그)(?:를|을) 날(?:렸|리)", "은어 → 삭제했다, 유실했다"),
    (r"박아 (?:넣|놓|뒀|두)", "은어 → 직접 입력했다, 고정값으로 두었다"),
    (r"상이(?:하|한)|용이(?:하|한)", "억지 한자어 → 다르다, 쉽다"),
    (r"에 기인", "억지 한자어 → ~때문이다"),
    (r"제고(?:하|한|해|를)|도모(?:하|한|해)", "억지 한자어 → 높인다, 꾀한다"),
    (r"(?<![가-힣])(?:금일|익일)", "억지 한자어 → 오늘, 다음 날"),
    (r"(?<![가-힣])(?:상기|하기) (?:내용|사항|표|그림|항목)|(?:상기|하기)와 같이|상기한 바", "억지 한자어 → 위, 아래"),
    (r"(?<![가-힣])기 (?:수립|보고|제출|확정|배포)", "억지 한자어 → 이미 ~한"),
    (r"잘라 (?:보내|보냈|올리|올렸)", "구어 → 크롭하여 전송"),
    (r"공기계|분점(?:하|해|한)|굴신", "은어, 억지 한자어 → 사용하지 않는 단말, 나눠 쓰다, 폈는지 접었는지"),
]

# 4-5. 제목 종결. 보고서 제목은 체언으로 끝낸다.
HEADING_BAD_END = re.compile(
    r"(?:했|하|되|이|였|이었|왔|갔|봤|줬|났|졌|쳤|겼|렀|썼|눴|췄|맞|같|아니)?"
    r"(?:나|까|는가|은가|을까|ㄹ까|냐|느냐|니|다|죠|네요|군요)\s*\??$"
)
# 체언인데 위 패턴에 걸리는 낱말. 오탐 방지용.
HEADING_OK_TAIL = ("하나", "가나", "만나", "사우나", "바나나", "안테나", "제나", "하까", "어머니", "주머니", "할머니")

# 5. UI 문구 번역투. ui 모드에서만 본다.
UI_TRANSLATIONESE = [
    (r"정말로? [^.?!]{0,40}(?:습니까|까요)", "Are you sure 직역 → '정말로'를 빼고 '~할까요?'"),
    (r"(?:시|하)겠습니까", "존대 과잉 → ~할까요?"),
    (r"십시오|시기 바랍니다", "공문 말투 → ~하세요, ~해 주세요"),
    (r"에 실패(?:했|하였)|(?:을|를) 실패(?:했|하였)", "Failed to 직역 → ~하지 못했습니다"),
    (r"는 (?:동안|중에?|도중에?) (?:오류|에러|문제)", "Error while -ing 직역 → ~하지 못했습니다"),
    (r"발견되지 않|찾아지지 않", "not found 직역 → ~가 없습니다"),
    (r"(?:\d|\}\})\s*개의 ", "'3개의 파일' → '파일 3개'"),
    # '업로드', '다운로드'는 굳은 말이라 뺀다.
    (r"로딩|(?<![업운])로드(?:하|되|에|를|할|가| 중|중)", "load 음차 → 불러오다"),
    (r"실행 취소(?:할|될) 수 없", "cannot be undone 직역 → 되돌릴 수 없습니다"),
    (r"요구(?:됩니다|된다|되는)", "is required 직역 → ~를 입력하세요, 필수 항목입니다"),
    (r"유효하지 않", "invalid 직역 → 형식이 맞지 않습니다, 올바르지 않습니다"),
    (r"사용 가능한 ", "available 직역 → 대개 지워도 된다 ('파일이 없습니다')"),
    (r"여기를 (?:클릭|누르)", "click here 직역 → 동작 이름을 버튼 문구로"),
    (r"참조하(?:십시오|세요|시기)", "refer to 직역 → ~를 보세요, '~ 보기'"),
    (r"을\(를\)|를\(을\)|이\(가\)|가\(이\)|은\(는\)|는\(은\)|와\(과\)|과\(와\)|\(으\)로",
     "병기 조사 → 어순을 바꿔 조사를 없앤다"),
    (r"\}\}[\"'”’)\]]?(?:을|를|이|가|은|는|와|과|로|으로)(?=[\s.,?!]|$)",
     "변수 뒤 조사 → 들어올 값의 받침을 알 수 없다. 어순을 바꾼다"),
    (r"\be\.g\.|\bi\.e\.|\betc\.", "영어 약어 → 예:, 즉, 등"),
    (r"(?:^|\s)(?:저희|우리)(?:는|가|의|\s)", "앱이 자기를 1인칭으로 부른다 → 생략"),
    (r"사용자님|고객님", "사용자를 부르지 않는다 → 주어 생략"),
]

_LOCAL_TARGETS = {
    "translationese": TRANSLATIONESE,
    "calque": CALQUE,
    "calque_syntax": CALQUE_SYNTAX,
    "cliche": CLICHE,
    "ai_tone": AI_TONE,
    "colloquial": COLLOQUIAL,
    "ui": UI_TRANSLATIONESE,
}


def load_local(path: Path) -> list[str]:
    """local/patterns.json의 패턴을 더한다. 문제가 있는 항목은 건너뛰고 경고를 돌려준다."""
    if not path.exists():
        return []
    warnings = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path} 읽기 실패: {exc}"]
    for name, target in _LOCAL_TARGETS.items():
        for entry in data.get(name, []):
            try:
                pattern, why = entry
                re.compile(pattern)
            except (ValueError, TypeError, re.error) as exc:
                warnings.append(f"{path} {name} 항목 무시: {entry!r} ({exc})")
                continue
            target.append((pattern, why))
    for char, why in data.get("banned_chars", {}).items():
        BANNED_CHARS[char] = why
    for char in data.get("allow_chars", []):
        BANNED_CHARS.pop(char, None)
    return warnings


HEADING_RE = re.compile(r"^\s*(?:#{1,3}\s+(.*)|<h[1-3][^>]*>(.*?)</h[1-3]>)\s*$", re.I)
TAG_RE = re.compile(r"<[^>]+>")
EMOJI_HEAD = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")


def pattern_groups(genre: str):
    groups = [
        ("번역투", TRANSLATIONESE),
        ("직역 의심", CALQUE),
        ("직역 구문", CALQUE_SYNTAX),
        ("상투구", CLICHE),
        ("AI 말투", AI_TONE),
    ]
    if genre == "report":
        groups.append(("구어", COLLOQUIAL))
    if genre == "ui":
        groups.append(("UI 번역투", UI_TRANSLATIONESE))
    return groups


def text_hits(text: str, genre: str = "general") -> list[tuple[str, str]]:
    """문장이나 문구 하나에서 걸리는 (분류, 이유) 목록. 테스트도 이 함수를 쓴다."""
    found = []
    for char, why in BANNED_CHARS.items():
        if char in text:
            found.append((f"금칙문자 '{char}'", why))
    for label, patterns in pattern_groups(genre):
        for pattern, why in patterns:
            if re.search(pattern, text):
                found.append((label, why))
    if genre != "ui" and "?" not in text and INTERROGATIVE.search(text):
        found.append(("의문형 종결", "물음표 없는 자문자답은 지운다"))
    return found


def heading_hits(title: str, genre: str = "report") -> list[tuple[str, str]]:
    found = []
    if EMOJI_HEAD.match(title):
        found.append(("이모지 머리말", "제목 앞 이모지를 지운다"))
    tail_ok = any(title.endswith(tail) for tail in HEADING_OK_TAIL)
    if genre == "report" and not tail_ok and HEADING_BAD_END.search(title):
        found.append(("제목 종결", "체언으로 끝낼 것"))
    return found


def strip_tags(text: str) -> str:
    """HTML은 태그를 걷어낸 뒤 검사한다. 안 그러면 내용이 통째로 skip된다."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    return TAG_RE.sub(" ", text)


def headings(text: str):
    """마크다운 #과 <h1>~<h3>을 제목으로 뽑는다."""
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        m = HEADING_RE.match(line)
        if m:
            title = (m.group(1) or m.group(2) or "").strip()
            title = TAG_RE.sub("", title).strip()
            if title:
                out.append((i, title))
    return out


def is_skippable(line: str) -> bool:
    """표 행, HTML 표 셀, 링크 목록, 코드 블록은 검사하지 않는다."""
    s = line.strip()
    return (
        s.startswith(("|", "```", "> ", "<"))
        or s.startswith("- [")
        or "](http" in s
    )


def json_strings(obj, prefix=""):
    """중첩 JSON에서 (키 경로, 문자열 값)을 꺼낸다."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from json_strings(val, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(obj, list):
        for idx, val in enumerate(obj):
            yield from json_strings(val, f"{prefix}[{idx}]")
    elif isinstance(obj, str):
        yield prefix, obj


def check_strings(path: str, text: str, genre: str) -> int:
    """문구 단위 검사. JSON이면 값만, 텍스트면 줄 단위로 본다."""
    if path.lower().endswith(".json"):
        try:
            items = list(json_strings(json.loads(text)))
        except json.JSONDecodeError as exc:
            print(f"\n=== {path} ===\n  JSON 파싱 실패: {exc}")
            return 1
    else:
        items = [(str(i), line) for i, line in enumerate(text.split("\n"), 1) if line.strip()]

    print(f"\n=== {path}  {genre} 모드, 문구 {len(items)}개 ===")
    hits = 0
    for where, value in items:
        for label, why in text_hits(value, genre):
            flat = value.replace("\n", " ")
            shown = flat if len(flat) <= 60 else flat[:60] + "..."
            print(f"  [{where}] {label}: {why}\n      {shown}")
            hits += 1
    print(f"  → {hits}건" if hits else "  → 이상 없음")
    return hits


def check_document(path: str, text: str, genre: str) -> int:
    """문서 단위 검사. 제목, 문장 길이, 표 무결성까지 본다."""
    raw = text
    is_html = path.lower().endswith((".html", ".htm")) or "<h1" in text or "<p " in text
    if is_html:
        text = strip_tags(text)

    lines = text.split("\n")
    body = re.sub(r"\s", "", re.sub(r"^[|\-].*$", "", text, flags=re.M))
    bold = text.count("**") // 2
    markers = text.count("[확인 필요")

    print(f"\n=== {path}  {genre} 모드, 산문 {len(body)}자, 볼드 {bold}, 마커 {markers} ===")
    hits = 0

    for ln, title in headings(raw):
        for label, why in heading_hits(title, genre):
            print(f"  [{ln}] {label}: {why}: {title}")
            hits += 1

    in_code = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or is_skippable(line):
            continue

        for label, why in text_hits(line, genre):
            print(f"  [{i}] {label}: {why}")
            hits += 1

        # 문장 분리: 종결부호 뒤에 **, ) 같은 마크업이 붙어도 끊는다
        for sent in re.split(r"(?<=[.!?다])[*_)\]\s]*\s+", line):
            # 나열 접미(거나, 도)와 수치 목록은 쉼표 난사가 아니다
            enum = len(re.findall(r"(?:거나|[가-힣]도|\d|%)\s*,", sent))
            if sent.count(",") >= 3 and enum < sent.count(","):
                print(f"  [{i}] 쉼표 3개 이상: {sent[:40]}...")
                hits += 1
            n = len(re.sub(r"\s", "", sent))
            if n > 110:
                print(f"  [{i}] {n}자 문장: 끊어 쓸 것")
                hits += 1

    # 표 무결성: 표 사이에 문단이 끼어 아래 행이 표 밖으로 떨어졌는지
    blocks, cur = [], []
    for i, line in enumerate(lines):
        if line.startswith("|"):
            cur.append(i)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    for a, b in zip(blocks, blocks[1:]):
        gap = b[0] - a[-1]
        same_cols = lines[a[0]].count("|") == lines[b[0]].count("|")
        if gap <= 4 and same_cols and not lines[b[0]].startswith("| ---"):
            print(f"  [{a[-1] + 1}행↔{b[0] + 1}행] 표 분단 의심: 문단이 표 중간에 끼었는지 확인")
            hits += 1

    print(f"  → {hits}건" if hits else "  → 이상 없음")
    return hits


def check(path: str, genre: str | None) -> int:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        print(f"\n=== {path} ===\n  읽기 실패: {exc}")
        return 1
    is_json = path.lower().endswith(".json")
    resolved = genre or ("ui" if is_json else "general")
    if is_json or resolved == "ui":
        return check_strings(path, text, resolved)
    return check_document(path, text, resolved)


def main() -> None:
    args = sys.argv[1:]
    strict = "--strict" in args
    genre = None
    paths = []
    skip = False
    for i, arg in enumerate(args):
        if skip:
            skip = False
        elif arg == "--genre":
            genre = args[i + 1] if i + 1 < len(args) else ""
            skip = True
        elif arg.startswith("--genre="):
            genre = arg.split("=", 1)[1]
        elif arg == "--ui":
            genre = "ui"
        elif arg != "--strict":
            paths.append(arg)
    if genre is not None and genre not in GENRES:
        print(f"--genre는 {', '.join(GENRES)} 가운데 하나여야 합니다.")
        sys.exit(2)
    if not paths:
        print(__doc__)
        sys.exit(2)

    total = sum(check(p, genre) for p in paths)
    print(f"\n총 {total}건")
    sys.exit(1 if strict and total else 0)


if os.environ.get("NATURAL_KOREAN_NO_LOCAL") != "1":
    for _warning in load_local(Path(__file__).parent / "local" / "patterns.json"):
        print(f"경고: {_warning}", file=sys.stderr)

if __name__ == "__main__":
    main()
