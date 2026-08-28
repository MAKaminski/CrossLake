import os
from fastapi import FastAPI

app = FastAPI()
DATABASE_URL = os.environ["DATABASE_URL"]
STRIPE_SECRET = os.environ.get("STRIPE_API_KEY")
PLAID_SECRET = os.environ.get("PLAID_SECRET")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/applications")
def create_application(payload: dict):
    return {"id": 1}

@app.get("/api/applications/{app_id}")
def get_application(app_id: int):
    return {"id": app_id}

@app.get("/api/loans")
def list_loans():
    return []

@app.post("/api/payments")
def take_payment(payload: dict):
    return {"status": "captured"}
