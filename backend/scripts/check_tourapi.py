import os, urllib.request, urllib.parse
k = os.environ["DATA_GO_KR_KEY_DECODING"]
for s in ["KorService2", "EngService2", "JpnService2", "ChtService2", "ChsService2"]:
    q = urllib.parse.urlencode({"serviceKey": k, "MobileOS": "ETC", "MobileApp": "aws5", "_type": "json", "keyword": "Haeundae" if s != "KorService2" else "해운대", "numOfRows": 1, "pageNo": 1})
    try:
        r = urllib.request.urlopen(f"https://apis.data.go.kr/B551011/{s}/searchKeyword2?{q}", timeout=10).read().decode("utf-8", "replace")
        print(s, r[:250].replace(k, "***"))
    except Exception as e:
        print(s, "ERR", e)
