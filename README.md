# 뉴항구호 좌석 감시 알림 봇

삼길포 선상낚시(daebak.sunsang24.com) 예약 페이지를 주기적으로 확인해서
**뉴항구호**에 "예약마감" → "남은자리"로 바뀌는 순간 카카오톡 + 휴대폰 푸시로 동시에 알려줍니다.

내 컴퓨터를 계속 켜둘 필요 없이 **GitHub Actions**(무료)가 자동으로 10분마다 대신 확인해줍니다.

---

## 전체 구조

```
매 10분 (GitHub Actions 스케줄)
   └─ monitor.py 실행
        ├─ daebak.sunsang24.com 페이지 읽기
        ├─ 뉴항구호 좌석 상태 파싱
        ├─ state.json 과 비교해서 "새로 열린 자리"만 골라내기
        └─ 새 자리가 있으면 알림 전송
             ├─ ntfy.sh → 휴대폰 푸시알림
             └─ 카카오 API → 카카오톡 "나에게 보내기"
```

---

## 1단계. 휴대폰 푸시알림 설정 (ntfy) — 5분

가장 간단한 채널이니 먼저 이것부터 켜두는 걸 추천합니다.

1. 휴대폰에 **ntfy** 앱 설치 ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347))
2. 앱에서 "+"로 새 구독 추가 → 토픽 이름을 아무 영문/숫자 조합으로 정하기
   (예: `newhangu-boat-alert-8281`, 남이 못 맞히게 조금 길고 특이하게 짓는 걸 추천)
3. 이 토픽 이름을 아래 3단계에서 `NTFY_TOPIC` 시크릿 값으로 사용

---

## 2단계. 카카오톡 "나에게 보내기" 설정 — 15분 (선택)

카카오톡 알림까지 원하면 아래 과정이 필요합니다. (조금 번거로우니, 귀찮으면 1단계 푸시알림만 쓰고 이 단계는 건너뛰어도 됩니다)

1. [카카오 디벨로퍼스](https://developers.kakao.com) 접속 → 로그인 → 애플리케이션 추가
2. 앱 선택 → **제품 설정 > 카카오 로그인** → 활성화 ON
3. **카카오 로그인 > Redirect URI** 에 `http://localhost:8888/callback` 등록
4. **카카오 로그인 > 동의항목** 에서 "카카오톡 메시지 전송" (talk_message) 항목 설정
   - 개인 개발자 계정은 별도 검수 없이 "나에게 보내기" 용도로 사용 가능합니다
5. **앱 키** 메뉴에서 **REST API 키** 복사
6. 이 프로젝트의 `kakao_get_refresh_token.py` 파일을 내 컴퓨터에서 열어
   `REST_API_KEY = "..."` 부분에 방금 복사한 키를 붙여넣기
7. 터미널에서 실행:
   ```bash
   pip install requests
   python kakao_get_refresh_token.py
   ```
8. 브라우저가 열리면 카카오 로그인 → 동의
9. 터미널에 출력된 `refresh_token` 값을 복사해두기 (3단계에서 사용)

---

## 3단계. GitHub 저장소 만들고 코드 올리기

1. GitHub 에서 새 저장소 생성 (알림 내용이 민감하지 않다면 **Public**으로 만들면
   Actions 사용 시간이 무제한 무료입니다. Private 저장소는 매달 무료 사용시간이
   제한되어 있어 10분 주기로는 시간이 모자를 수 있습니다.)
2. 이 폴더(`boat-seat-monitor`)의 모든 파일을 그대로 저장소에 업로드/푸시
3. 저장소 **Settings > Secrets and variables > Actions > New repository secret**
   에서 아래 값들을 등록:

   | 이름 | 값 |
   |---|---|
   | `NTFY_TOPIC` | 1단계에서 정한 토픽 이름 |
   | `KAKAO_REST_API_KEY` | (카카오 알림 사용 시) REST API 키 |
   | `KAKAO_REFRESH_TOKEN` | (카카오 알림 사용 시) 2단계에서 얻은 refresh_token |

4. 저장소 **Settings > Actions > General > Workflow permissions** 에서
   "Read and write permissions" 로 설정 (state.json 자동 커밋을 위해 필요)
5. **Actions** 탭 → `뉴항구호 좌석 감시` 워크플로우 선택 → **Run workflow** 로
   한 번 수동 실행해서 정상 동작하는지 확인

이후로는 10분마다 자동으로 확인하고, 뉴항구호에 자리가 새로 나면 알림이 옵니다.

---

## 커스터마이징

- **다른 선박으로 감시 대상 변경**: `monitor.py` 상단 또는 워크플로우 env에
  `TARGET_BOAT` 값을 `뉴항구1호` 또는 `레전드호` 등으로 바꾸면 됩니다.
- **확인 주기 변경**: `.github/workflows/monitor.yml` 의
  `cron: "*/10 * * * *"` 부분을 원하는 주기로 수정 (너무 잦으면 사이트에
  부담을 줄 수 있으니 5분 미만은 권장하지 않습니다).
- **확인할 달 지정**: 기본값은 이번 달 + 다음 달을 자동으로 봅니다.
  특정 달만 보고 싶으면 워크플로우에 `MONTHS: "202610,202611"` 처럼
  환경변수를 추가하세요.

---

## 참고 / 주의사항

- 이 스크립트는 대박(daebak.sunsang24.com) 사이트가 공개적으로 보여주는
  예약 현황 페이지를 그대로 읽어오는 개인용 도구입니다. 사이트 구조가
  바뀌면 파싱 로직(`monitor.py`의 정규식)을 손봐야 할 수 있습니다.
- 너무 잦은 요청은 사이트에 부담을 줄 수 있으니 확인 주기는 여유 있게
  잡는 것을 권장합니다.
- 카카오 refresh_token 은 카카오 정책에 따라 자동 갱신될 수 있고, 그 경우
  `monitor.py` 실행 로그(Actions 로그)에 새 토큰이 출력됩니다 — 이때는
  GitHub Secret `KAKAO_REFRESH_TOKEN` 값을 새 값으로 교체해주세요.
