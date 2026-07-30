#!/usr/bin/env python3
"""
네이버 금융 리서치 6개 카테고리를 스크래핑해서
각 카테고리별 RSS XML 파일을 생성한다.

대상:
- 시황정보 (market_info)
- 투자정보 (invest)
- 종목분석 (company)   -- 6열 구조 (종목명 포함)
- 산업분석 (industry)  -- 6열 구조 (업종명 포함)
- 경제분석 (economy)
- 채권분석 (debenture)

결과: docs/<카테고리>.xml (개별 피드) + docs/all.xml (통합 피드)
"""

import datetime
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

BASE = "https://finance.naver.com/research/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# (카테고리 키, 목록 파일명, 표시 이름, 6열 구조 여부)
CATEGORIES = [
    ("market_info", "market_info_list.naver", "시황정보", False),
    ("invest", "invest_list.naver", "투자정보", False),
    ("company", "company_list.naver", "종목분석", True),
    ("industry", "industry_list.naver", "산업분석", True),
    ("economy", "economy_list.naver", "경제분석", False),
    ("debenture", "debenture_list.naver", "채권분석", False),
]

MAX_ITEMS_PER_PAGE = 30  # 페이지당 최대 수집 개수 (안전 상한)


def fetch_list(list_file):
    """목록 페이지를 가져와 BeautifulSoup 객체로 반환한다."""
    url = BASE + list_file
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.encoding = "euc-kr"
    return BeautifulSoup(res.text, "html.parser")


def parse_rows(soup, has_extra_col):
    """
    테이블 행을 파싱해 리포트 목록(dict 리스트)으로 반환한다.
    has_extra_col=True 이면 종목명/업종명 열이 앞에 하나 더 있는 구조.
    """
    table = soup.find("table", class_="type_1")
    if table is None:
        return []

    reports = []
    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        min_len = 6 if has_extra_col else 5
        if len(cells) < min_len:
            continue

        title_idx = 1 if has_extra_col else 0
        attach_idx = title_idx + 2

        title_tag = cells[title_idx].find("a")
        if title_tag is None:
            continue

        title = title_tag.get_text(strip=True)
        title_href = title_tag.get("href", "")
        # 상대경로면 절대경로로 변환
        if title_href and not title_href.startswith("http"):
            link = BASE + title_href
        else:
            link = title_href

        attach_tag = cells[attach_idx].find("a") if len(cells) > attach_idx else None
        attach_href = attach_tag.get("href") if attach_tag else None

        broker = cells[title_idx + 1].get_text(strip=True)
        date_str = cells[title_idx + 3].get_text(strip=True) if len(cells) > title_idx + 3 else ""

        subject = cells[0].get_text(strip=True) if has_extra_col else None

        reports.append({
            "title": f"[{subject}] {title}" if subject else title,
            "link": link,
            "broker": broker,
            "date_str": date_str,
            "attach": attach_href,
        })

        if len(reports) >= MAX_ITEMS_PER_PAGE:
            break

    return reports


def parse_date(date_str):
    """'26.07.30' 형식을 datetime으로 변환. 실패하면 현재 시각 사용."""
    try:
        parsed = datetime.datetime.strptime(date_str, "%y.%m.%d")
        return parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
    except ValueError:
        return datetime.datetime.now(datetime.timezone.utc)


def build_feed(title, link, description, reports):
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.description(description)
    fg.language("ko")

    for r in reports:
        fe = fg.add_entry()
        fe.title(r["title"])
        fe.link(href=r["link"])
        summary = f"{r['broker']} · {r['date_str']}"
        if r["attach"]:
            summary += f" · 첨부: {r['attach']}"
        fe.description(summary)
        fe.pubDate(parse_date(r["date_str"]))

    return fg


def main():
    all_reports_by_cat = {}

    for key, list_file, name, has_extra_col in CATEGORIES:
        print(f"수집 중: {name} ({list_file})")
        try:
            soup = fetch_list(list_file)
            reports = parse_rows(soup, has_extra_col)
            print(f"  -> {len(reports)}건 수집")
            all_reports_by_cat[key] = (name, reports)
        except Exception as e:
            print(f"  !! 오류: {e}")
            all_reports_by_cat[key] = (name, [])

        # 개별 피드 생성
        fg = build_feed(
            title=f"네이버 금융 리서치 - {name}",
            link=BASE + list_file,
            description=f"네이버 금융 {name} 리포트 자동 수집 피드",
            reports=all_reports_by_cat[key][1],
        )
        fg.rss_file(f"docs/{key}.xml")

    # 통합 피드 생성 (전체 카테고리를 한 파일에)
    fg_all = FeedGenerator()
    fg_all.title("네이버 금융 리서치 - 전체")
    fg_all.link(href=BASE, rel="alternate")
    fg_all.description("네이버 금융 리서치 6개 카테고리 통합 피드")
    fg_all.language("ko")

    for key, (name, reports) in all_reports_by_cat.items():
        for r in reports:
            fe = fg_all.add_entry()
            fe.title(f"[{name}] {r['title']}")
            fe.link(href=r["link"])
            summary = f"{r['broker']} · {r['date_str']}"
            if r["attach"]:
                summary += f" · 첨부: {r['attach']}"
            fe.description(summary)
            fe.pubDate(parse_date(r["date_str"]))

    fg_all.rss_file("docs/all.xml")

    total = sum(len(v[1]) for v in all_reports_by_cat.values())
    print(f"\n완료: 총 {total}건 수집, docs/ 폴더에 XML 생성됨")


if __name__ == "__main__":
    main()
