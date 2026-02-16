"""Calendar tool — stub with fake data.

Proves multi-tool routing works. Returns hardcoded events
so the model can demonstrate calendar-aware responses.
"""

from datetime import datetime
from typing import Any

from .base import BaseTool


class CalendarTool(BaseTool):
    @property
    def name(self) -> str:
        return "check_calendar"

    @property
    def description(self) -> str:
        return "Check your calendar for upcoming events and appointments."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format. Defaults to today.",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        date = kwargs.get("date", datetime.now().strftime("%Y-%m-%d"))
        return (
            f"Calendar for {date}:\n"
            f"- 9:00 AM: Team standup (Zoom)\n"
            f"- 11:30 AM: Lunch with Alex at Torchy's Tacos\n"
            f"- 2:00 PM: Dentist appointment\n"
            f"- 5:00 PM: Yoga class"
        )
