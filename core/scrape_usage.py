from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import settings
from models import AuthorDailyUsage


def _seconds_until_next_utc_day(now_utc: datetime) -> int:
    tomorrow = now_utc.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, time.min, tzinfo=timezone.utc)
    return max(1, int((next_midnight - now_utc).total_seconds()))


def enforce_daily_scrape_limit(db: Session, author_id: str) -> None:
    normalized_author_id = (author_id or "").strip()
    if not normalized_author_id:
        raise HTTPException(status_code=400, detail="authorId is required for scrape rate limiting.")

    daily_limit = max(0, settings.SCRAPE_DAILY_LIMIT)
    if daily_limit == 0:
        return

    today_utc: date = datetime.now(timezone.utc).date()
    now_utc = datetime.now(timezone.utc)

    usage = (
        db.query(AuthorDailyUsage)
        .filter(
            AuthorDailyUsage.author_id == normalized_author_id,
            AuthorDailyUsage.usage_date == today_utc,
        )
        .with_for_update()
        .first()
    )

    if usage is None:
        usage = AuthorDailyUsage(
            author_id=normalized_author_id,
            usage_date=today_utc,
            scrape_requests_count=1,
        )
        db.add(usage)
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            usage = (
                db.query(AuthorDailyUsage)
                .filter(
                    AuthorDailyUsage.author_id == normalized_author_id,
                    AuthorDailyUsage.usage_date == today_utc,
                )
                .with_for_update()
                .first()
            )

    if usage.scrape_requests_count >= daily_limit:
        retry_after = _seconds_until_next_utc_day(now_utc)
        raise HTTPException(
            status_code=429,
            detail=f"Daily scrape limit exceeded for authorId. Limit: {daily_limit} requests per UTC day.",
            headers={"Retry-After": str(retry_after)},
        )

    usage.scrape_requests_count += 1
    db.commit()
