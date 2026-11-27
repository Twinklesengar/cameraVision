import os
from typing import Dict, Any, List
from google import genai
from app.config import config
from app.db.sqlite_db import SessionLocal
from app.db.models import Personnel, AttendanceLog, IncidentAlert, ProductivityLog, HealthLog, AssetLog

class GeminiDecisionEngine:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiEngine Warning] Failed to initialize Gemini API client: {e}")

    def query_copilot(self, prompt: str) -> str:
        """
        Answers natural language queries using system DB context & Gemini model.
        e.g., 'Who entered the building today?', 'Summarize all security alerts', 'Is there any theft suspect?'
        """
        db = SessionLocal()
        try:
            # Fetch contextual stats from database
            personnel_count = db.query(Personnel).count()
            recent_attendance = db.query(AttendanceLog).order_by(AttendanceLog.timestamp.desc()).limit(10).all()
            unresolved_alerts = db.query(IncidentAlert).filter(IncidentAlert.is_resolved == False).all()
            assets = db.query(AssetLog).all()

            att_summary = [f"- {a.name} ({a.person_id}) at {a.timestamp.strftime('%H:%M:%S')} via {a.camera_id}" for a in recent_attendance]
            alert_summary = [f"- [{a.severity}] {a.alert_type}: {a.description} at {a.timestamp.strftime('%H:%M:%S')}" for a in unresolved_alerts]
            asset_summary = [f"- {ast.asset_name} (Owner: {ast.owner_person_id}, Status: {ast.status})" for ast in assets]

            context = f"""
            SYSTEM SURVEILLANCE CONTEXT:
            Total Enrolled Personnel: {personnel_count}
            Recent Attendance Events:
            {chr(10).join(att_summary) if att_summary else 'No recent attendance logs.'}

            Unresolved Security Alerts:
            {chr(10).join(alert_summary) if alert_summary else 'No active unresolved alerts.'}

            Monitored Assets:
            {chr(10).join(asset_summary) if asset_summary else 'No assets registered.'}
            """

            if self.client:
                full_prompt = f"""
                You are AegisVision AI Security Copilot, an enterprise autonomous decision engine for modern surveillance.
                Use the following real-time database context to answer the user's question accurately, concisely, and professionally.

                {context}

                USER QUESTION: {prompt}
                """
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt
                )
                return response.text.strip()
            else:
                # Rule-based fallback response if API key is not configured
                prompt_lower = prompt.lower()
                if "alert" in prompt_lower or "theft" in prompt_lower or "unresolved" in prompt_lower:
                    if alert_summary:
                        return "Active Unresolved Alerts:\n" + "\n".join(alert_summary)
                    return "No active unresolved alerts at this time. All systems operating normally."
                elif "who" in prompt_lower or "attendance" in prompt_lower or "entered" in prompt_lower:
                    if att_summary:
                        return "Recent Attendance Logs:\n" + "\n".join(att_summary)
                    return f"Total registered personnel: {personnel_count}. No recent entrance logs recorded."
                elif "asset" in prompt_lower or "laptop" in prompt_lower:
                    if asset_summary:
                        return "Monitored Assets Status:\n" + "\n".join(asset_summary)
                    return "No registered assets."
                else:
                    return f"AegisVision AI Copilot Active. Total Registered Personnel: {personnel_count}. Active Alerts: {len(unresolved_alerts)}."

        except Exception as e:
            return f"Error processing query: {str(e)}"
        finally:
            db.close()

genai_engine = GeminiDecisionEngine()
