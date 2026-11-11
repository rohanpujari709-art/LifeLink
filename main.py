
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

supabase = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global supabase

    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SECRET_KEY in backend/.env"
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    yield


app = FastAPI(
    title="LifeLink API",
    description="Smart Blood Donor Management System",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

BLOOD_GROUPS = {
    "A+", "A-", "B+", "B-",
    "AB+", "AB-", "O+", "O-",
}


class DonorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    blood_group: str
    city: str = Field(min_length=1, max_length=80)
    availability: str = "Availability Not Confirmed"


class EmergencyCreate(BaseModel):
    blood_group: str
    city: str = Field(min_length=1, max_length=100)
    hospital_name: str = Field(min_length=1, max_length=120)
    units: int = Field(ge=1, le=10)
    notes: str | None = Field(default=None, max_length=500)


def check_blood_group(group: str):
    if group.strip().upper() not in BLOOD_GROUPS:
        raise HTTPException(
            status_code=422,
            detail="Invalid blood group.",
        )
    return group.strip().upper()


@app.get("/")
def home():
    return {
        "message": "LifeLink API is running!",
        "database": "Supabase",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    try:
        supabase.table("donors").select("id").limit(1).execute()
        return {"status": "ok", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed. Check server configuration.",
        )


@app.get("/donors")
def find_donors(
    blood_group: str = Query(...),
    city: str | None = Query(default=None),
):
    group = check_blood_group(blood_group)

    try:
        query = (
            supabase.table("donors")
            .select(
                "id, donor_code, name, blood_group, city, "
                "availability, created_at"
            )
            .eq("blood_group", group)
        )

        if city and city.strip():
            query = query.ilike("city", f"%{city.strip()}%")

        response = query.order("id").execute()
        records = response.data or []

        # Keep the response compatible with the existing frontend.
        donors = [
            {
                "id": row["donor_code"],
                "name": row["name"],
                "blood_group": row["blood_group"],
                "city": row["city"],
                "availability": row["availability"],
            }
            for row in records
        ]

        return {"count": len(donors), "donors": donors}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Donor search failed. Check the database configuration.",
        )


@app.post("/donors", status_code=201)
def register_donor(donor: DonorCreate):
    group = check_blood_group(donor.blood_group)

    allowed_statuses = {
        "Available for Contact",
        "Availability Not Confirmed",
        "Not Available",
    }

    if donor.availability not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Invalid availability status.",
        )

    record = {
        "donor_code": "LL-" + uuid.uuid4().hex[:8].upper(),
        "name": donor.name.strip(),
        "blood_group": group,
        "city": donor.city.strip(),
        "availability": donor.availability,
    }

    try:
        response = (
            supabase.table("donors")
            .insert(record)
            .execute()
        )
        return {
            "message": "Donor saved successfully.",
            "donor": response.data[0],
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Donor registration failed.",
        )


@app.post("/emergency-requests", status_code=201)
def create_emergency_request(request: EmergencyCreate):
    group = check_blood_group(request.blood_group)

    record = {
        "request_code": "LL-ER-" + uuid.uuid4().hex[:8].upper(),
        "blood_group": group,
        "city": request.city.strip(),
        "hospital_name": request.hospital_name.strip(),
        "units": request.units,
        "notes": request.notes.strip() if request.notes else None,
        "status": "Pending",
    }

    try:
        response = (
            supabase.table("emergency_requests")
            .insert(record)
            .execute()
        )
        return {
            "message": "Emergency request saved successfully.",
            "request": response.data[0],
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Emergency request could not be saved.",
        )
