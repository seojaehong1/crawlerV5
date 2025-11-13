## 실행 방법

1. 가상환경을 생성하고 활성화합니다.
   - `python -m venv venv`
   - Windows: `venv\Scripts\activate`
2. 필요한 패키지를 설치합니다.
   - `pip install playwright pandas`
   - Playwright 브라우저 드라이버 초기화: `playwright install`
3. 패턴 학습 스크립트 실행:
   - `python pattern_learn.py --category-url <카테고리_URL> --pages 1 --items-per-page 0`
4. 카테고리 크롤러 실행:
   - `python test2.py --category-url <카테고리_URL> --output danawa_output.csv`

필요한 옵션은 `--help` 플래그로 확인할 수 있습니다.

