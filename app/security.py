from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError, PyJWKClientConnectionError

from app.core import Failure

ROLES = {"ADMIN", "INVENTORY", "SUPERVISOR", "CONSULTATION"}


class Tokens:
    def __init__(self, jwks_url: str):
        self.keys = PyJWKClient(jwks_url, timeout=2, lifespan=300)

    @staticmethod
    def decode(token: str, key) -> dict:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not header["kid"]:
            raise InvalidTokenError("Invalid header")
        claims = jwt.decode(token, key, algorithms=["RS256"], audience="mis-api", issuer="mis-security",
            leeway=30, options={"require": ["sub", "exp", "iss", "aud", "roles"]})
        roles = claims["roles"]
        try:
            valid_subject = str(UUID(claims["sub"])) == claims["sub"]
        except (ValueError, TypeError, AttributeError):
            valid_subject = False
        if (not valid_subject or not isinstance(roles, list)
                or not roles or any(not isinstance(role, str) or role not in ROLES for role in roles)):
            raise InvalidTokenError("Invalid claims")
        return claims

    def authenticate(self, authorization: str | None) -> dict:
        try:
            if not authorization or len(authorization.split()) != 2:
                raise InvalidTokenError("Missing bearer")
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise InvalidTokenError("Missing bearer")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise InvalidTokenError("Invalid header")
            key = self.keys.get_signing_key_from_jwt(token).key
            return self.decode(token, key)
        except PyJWKClientConnectionError:
            raise Failure(503, "SERVICE_UNAVAILABLE", "Identidad no disponible.") from None
        except (InvalidTokenError, PyJWKClientError, ValueError, TypeError, AttributeError):
            raise Failure(401, "UNAUTHORIZED", "Autenticacion requerida.") from None
