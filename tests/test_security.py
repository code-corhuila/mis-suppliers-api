from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from app.security import Tokens


@pytest.fixture(scope="module")
def pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def token(private, **changes):
    claims = {"sub": str(uuid4()), "iss": "mis-security", "aud": "mis-api",
              "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "roles": ["ADMIN"], **changes}
    if claims["exp"] is None:
        del claims["exp"]
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"})


@pytest.mark.parametrize("role", ["ADMIN", "INVENTORY", "SUPERVISOR", "CONSULTATION"])
def test_four_roles(pair, role):
    assert Tokens.decode(token(pair[0], roles=[role]), pair[1])["roles"] == [role]


@pytest.mark.parametrize("changes", [
    {"iss": "wrong"}, {"aud": "wrong"}, {"sub": "invalid"}, {"roles": []}, {"roles": ["UNKNOWN"]},
    {"roles": "ADMIN"}, {"exp": None}, {"exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
])
def test_invalid_claims(pair, changes):
    with pytest.raises(jwt.InvalidTokenError):
        Tokens.decode(token(pair[0], **changes), pair[1])


def test_other_signature(pair):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidTokenError):
        Tokens.decode(token(other), pair[1])


def test_hmac_and_unsigned(pair):
    for algorithm in ("HS256", "none"):
        forged = jwt.encode({"sub": str(uuid4()), "roles": ["ADMIN"]},
            "x" * 32 if algorithm == "HS256" else None, algorithm=algorithm, headers={"kid": "test-key"})
        with pytest.raises(jwt.InvalidTokenError):
            Tokens.decode(forged, pair[1])


@pytest.mark.parametrize("header", [None, "", "Basic value", "Bearer", "Bearer a b", "Bearer invalid"])
def test_invalid_authorization_is401_without_jwks_fetch(header):
    from unittest.mock import Mock
    from app.core import Failure
    validator = Tokens("http://unused.invalid/jwks"); validator.keys = Mock()
    with pytest.raises(Failure) as error:
        validator.authenticate(header)
    assert error.value.status == 401
    validator.keys.get_signing_key_from_jwt.assert_not_called()


def test_authenticate_accepts_verified_token(pair):
    from types import SimpleNamespace
    from unittest.mock import Mock
    validator = Tokens("http://unused.invalid/jwks"); validator.keys = Mock()
    encoded = token(pair[0])
    validator.keys.get_signing_key_from_jwt.return_value = SimpleNamespace(key=pair[1])
    assert validator.authenticate("bearer " + encoded)["roles"] == ["ADMIN"]
    validator.keys.get_signing_key_from_jwt.assert_called_once_with(encoded)


@pytest.mark.parametrize("failure,status", [(jwt.PyJWKClientConnectionError, 503), (jwt.PyJWKClientError, 401)])
def test_jwks_failures_have_safe_distinct_statuses(pair, failure, status):
    from unittest.mock import Mock
    from app.core import Failure
    validator = Tokens("http://unused.invalid/jwks"); validator.keys = Mock()
    validator.keys.get_signing_key_from_jwt.side_effect = failure("private-debug-details")
    with pytest.raises(Failure) as error:
        validator.authenticate("Bearer " + token(pair[0]))
    assert error.value.status == status and "private-debug-details" not in str(error.value)
