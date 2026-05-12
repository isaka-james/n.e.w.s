from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr
from database import get_session
from models import User
from auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

CONTINENT_BY_COUNTRY = {
    "Afghanistan": "Asia", "Albania": "Europe", "Algeria": "Africa",
    "Andorra": "Europe", "Angola": "Africa", "Argentina": "South America",
    "Armenia": "Asia", "Australia": "Oceania", "Austria": "Europe",
    "Azerbaijan": "Asia", "Bahamas": "North America", "Bahrain": "Asia",
    "Bangladesh": "Asia", "Belarus": "Europe", "Belgium": "Europe",
    "Belize": "North America", "Benin": "Africa", "Bhutan": "Asia",
    "Bolivia": "South America", "Bosnia and Herzegovina": "Europe",
    "Botswana": "Africa", "Brazil": "South America", "Brunei": "Asia",
    "Bulgaria": "Europe", "Burkina Faso": "Africa", "Burundi": "Africa",
    "Cambodia": "Asia", "Cameroon": "Africa", "Canada": "North America",
    "Cape Verde": "Africa", "Central African Republic": "Africa", "Chad": "Africa",
    "Chile": "South America", "China": "Asia", "Colombia": "South America",
    "Comoros": "Africa", "Congo": "Africa", "Costa Rica": "North America",
    "Croatia": "Europe", "Cuba": "North America", "Cyprus": "Europe",
    "Czech Republic": "Europe", "Denmark": "Europe", "Djibouti": "Africa",
    "Dominican Republic": "North America", "Ecuador": "South America",
    "Egypt": "Africa", "El Salvador": "North America", "Equatorial Guinea": "Africa",
    "Eritrea": "Africa", "Estonia": "Europe", "Ethiopia": "Africa",
    "Fiji": "Oceania", "Finland": "Europe", "France": "Europe",
    "Gabon": "Africa", "Gambia": "Africa", "Georgia": "Asia",
    "Germany": "Europe", "Ghana": "Africa", "Greece": "Europe",
    "Guatemala": "North America", "Guinea": "Africa", "Guinea-Bissau": "Africa",
    "Guyana": "South America", "Haiti": "North America", "Honduras": "North America",
    "Hungary": "Europe", "Iceland": "Europe", "India": "Asia",
    "Indonesia": "Asia", "Iran": "Asia", "Iraq": "Asia",
    "Ireland": "Europe", "Israel": "Asia", "Italy": "Europe",
    "Jamaica": "North America", "Japan": "Asia", "Jordan": "Asia",
    "Kazakhstan": "Asia", "Kenya": "Africa", "Kuwait": "Asia",
    "Kyrgyzstan": "Asia", "Laos": "Asia", "Latvia": "Europe",
    "Lebanon": "Asia", "Lesotho": "Africa", "Liberia": "Africa",
    "Libya": "Africa", "Liechtenstein": "Europe", "Lithuania": "Europe",
    "Luxembourg": "Europe", "Madagascar": "Africa", "Malawi": "Africa",
    "Malaysia": "Asia", "Maldives": "Asia", "Mali": "Africa",
    "Malta": "Europe", "Mauritania": "Africa", "Mauritius": "Africa",
    "Mexico": "North America", "Moldova": "Europe", "Monaco": "Europe",
    "Mongolia": "Asia", "Montenegro": "Europe", "Morocco": "Africa",
    "Mozambique": "Africa", "Myanmar": "Asia", "Namibia": "Africa",
    "Nepal": "Asia", "Netherlands": "Europe", "New Zealand": "Oceania",
    "Nicaragua": "North America", "Niger": "Africa", "Nigeria": "Africa",
    "North Korea": "Asia", "North Macedonia": "Europe", "Norway": "Europe",
    "Oman": "Asia", "Pakistan": "Asia", "Panama": "North America",
    "Papua New Guinea": "Oceania", "Paraguay": "South America", "Peru": "South America",
    "Philippines": "Asia", "Poland": "Europe", "Portugal": "Europe",
    "Qatar": "Asia", "Romania": "Europe", "Russia": "Europe",
    "Rwanda": "Africa", "Saudi Arabia": "Asia", "Senegal": "Africa",
    "Serbia": "Europe", "Sierra Leone": "Africa", "Singapore": "Asia",
    "Slovakia": "Europe", "Slovenia": "Europe", "Somalia": "Africa",
    "South Africa": "Africa", "South Korea": "Asia", "South Sudan": "Africa",
    "Spain": "Europe", "Sri Lanka": "Asia", "Sudan": "Africa",
    "Suriname": "South America", "Sweden": "Europe", "Switzerland": "Europe",
    "Syria": "Asia", "Taiwan": "Asia", "Tajikistan": "Asia",
    "Tanzania": "Africa", "Thailand": "Asia", "Togo": "Africa",
    "Trinidad and Tobago": "North America", "Tunisia": "Africa", "Turkey": "Asia",
    "Turkmenistan": "Asia", "Uganda": "Africa", "Ukraine": "Europe",
    "United Arab Emirates": "Asia", "United Kingdom": "Europe",
    "United States": "North America", "Uruguay": "South America",
    "Uzbekistan": "Asia", "Venezuela": "South America", "Vietnam": "Asia",
    "Yemen": "Asia", "Zambia": "Africa", "Zimbabwe": "Africa",
}


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    city: str
    country: str
    tags: list[dict] = []
    blocked_words: list[str] = []


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    city: str
    country: str
    continent: str
    tags: list[dict]
    blocked_words: list[str]


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    continent = CONTINENT_BY_COUNTRY.get(payload.country, "Unknown")
    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        city=payload.city,
        country=payload.country,
        continent=continent,
        tags=payload.tags,
        blocked_words=payload.blocked_words,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            city=user.city,
            country=user.country,
            continent=user.continent,
            tags=user.tags,
            blocked_words=user.blocked_words,
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            city=user.city,
            country=user.country,
            continent=user.continent,
            tags=user.tags,
            blocked_words=user.blocked_words,
        ),
    )
