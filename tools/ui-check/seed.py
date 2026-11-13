import json, os, secrets, sqlite3, sys, urllib.parse, urllib.request
BASE = os.environ.get("UI_CHECK_BASE", "http://127.0.0.1:" + os.environ.get("UI_CHECK_PORT", "8001"))
db_path, out = sys.argv[1], sys.argv[2]
def call(method, path, body=None, token=None, form=False):
    data = None; headers = {}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode(); headers["Content-Type"]="application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode(); headers["Content-Type"]="application/json"
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE+path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r: return json.loads(r.read() or "null")
pw = secrets.token_urlsafe(12)
tokens = {}
for email, nick in [("seller@uicheck.ac.kr","판매자민수"),("buyer@uicheck.ac.kr","구매자지은")]:
    call("POST","/auth/signup",{"email":email,"password":pw,"nickname":nick,"security_question":{"question_key":"CHILDHOOD_SHOP","answer":"확인용가게"}})
    tokens[nick] = call("POST","/auth/login",{"username":email,"password":pw},form=True)["access_token"]
s, b = tokens["판매자민수"], tokens["구매자지은"]
p1 = call("POST","/posts",{"title":"자료구조 교재 팝니다 (필기 거의 없음)","book_title":"C언어로 쉽게 풀어쓴 자료구조","course_name":"자료구조","condition":"GOOD","price":15000,"open_chat_url":"https://open.kakao.com/o/sTest123"},s)
p2 = call("POST","/posts",{"title":"운영체제 공룡책","book_title":"Operating System Concepts","condition":"FAIR","price":20000},s)
p3 = call("POST","/posts",{"title":"선형대수 교재 나눔","book_title":"선형대수학","condition":"POOR","price":0},b)
c1 = call("POST",f"/posts/{p1['id']}/conversations",None,b)
c2 = call("POST",f"/posts/{p2['id']}/conversations",None,b)
c3 = call("POST",f"/posts/{p3['id']}/conversations",None,s)
# 이전 메시지 불러오기 확인용으로 c1에 40개를 직접 넣는다. (도배 제한을 피하려고 DB에 직접)
con = sqlite3.connect(db_path)
sid = call("GET","/users/me",None,s)["id"]; bid = call("GET","/users/me",None,b)["id"]
for i in range(40):
    sender = bid if i % 2 == 0 else sid
    text = f"{i+1}번째 메시지입니다." + ("\n줄바꿈도 그대로 보여야 해요." if i % 7 == 0 else "")
    con.execute("insert into messages(conversation_id,sender_id,content,created_at,read_at) values (?,?,?,datetime('now', ?), case when ? then datetime('now') else null end)",
                (c1["id"], sender, text, f"-{(40-i)*60} seconds", i < 34))
last = con.execute("select id, created_at from messages where conversation_id=? order by id desc limit 1",(c1["id"],)).fetchone()
con.execute("update conversations set last_message_id=?, last_message_at=? where id=?",(last[0], last[1], c1["id"]))
con.commit()
call("POST",f"/conversations/{c3['id']}/messages",{"content":"나눔 아직 가능한가요? 내일 학생회관 앞에서 받을 수 있을까요?"},s)
call("POST",f"/conversations/{c2['id']}/messages",{"content":"<script>alert(1)</script> 이 문자열은 글자로만 보여야 합니다"},b)
json.dump({"seller_token":s,"buyer_token":b,"p1":p1["id"],"p2":p2["id"],"p3":p3["id"],"c1":c1["id"],"c2":c2["id"],"c3":c3["id"]}, open(out,"w"))
print("seeded", {k:v for k,v in [("p1",p1["id"]),("c1",c1["id"]),("c2",c2["id"]),("c3",c3["id"])]})
