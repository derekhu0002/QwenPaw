"""生成 demo-rbac 自包含 JWT 密钥与 Token（不依赖 agentgateway-main）。"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ISSUER = "agentgateway.dev"
AUDIENCE = "test.agentgateway.dev"
EXP = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp())
DIR = Path(__file__).resolve().parent


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jwk_thumbprint(kty: str, crv: str, x: str, y: str) -> str:
    payload = json.dumps({"crv": crv, "kty": kty, "x": x, "y": y}, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).digest()
    return b64url(digest)


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    numbers = public_key.public_numbers()
    x = b64url(numbers.x.to_bytes(32, "big"))
    y = b64url(numbers.y.to_bytes(32, "big"))
    kid = jwk_thumbprint("EC", "P-256", x, y)

    jwks = {
        "keys": [
            {
                "use": "sig",
                "kty": "EC",
                "kid": kid,
                "crv": "P-256",
                "alg": "ES256",
                "x": x,
                "y": y,
            }
        ]
    }
    (DIR / "pub-key").write_text(json.dumps(jwks, indent=2) + "\n", encoding="utf-8")

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    (DIR / "priv-key.pem").write_bytes(pem)

    profiles = {
        "employeeQwenpaw.key": {
            "sub": "employeeQwenpaw",
            "roles": ["employee"],
        },
        "managerQwenpaw.key": {
            "sub": "managerQwenpaw",
            "roles": ["manager"],
        },
    }

    for filename, extra in profiles.items():
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": EXP,
            "sub": extra["sub"],
            "roles": extra["roles"],
        }
        token = jwt.encode(
            claims,
            private_key,
            algorithm="ES256",
            headers={"kid": kid, "typ": "JWT"},
        )
        (DIR / filename).write_text(token + "\n", encoding="utf-8")
        print(f"Wrote {filename}  sub={extra['sub']}  roles={extra['roles']}")

    update_inspector_helper(
        (DIR / "employeeQwenpaw.key").read_text(encoding="utf-8").strip(),
        (DIR / "managerQwenpaw.key").read_text(encoding="utf-8").strip(),
    )
    print(f"Wrote pub-key (kid={kid})")


def update_inspector_helper(employee_token: str, manager_token: str) -> None:
    helper = DIR.parent / "inspector-helper.html"
    if not helper.is_file():
        return
    text = helper.read_text(encoding="utf-8")
    start = '    const TOKENS = {'
    end = '    };'
    i = text.find(start)
    j = text.find(end, i)
    if i < 0 or j < 0:
        return
    block = (
        f'    const TOKENS = {{\n'
        f'      employee: "Bearer {employee_token}",\n'
        f'      manager: "Bearer {manager_token}"\n'
        f'    }};'
    )
    helper.write_text(text[:i] + block + text[j + len(end) :], encoding="utf-8")
    print("Updated inspector-helper.html")


if __name__ == "__main__":
    main()
