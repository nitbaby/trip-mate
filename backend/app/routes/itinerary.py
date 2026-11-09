from fastapi import APIRouter

from ..db import connect
from ..schemas import ItemIn, ItemPatch
from ..services import itinerary as svc

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["itinerary"])


@router.get("/itinerary")
def list_items(trip_id: str, date_from: str | None = None, date_to: str | None = None):
    with connect() as c:
        return svc.list_items(c, trip_id, date_from, date_to)


@router.post("/itinerary", status_code=201)
def create_item(trip_id: str, body: ItemIn):
    with connect() as c:
        return svc.create_item(c, trip_id, body)


@router.patch("/itinerary/{item_id}")
def update_item(trip_id: str, item_id: str, body: ItemPatch):
    with connect() as c:
        return svc.update_item(c, trip_id, item_id, body)


@router.delete("/itinerary/{item_id}", status_code=204)
def delete_item(trip_id: str, item_id: str):
    with connect() as c:
        svc.delete_item(c, trip_id, item_id)


@router.post("/undo/{undo_id}")
def undo(trip_id: str, undo_id: str):
    """Undo an agent itinerary write (UI shows an Undo toast for ~10 s)."""
    with connect() as c:
        return svc.undo(c, trip_id, undo_id)
