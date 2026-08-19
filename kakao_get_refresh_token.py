#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카카오톡 '나에게 보내기' 알림을 쓰기 위해 최초 1회만 실행하는 스크립트입니다.
내 컴퓨터에서 실행하세요 (GitHub Actions 안에서는 실행 불가 - 브라우저 로그인이 필요합니다).

사용 순서:
1. https://developers.kakao.com 에서 애플리케이션 생성
2. [카카오 로그인] 활성화, Redirect URI 에 http://localhost:8888/callback 등록
3. [카카오 로그인 > 동의항목] 에서 "카카오톡 메시지 전송(talk_message)" 항목을
   '필수 동의' 또는 '선택 동의'로 설정 (팀 관리자 승인 필요할 수 있음)
4. 아래 REST_API_KEY 값을 [내 애플리케이션 > 앱 키 > REST API 키] 값으로 교체
5. 이 스크립트를 실행: python kakao_get_refresh_token.py
6. 브라우저가 열리면 카카오 로그인 & 동의
7. 터미널에 출력되는 refresh_token 값을 복사해서
   GitHub 저장소 Secret 인 KAKAO_REFRESH_TOKEN 에 등록
"""

import http.server
import threading
import urllib.parse
import webbrowser
import requests

REST_API_KEY = "여기에_카카오_REST_API_키를_입력하세요"
REDIRECT_URI = "http://localhost:8888/callback"

AUTH_URL = (
    "https://kauth.kakao.com/oauth/authorize"
    f"?client_id={REST_API_KEY}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
    "&response_type=code"
    "&scope=talk_message"
)

_code_holder = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _code_holder["code"] = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("인증이 완료되었습니다. 이 창은 닫으셔도 됩니다.".encode("utf-8"))

    def log_message(self, format, *args):
        pass  # 콘솔에 요청 로그 안 찍기


def main():
    if REST_API_KEY.startswith("여기에"):
        print("먼저 이 파일 상단의 REST_API_KEY 값을 채워주세요.")
        return

    server = http.server.HTTPServer(("localhost", 8888), _CallbackHandler)
    t = threading.Thread(target=server.handle_request)
    t.start()

    print("브라우저에서 카카오 로그인 창을 엽니다...")
    webbrowser.open(AUTH_URL)
    t.join()

    code = _code_holder.get("code")
    if not code:
        print("인증 코드를 받지 못했습니다. 다시 시도해주세요.")
        return

    resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": REST_API_KEY,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\n===== 토큰 발급 완료 =====")
    print("access_token :", tokens.get("access_token"))
    print("refresh_token:", tokens.get("refresh_token"))
    print("\n이 refresh_token 값을 GitHub Secret KAKAO_REFRESH_TOKEN 에 등록하세요.")


if __name__ == "__main__":
    main()
