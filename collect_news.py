name: 뉴스 자동 수집

on:
  schedule:
    # 매 시간 정각과 30분에 실행 (UTC 기준 = 한국시간 +9시간이지만 간격은 동일)
    - cron: '0,30 * * * *'
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - name: 코드 가져오기
        uses: actions/checkout@v4

      - name: Python 설정
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 뉴스 수집 실행
        run: python collect_news.py

      - name: 수집 시각 확인
        run: echo "한국시간 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M') 수집 완료"
