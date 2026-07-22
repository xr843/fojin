"""OAuth must not merge into an account whose email was never proven.

`register_user` accepts a self-asserted email and there is no email
confirmation flow anywhere in the project. `_find_or_create_user` used to
match any existing row by email, so:

  1. attacker registers with victim@gmail.com (nothing is sent, nothing
     is verified)
  2. victim later signs in with Google as victim@gmail.com
  3. the Google identity is linked to the *attacker's* row and the
     callback issues a JWT for it
  4. the attacker logs in with the password they chose and reads the
     victim's sessions, bookmarks and BYOK key preview

The merge is now gated on `User.email_verified`, which is only true for
addresses an identity provider vouched for.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import hash_password
from app.models.user import SocialAccount, User
from app.services.oauth import _find_or_create_user


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (User, SocialAccount):
            await conn.run_sync(model.__table__.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _add_user(db, *, email, verified, username="victim"):
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password("attacker-chosen-pw"),
        display_name=username,
        email_verified=verified,
        last_active_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_does_not_merge_into_unverified_password_account(db):
    """The pre-hijack scenario: attacker pre-claimed the address."""
    attacker = await _add_user(db, email="victim@gmail.com", verified=False, username="attacker")

    linked = await _find_or_create_user(
        db, provider="google", provider_user_id="google-sub-123", email="victim@gmail.com", display_name="Victim"
    )

    assert linked.id != attacker.id, "Google identity was linked to the attacker's pre-claimed account"


@pytest.mark.asyncio
async def test_prehijacked_address_still_yields_a_working_account(db):
    """Refusing the merge must not turn the attack into a lockout.

    `users.email` is unique, so simply declining to merge and then creating
    a row with the same address raises IntegrityError — the victim could
    never sign in at all, which hands the attacker a denial of service
    instead of an account takeover.
    """
    await _add_user(db, email="victim@gmail.com", verified=False, username="attacker")

    linked = await _find_or_create_user(
        db, provider="google", provider_user_id="google-sub-123", email="victim@gmail.com", display_name="Victim"
    )

    assert linked.id is not None
    assert linked.email == "google_google-sub-123@noreply.fojin.app"
    assert linked.email_verified is False


@pytest.mark.asyncio
async def test_merges_into_a_verified_account(db):
    """A previously IdP-verified address is still a legitimate merge target."""
    existing = await _add_user(db, email="real@gmail.com", verified=True)

    linked = await _find_or_create_user(
        db, provider="github", provider_user_id="gh-42", email="real@gmail.com", display_name="Real"
    )

    assert linked.id == existing.id


@pytest.mark.asyncio
async def test_new_oauth_user_with_idp_email_is_marked_verified(db):
    """Providers only reach here after their own verification check."""
    user = await _find_or_create_user(
        db, provider="google", provider_user_id="sub-new", email="fresh@gmail.com", display_name="Fresh"
    )

    assert user.email_verified is True


@pytest.mark.asyncio
async def test_synthetic_placeholder_email_is_not_marked_verified(db):
    """No email from the IdP means a @noreply placeholder — never verified."""
    user = await _find_or_create_user(
        db, provider="github", provider_user_id="gh-noemail", email=None, display_name="Anon"
    )

    assert user.email.endswith("@noreply.fojin.app")
    assert user.email_verified is False


@pytest.mark.asyncio
async def test_existing_social_link_still_short_circuits(db):
    """An already-linked identity is returned regardless of email_verified."""
    user = await _add_user(db, email="linked@gmail.com", verified=False)
    db.add(SocialAccount(user_id=user.id, provider="google", provider_user_id="sub-linked"))
    await db.commit()

    found = await _find_or_create_user(
        db, provider="google", provider_user_id="sub-linked", email="linked@gmail.com", display_name="X"
    )

    assert found.id == user.id


@pytest.mark.asyncio
async def test_password_registration_defaults_to_unverified(db):
    """Must go through register_user — the column default is the invariant.

    Asserting on a hand-built User with email_verified=False proves nothing:
    it tests the literal we passed in. The thing that has to hold is that the
    *registration path*, which never sets the flag, produces an unverified
    row. (A bare `server_default="false"` string compiles to DDL `DEFAULT
    'false'`, which SQLite stores as text and reads back as True — so this
    test failing is exactly how that class of bug surfaces.)
    """
    from app.schemas.user import UserRegister
    from app.services.auth import register_user

    user = await register_user(
        db, UserRegister(username="selfsignup", email="self@example.com", password="Passw0rd1")
    )

    assert user.email_verified is False

    row = await db.scalar(select(User).where(User.id == user.id))
    assert row.email_verified is False


@pytest.mark.asyncio
async def test_a_registration_cannot_claim_the_placeholder_namespace(db):
    """Reserving @noreply.fojin.app is what makes the anti-lockout path work.

    Without it: attacker registers victim@gmail.com AND
    github_<id>@noreply.fojin.app (the id is public), the victim's first
    GitHub sign-in falls back to that placeholder, hits the unique constraint
    on users.email, and the callback's blanket `except Exception` turns it
    into ?error=github_failed forever. Two free registrations, no
    verification step, permanent lockout of a named GitHub user.
    """
    from pydantic import ValidationError

    from app.schemas.user import UserRegister

    with pytest.raises(ValidationError):
        UserRegister(username="squatter", email="github_12345@noreply.fojin.app", password="Passw0rd1")


@pytest.mark.asyncio
async def test_victim_still_signs_in_when_placeholder_is_squatted(db):
    """End-to-end version of the above, at the service layer."""
    await _add_user(db, email="victim@gmail.com", verified=False, username="attacker")
    await _add_user(db, email="github_12345@noreply.fojin.app", verified=False, username="squat")

    linked = await _find_or_create_user(
        db, provider="github", provider_user_id="12345", email="victim@gmail.com", display_name="Victim"
    )

    assert linked.id is not None
    assert linked.email_verified is False
