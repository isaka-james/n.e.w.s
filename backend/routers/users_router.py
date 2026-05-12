from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from database import get_session
from models import User
from auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    city: str | None = None
    country: str | None = None
    tags: list[dict] | None = None
    blocked_words: list[str] | None = None


CONTINENT_BY_COUNTRY = {
    "Afghanistan": "Asia", "Albania": "Europe", "Algeria": "Africa",
    "Argentina": "South America", "Armenia": "Asia", "Australia": "Oceania",
    "Austria": "Europe", "Azerbaijan": "Asia", "Bahrain": "Asia",
    "Bangladesh": "Asia", "Belarus": "Europe", "Belgium": "Europe",
    "Bolivia": "South America", "Bosnia and Herzegovina": "Europe",
    "Botswana": "Africa", "Brazil": "South America", "Bulgaria": "Europe",
    "Cambodia": "Asia", "Cameroon": "Africa", "Canada": "North America",
    "Chile": "South America", "China": "Asia", "Colombia": "South America",
    "Croatia": "Europe", "Cuba": "North America", "Czech Republic": "Europe",
    "Denmark": "Europe", "Dominican Republic": "North America", "Ecuador": "South America",
    "Egypt": "Africa", "Estonia": "Europe", "Ethiopia": "Africa", "Finland": "Europe",
    "France": "Europe", "Georgia": "Asia", "Germany": "Europe", "Ghana": "Africa",
    "Greece": "Europe", "Hungary": "Europe", "Iceland": "Europe", "India": "Asia",
    "Indonesia": "Asia", "Iran": "Asia", "Iraq": "Asia", "Ireland": "Europe",
    "Israel": "Asia", "Italy": "Europe", "Japan": "Asia", "Jordan": "Asia",
    "Kazakhstan": "Asia", "Kenya": "Africa", "Kuwait": "Asia", "Latvia": "Europe",
    "Lebanon": "Asia", "Libya": "Africa", "Lithuania": "Europe", "Luxembourg": "Europe",
    "Malaysia": "Asia", "Malta": "Europe", "Mexico": "North America", "Moldova": "Europe",
    "Mongolia": "Asia", "Montenegro": "Europe", "Morocco": "Africa", "Myanmar": "Asia",
    "Nepal": "Asia", "Netherlands": "Europe", "New Zealand": "Oceania",
    "Nigeria": "Africa", "North Korea": "Asia", "North Macedonia": "Europe",
    "Norway": "Europe", "Oman": "Asia", "Pakistan": "Asia", "Panama": "North America",
    "Paraguay": "South America", "Peru": "South America", "Philippines": "Asia",
    "Poland": "Europe", "Portugal": "Europe", "Qatar": "Asia", "Romania": "Europe",
    "Russia": "Europe", "Saudi Arabia": "Asia", "Senegal": "Africa", "Serbia": "Europe",
    "Singapore": "Asia", "Slovakia": "Europe", "Slovenia": "Europe", "Somalia": "Africa",
    "South Africa": "Africa", "South Korea": "Asia", "Spain": "Europe",
    "Sri Lanka": "Asia", "Sudan": "Africa", "Sweden": "Europe", "Switzerland": "Europe",
    "Syria": "Asia", "Taiwan": "Asia", "Tanzania": "Africa", "Thailand": "Asia",
    "Tunisia": "Africa", "Turkey": "Asia", "Uganda": "Africa", "Ukraine": "Europe",
    "United Arab Emirates": "Asia", "United Kingdom": "Europe",
    "United States": "North America", "Uruguay": "South America",
    "Venezuela": "South America", "Vietnam": "Asia", "Yemen": "Asia",
    "Zambia": "Africa", "Zimbabwe": "Africa",
}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "city": current_user.city,
        "country": current_user.country,
        "continent": current_user.continent,
        "tags": current_user.tags,
        "blocked_words": current_user.blocked_words,
    }


@router.patch("/me")
def update_me(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.city is not None:
        current_user.city = payload.city
    if payload.country is not None:
        if payload.country not in CONTINENT_BY_COUNTRY:
            raise HTTPException(status_code=400, detail=f"Unknown country: {payload.country}")
        current_user.country = payload.country
        current_user.continent = CONTINENT_BY_COUNTRY[payload.country]
    if payload.tags is not None:
        current_user.tags = payload.tags
    if payload.blocked_words is not None:
        current_user.blocked_words = payload.blocked_words

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "city": current_user.city,
        "country": current_user.country,
        "continent": current_user.continent,
        "tags": current_user.tags,
        "blocked_words": current_user.blocked_words,
    }
