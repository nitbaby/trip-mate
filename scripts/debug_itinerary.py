"""Read-only check of what the agents would see for a trip. Prints no secrets.

  .venv/bin/python scripts/debug_itinerary.py <trip_id> ["question"]
Uses the same settings/.env as the backend and only READS the database."""
import sys
from urllib.parse import urlparse

sys.path.insert(0, "backend")
from app.agent.prompt import itinerary_block, role_prompt  # noqa: E402
from app.agent.router import route  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.services.itinerary import list_items  # noqa: E402

trip_id = sys.argv[1]
question = sys.argv[2] if len(sys.argv) > 2 else "What is the itinerary for this trip?"
s = get_settings()
host = urlparse(s.llm_base_url).netloc if s.llm_provider == "openai" else "-"
print(f"provider={s.llm_provider} model={s.llm_model or s.gemini_model} host={host} agent_mode={s.agent_mode} data_dir={s.tripmate_data_dir}")
with connect() as c:
    trip = c.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        sys.exit(f"trip {trip_id} not found in this data dir")
    trip = dict(trip)
    trip["destinations"] = trip["destinations"].split(",") if isinstance(trip["destinations"], str) else trip["destinations"]
    items = list_items(c, trip_id)
print(f"trip: {trip['name']} {trip['start_date']}..{trip['end_date']} tz={trip['timezone']}; {len(items)} itinerary item(s)")
print(f"route({question!r}) = {route(question)}")
print(itinerary_block(items))
print("--- itinerary agent prompt (first 1500 chars) ---")
print(role_prompt("itinerary", trip, itinerary=items)[:1500])
