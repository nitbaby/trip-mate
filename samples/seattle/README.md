# Seattle sample trip

Fictional documents for a Seattle trip, 14 - 18 Jan 2027 (traveler "Jordan Lee", flying from Toronto). All names, numbers and policies are fake; the entry-rules text is a demo summary, not advice.

Trip to create: name "Seattle Jan 2027", destination Seattle, 2027-01-14 to 2027-01-18, timezone America/Los_Angeles. Or: `.venv/bin/python scripts/demo_seed.py --trip seattle --with-itinerary`.

| File | Type | Good for |
|---|---|---|
| `hotel_confirmation.txt` | confirmation | Check-in/out times, **no breakfast** (contrast with the Tokyo and Delhi hotels), parking and destination fee, cancellation deadline; masked passport and card |
| `flight_itinerary.txt` | itinerary | Toronto-Seattle flights AC 7731 / AC 7732, preclearance advice (3 hours), baggage, change fee; masked booking ref and passport |
| `us_entry_rules.txt` | rules | Medication and customs, cannabis warning, 10,000 USD declaration (verify badge) |
| `seattle_guide.md` | guide | Light rail, rain, vegetarian food, tipping, emergency numbers |
| `harbor_cruise_ticket.txt` | ticket | A booked activity: boarding time, refund deadline, weather cancellation |

## Questions and expected answers
| Question | Expected |
|---|---|
| What time is check-out? | 12:00 PM (noon) on 18 January 2027 |
| Is breakfast included? | No: the lobby cafe serves it, about 22 USD |
| How much is parking? | 55 USD per night, valet only |
| How long before my flight should I arrive at Toronto airport? | At least 3 hours (US preclearance) |
| When does the harbor cruise board and what is the last boarding time? | Boarding 10:00 AM, closes 10:20 AM sharp; sailing 10:30 AM on Saturday 16 January |
| Can I still get a refund on the cruise? | Only until 10:30 AM on 14 January 2027 (48 hours before) |
| Can I bring cannabis home from Washington? | No: illegal under federal law (verify badge) |
| What is the passport number? | Masked, never revealed in chat |
| Does the hotel have a pool? | Not in the documents (should say so) |

Mock live data notes (`LIVE_MODE=mock`): flights other than JL 44 report "on time"; weather uses a generic forecast; **places search only knows Tokyo anchors**, so "restaurants near my hotel" returns an error here until Seattle fixtures are added.
