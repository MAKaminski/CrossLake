import os
DATABASE_URL = os.environ["DATABASE_URL"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

def score_application(application_id: int) -> float:
    return 0.72
