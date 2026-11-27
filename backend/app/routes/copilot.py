from pydantic import BaseModel
from fastapi import APIRouter
from app.services.genai_engine import genai_engine

router = APIRouter(prefix="/api/copilot", tags=["Gemini AI Decision Copilot"])

class CopilotQueryRequest(BaseModel):
    query: str

@router.post("/query")
def query_copilot(req: CopilotQueryRequest):
    answer = genai_engine.query_copilot(req.query)
    return {
        "status": "success",
        "query": req.query,
        "response": answer
    }