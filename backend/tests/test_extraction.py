from app.ingest.facts import extract_key_facts
from app.ingest.mask import find_sensitive

FLIGHT = "Passenger: Alex\nBooking reference: QX93LM\nPassport: P48213907\nFlight: JL 44"
HOTEL = "SHINJUKU HOTEL - BOOKING CONFIRMATION\nHotel: Shinjuku Granbell Hotel\nConfirmation number: GB7K2941\nCard number 4539 1488 0343 6467"


def test_booking_reference_after_word_reference():
    vals = {f["label"]: f["value"] for f in find_sensitive(FLIGHT)}
    assert vals["booking_reference"] == "QX93LM" and vals["passport_number"] == "P48213907"


def test_plain_words_not_treated_as_references():
    assert [f for f in find_sensitive("Booking policy: see reference material here")] == []


def test_hotel_name_and_card():
    facts = {f["label"]: f for f in extract_key_facts(HOTEL)}
    assert facts["Hotel"]["value"] == "Shinjuku Granbell Hotel"
    assert facts["Booking reference"]["value"] == "GB7K2941"
    assert facts["Card number"]["masked"].endswith("67")
