"""요청한 사람의 IP. 횟수 제한(로그인, 비밀번호 재설정)이 IP별로 세는 데 쓴다.

운영(Railway)에서는 앱 앞에 프록시가 있어 TCP 접속 주소는 항상 프록시다. 실제 주소는 X-Forwarded-For에 있다.
- uvicorn --forwarded-allow-ips='*'는 X-Forwarded-For의 "맨 왼쪽" 값을 request.client로 넣는데,
  맨 왼쪽은 요청한 사람이 헤더에 직접 적어 보낼 수 있는 값이라 그대로 믿으면 요청마다 IP를 바꿔 제한을 피할 수 있다.
- 프록시는 받은 접속 주소를 헤더 "오른쪽 끝"에 붙인다. 그래서 오른쪽부터 보면서 프록시 내부망 주소(사설·루프백 등)를
  건너뛰고 처음 나오는 공인 주소를 실제 접속 주소로 쓴다. 그보다 왼쪽은 요청한 사람이 지어낼 수 있으므로 보지 않는다.
- 헤더가 없거나 공인 주소가 없으면(로컬 개발·테스트) TCP 접속 주소를 쓴다.
"""

import ipaddress

from fastapi import Request


def client_ip(request: Request) -> str:
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
