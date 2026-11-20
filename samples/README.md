# Sample documents

Fictional documents for three demo trips, one folder each. Every folder has its documents and a `trip.json` (trip details, document list, sample itinerary item) that `scripts/demo_seed.py` reads. All names and numbers are fake.

| Folder | Trip | Notable test data |
|---|---|---|
| `tokyo/` | Tokyo, 30 Nov - 6 Dec 2026, timezone Asia/Tokyo, traveler "Alex Morgan". **The default trip: the eval set (`eval/`), the E2E tests and the demo plan use it.** | Late check-out fee, breakfast, flight JL 44 (delayed in mock mode), medication rules (verify badge), vegetarian tips; a PDF copy of the hotel confirmation to test PDF parsing |
| `seattle/` | Seattle, 14-18 Jan 2027, timezone America/Los_Angeles | No breakfast included, preclearance advice, cannabis warning, a prepaid harbor cruise with a refund deadline |
| `delhi/` | Delhi, 9-16 Feb 2027, timezone Asia/Kolkata | Noon arrival vs 2:00 PM check-in, 11:50 PM departure vs noon check-out, e-Visa rules, an Agra train on a Friday when the Taj Mahal is closed (intentional trap) |

## Tokyo files (`samples/tokyo/`)
| File | Type | Good for |
|---|---|---|
| `hotel_confirmation.txt` / `.pdf` | confirmation | Check-out time, breakfast, cancellation; masked booking ref, passport, card. The PDF is the same content, to test PDF parsing. |
| `flight_itinerary.txt` | itinerary | Flight JL 44 departs 6:00 PM (demo flow 2); masked booking ref and passport |
| `japan_entry_rules.txt` | rules | Medication rules (demo flow 3, verify badge) |
| `tokyo_guide.md` | guide | Vegetarian food tips, transport (demo flow 4) |

Seattle and Delhi have their own README with questions and expected answers.

## Using them
- Create a trip with its documents on a demo backend: `.venv/bin/python scripts/demo_seed.py --trip tokyo|seattle|delhi --with-itinerary` (default `tokyo`). Or create it by hand in the UI: name, destination, dates and timezone are in each `trip.json`.
- Mock live data only knows Tokyo places, so place searches near the Seattle or Delhi hotels return an error until fixtures are added. Flights other than JL 44 report "on time" and weather is generic.
- `backend/tests/test_samples.py` checks every trip folder (manifest, dates, weekday statements, masking of sensitive values).
