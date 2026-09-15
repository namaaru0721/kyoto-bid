name: 京都入札モニター

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          
      - run: pip install playwright requests && playwright install chromium
      
      - run: python main.py
      - run: python kyoto_city.py
      
      - name: Commit and push changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add -A
          git diff --staged --quiet || git commit -m "Auto update cache"
          git push
