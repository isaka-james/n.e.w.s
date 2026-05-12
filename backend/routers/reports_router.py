from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from database import get_session
from models import User, CachedStories, Report
from auth import get_current_user
from fetcher import fetch_stories
from deepseek import generate_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate")
def generate(
    # Standard call — one per day, no overrides
    force: bool = Query(default=False, description="Re-run AI using today's cached stories"),
    fresh: bool = Query(default=False, description="Re-fetch news AND re-run AI (implies force)"),
    temperature: float = Query(default=0.7, ge=0.1, le=1.5),
    max_stories: int = Query(default=15, ge=3, le=25),
    use_newsdata: bool = Query(default=True),
    use_newsapi: bool = Query(default=True),
    use_newscatcher: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    today = date.today()
    do_force = force or fresh

    existing_report = session.exec(
        select(Report).where(
            Report.user_id == current_user.id,
            Report.report_date == today,
        )
    ).first()

    # Normal path — return cached report, one per day
    if existing_report and not do_force:
        return {
            "report_title": existing_report.report_title,
            "opening_line": existing_report.opening_line,
            "closing_line": existing_report.closing_line,
            "sections": existing_report.sections,
            "report_date": existing_report.report_date.isoformat(),
            "cached": True,
        }

    if existing_report:
        session.delete(existing_report)
        session.commit()

    # fresh=True also discards cached stories so news is re-fetched
    cached = session.exec(
        select(CachedStories).where(
            CachedStories.user_id == current_user.id,
            CachedStories.fetch_date == today,
        )
    ).first()

    if fresh and cached:
        session.delete(cached)
        session.commit()
        cached = None

    if cached:
        stories = cached.stories
    else:
        stories = fetch_stories(
            current_user,
            use_newsdata=use_newsdata,
            use_newsapi=use_newsapi,
            use_newscatcher=use_newscatcher,
        )
        if not stories:
            raise HTTPException(status_code=502, detail="No stories returned from any news source")

        session.add(CachedStories(
            user_id=current_user.id,
            fetch_date=today,
            stories=stories,
        ))
        session.commit()

    try:
        report_data, raw_response = generate_report(
            current_user, stories,
            temperature=temperature,
            max_stories=max_stories,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI report generation failed: {str(e)}")

    report = Report(
        user_id=current_user.id,
        report_date=today,
        report_title=report_data.get("report_title", "Today's Briefing"),
        opening_line=report_data.get("opening_line", ""),
        closing_line=report_data.get("closing_line", ""),
        sections=report_data.get("sections", {}),
        raw_response=raw_response,
    )
    session.add(report)
    session.commit()

    return {
        "report_title": report.report_title,
        "opening_line": report.opening_line,
        "closing_line": report.closing_line,
        "sections": report.sections,
        "report_date": report.report_date.isoformat(),
        "cached": False,
    }


@router.get("/today")
def get_today(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    today = date.today()
    report = session.exec(
        select(Report).where(
            Report.user_id == current_user.id,
            Report.report_date == today,
        )
    ).first()

    if not report:
        return None

    return {
        "report_title": report.report_title,
        "opening_line": report.opening_line,
        "closing_line": report.closing_line,
        "sections": report.sections,
        "report_date": report.report_date.isoformat(),
        "cached": True,
    }
