#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
뉴항구호(삼길포 선상낚시) 좌석 감시 & 알림 스크립트
--------------------------------------------------
- daebak.sunsang24.com 의 월별 출항일정 페이지를 읽어서
  지정한 선박(기본값: 뉴항구호)에 "남은자리"가 생겼는지 확인합니다.
- 이전 상태와 비교해서 "마감 -> 자리있음"으로 바뀐 날짜만 알림을 보냅니다.
- 알림 채널: ntfy.sh(휴대폰 푸시), 카카오톡 나에게 보내기 중 설정된 것만 사용됩니다.

환경변수:
  TARGET_BOAT          감시할 선박명 (기본값: 뉴항구호)
  MONTHS                감시할 연월, 콤마로 구분 (예: 202610,202611). 미지정시 이번달+다음달 자동계산
  STATE_FILE            상태 저장 파일 경로 (기본값: state.json)

  NTFY_TOPIC            ntfy.sh 토픽명 (설정 시 푸시알림 사용)
  KAKAO_REST_API_KEY    카카오 디벨로퍼스 REST API 키
  KAKAO_REFRESH_TOKEN   카카오 "나에게 보내기"용 refresh token
                         (둘 다 설정 시 카카오톡 알림 사용)
"""

import os
import re
import json
import sys
import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://daebak.sunsang24.com/ship/schedule_fleet/{yyyymm}"

TARGET_BOAT = os.environ.get("TARGET_BOAT", "뉴항구호")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()

DAY_RE = re.compile(r"(\d{1,2})월(\d{1,2})일\(([^)]+)\)")
STATUS_RE = re.compile(r"(예약마감|남은자리)\s*(\d+)\s*명")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def default_months():
    """이번달과 다음달의 YYYYMM 리스트를 반환"""
    today = datetime.date.today()
    months = []
    for offset in (0, 1):
        y, m = today.year, today.month + offset
        if m > 12:
            y += 1
            m -= 12
        months.append(f"{y}{m:02d}")
    return months


def fetch_page_text(yyyymm: str) -> str:
    url = BASE_URL.format(yyyymm=yyyymm)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n"), url


def parse_target_boat(text: str, year: int, boat_name: str):
    """
    각 날짜 블록을 잘라서 boat_name 이 등장하는 부분의
    '예약마감 N명' / '남은자리 N명' 상태를 뽑아낸다.
    """
    results = []
    day_matches = list(DAY_RE.finditer(text))
    for i, m in enumerate(day_matches):
        start = m.start()
        end = day_matches[i + 1].start() if i + 1 < len(day_matches) else len(text)
        block = text[start:end]

        idx = block.find(boat_name)
        if idx == -1:
            continue

        window = block[idx: idx + 800]
        status_m = STATUS_RE.search(window)
        if not status_m:
            continue

        status, count = status_m.group(1), int(status_m.group(2))
        month, day = int(m.group(1)), int(m.group(2))
        try:
            date_str = datetime.date(year, month, day).isoformat()
        except ValueError:
            continue

        results.append(
            {
                "date": date_str,
                "status": status,
                "seats": count,
                "available": status == "남은자리",
            }
        )
    return results


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def notify_ntfy(message: str):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Tags": "fishing_pole_and_fish,bell",
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[ntfy 알림 실패] {e}", file=sys.stderr)


def refresh_kakao_access_token():
    resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": KAKAO_REST_API_KEY,
            "refresh_token": KAKAO_REFRESH_TOKEN,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "refresh_token" in data:
        # 카카오가 새 refresh_token 을 내려주면 다음 실행부터는 이걸 써야 함
        print(
            "[안내] 카카오가 새 refresh_token 을 발급했습니다. "
            "GitHub Secret(KAKAO_REFRESH_TOKEN)을 아래 값으로 갱신하세요:\n"
            f"{data['refresh_token']}"
        )
    return data["access_token"]


def notify_kakao(message: str, link_url: str):
    if not (KAKAO_REST_API_KEY and KAKAO_REFRESH_TOKEN):
        return
    try:
        access_token = refresh_kakao_access_token()
        template = {
            "object_type": "text",
            "text": message,
            "link": {"web_url": link_url, "mobile_web_url": link_url},
            "button_title": "예약하러 가기",
        }
        resp = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {access_token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[카카오 알림 실패] {resp.status_code} {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"[카카오 알림 실패] {e}", file=sys.stderr)


def main():
    months = os.environ.get("MONTHS")
    months = [m.strip() for m in months.split(",")] if months else default_months()

    state = load_state()
    new_state = dict(state)  # 갱신해서 저장할 상태
    newly_available = []

    for yyyymm in months:
        year = int(yyyymm[:4])
        try:
            text, url = fetch_page_text(yyyymm)
        except Exception as e:
            print(f"[{yyyymm}] 페이지 조회 실패: {e}", file=sys.stderr)
            continue

        entries = parse_target_boat(text, year, TARGET_BOAT)
        for entry in entries:
            date = entry["date"]
            prev = state.get(date, {})
            was_available = prev.get("available", False)

            new_state[date] = {
                "available": entry["available"],
                "seats": entry["seats"],
                "status": entry["status"],
            }

            # 마감 -> 자리있음 으로 바뀐 경우에만 알림
            if entry["available"] and not was_available:
                newly_available.append((date, entry, url))
            # 이미 알림 보낸 날짜인데 남은자리 수가 늘어난 경우도 알림
            elif (
                entry["available"]
                and was_available
                and entry["seats"] > prev.get("seats", 0)
            ):
                newly_available.append((date, entry, url))

    if newly_available:
        for date, entry, url in newly_available:
            msg = (
                f"🎣 {TARGET_BOAT} 자리 발생!\n"
                f"날짜: {date}\n"
                f"남은자리: {entry['seats']}명\n"
                f"바로 확인: {url}"
            )
            print(msg)
            notify_ntfy(msg)
            notify_kakao(msg, url)
    else:
        print("변동 없음 (새로 열린 자리 없음)")

    save_state(new_state)


if __name__ == "__main__":
    main()
