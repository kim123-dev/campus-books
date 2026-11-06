import bcrypt


# 솔트를 매번 새로 만들어, 같은 비밀번호라도 해시가 달라지게 한다.
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# 해시 안에 솔트가 들어 있어서 별도 저장 없이 검증할 수 있다. (2단계 로그인에서 사용)
def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
