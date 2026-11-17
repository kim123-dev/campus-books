"""요청한 사람의 IP. 횟수 제한(로그인, 비밀번호 재설정)이 IP별로 세는 데 쓴다.

운영(Railway)에서는 앱 앞에 엣지 프록시(와 CDN)가 있어 TCP 접속 주소는 항상 프록시다.
- X-Real-IP: Railway 엣지가 공개 접속마다 실제 접속 주소로 채운다(Railway 안내). 있으면 이것을 쓴다.
- X-Forwarded-For는 쓰지 않는 쪽을 우선한다. 맨 왼쪽은 요청한 사람이 지어낼 수 있고(uvicorn --forwarded-allow-ips='*'가
  request.client에 넣는 값), 오른쪽 끝에는 CDN 노드의 공인 주소가 붙어 요청마다 바뀔 수 있다.
  (실제로 "오른쪽 첫 공인 주소" 방식은 운영에서 요청마다 다른 IP로 세어져 제한이 걸리지 않았다)
- X-Real-IP가 없을 때만(로컬 개발·다른 배포 환경) X-Forwarded-For를 오른쪽부터 보며 사설·루프백 주소를 건너뛴
  첫 공인 주소를, 그것도 없으면 TCP 접속 주소를 쓴다.
"""

import ipaddress

from fastapi import Request


def client_ip(request: Request) -> str:
    real = _parse(request.headers.get("x-real-ip", ""))
    if real is not None:
        return str(real)
    header = ",".join(request.headers.getlist("x-forwarded-for"))
    for raw in reversed(header.split(",")):
        address = _parse(raw)
        if address is not None and address.is_global:
            return str(address)
    return request.client.host if request.client else "unknown"


def _parse(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    value = raw.strip()
    # "1.2.3.4:5678", "[2001:db8::1]:443" 같은 포트 표기도 받아 준다.
    if value.startswith("["):
        value = value[1:].split("]", 1)[0]
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    # IPv4를 담은 IPv6(::ffff:1.2.3.4)는 IPv4로 본다. 같은 사람이 두 형식으로 따로 세지지 않게.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address
