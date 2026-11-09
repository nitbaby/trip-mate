"""TripMate MCP tool server (stdio). Runs on the same host as the backend and shares its data dir.

Run:  python -m tripmate_mcp.server
"""
import json
import logging
import sys

from app.errors import ApiError
from app.tools import impl
from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is reserved for the MCP protocol
mcp = FastMCP("tripmate")


def _run(fn, *a, **kw) -> str:
    """Tools return JSON text. Failures become {"error": ...} so the agent can explain them, not crash."""
    try:
        return json.dumps(fn(*a, **kw))
    except ApiError as e:
        return json.dumps({"error": {"code": e.code, "message": e.message}})
    except (ValueError, NotImplementedError) as e:
        return json.dumps({"error": {"code": "VALIDATION_FAILED", "message": str(e)}})
    except Exception as e:
        logging.exception("tool failed")
        return json.dumps({"error": {"code": "EXTERNAL_UNAVAILABLE", "message": f"{type(e).__name__}"}})


@mcp.tool()
def search_docs(trip_id: str, query: str, doc_type: str | None = None) -> str:
    """Search the traveler's uploaded documents (bookings, itineraries, rules, guides). Returns ranked passages
    with document name, page and similarity score. doc_type may be confirmation, itinerary, rules or guide."""
    return _run(impl.search_docs, trip_id, query, doc_type)


@mcp.tool()
def read_itinerary(trip_id: str, date_from: str | None = None, date_to: str | None = None) -> str:
    """Read itinerary items for a trip, optionally between ISO datetimes. Includes conflicts_with for overlaps."""
    return _run(impl.read_itinerary, trip_id, date_from, date_to)


@mcp.tool()
def write_itinerary(trip_id: str, action: str, item_id: str | None = None, type: str | None = None,
                    title: str | None = None, start_at: str | None = None, end_at: str | None = None,
                    location: str | None = None, notes: str | None = None) -> str:
    """Create, update or delete an itinerary item. action: create|update|delete. type: flight, hotel,
    reservation, activity, transit or note. Times are ISO 8601 local to the trip. Returns an undo_id."""
    return _run(impl.write_itinerary, trip_id, action, item_id, type, title, start_at, end_at, location, notes)


@mcp.tool()
def get_flight_status(flight_number: str, date: str) -> str:
    """Live status for a flight (e.g. 'JL 44') on a date (YYYY-MM-DD): delay, gate, last updated."""
    return _run(impl.get_flight_status, flight_number, date)


@mcp.tool()
def get_weather(location: str, days: int = 3) -> str:
    """Weather forecast for a location for up to 7 days, in Celsius."""
    return _run(impl.get_weather, location, days)


@mcp.tool()
def search_places(location: str, query: str = "", vegetarian: bool = False, open_now: bool = False,
                  trip_id: str | None = None) -> str:
    """Find places near a location (e.g. the hotel name). Returns rating, open_now, distance in metres.
    Set vegetarian=true for vegetarian-friendly places and open_now=true to only return places open now."""
    return _run(impl.search_places, location, query, vegetarian, open_now, None, None, 2000, trip_id)


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies (3-letter codes) using the latest rate, with a timestamp."""
    return _run(impl.convert_currency, amount, from_currency, to_currency)


if __name__ == "__main__":
    mcp.run()
