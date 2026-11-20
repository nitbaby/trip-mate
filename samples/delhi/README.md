# Delhi sample trip

Fictional documents for a Delhi trip, 9 - 16 Feb 2027 (traveler "Casey Brooks", flying from London). All names, numbers and policies are fake; the entry-rules text is a demo summary, not advice.

Trip to create: name "Delhi Feb 2027", destination Delhi, 2027-02-09 to 2027-02-16, timezone Asia/Kolkata. Or: `.venv/bin/python scripts/demo_seed.py --trip delhi --with-itinerary`.

| File | Type | Good for |
|---|---|---|
| `hotel_confirmation.txt` | confirmation | Check-in at 2:00 PM vs a noon arrival (early check-in fee), late check-out until 6:00 PM, airport pickup, breakfast, water advice; masked passport and card |
| `flight_itinerary.txt` | itinerary | AI 2131 / AI 2132, an **overnight arrival the next day** and a **late-night departure** (11:50 PM on 15 Feb), baggage, 3-hour airport advice |
| `india_entry_rules.txt` | rules | e-Visa timing, medication, currency declaration limits (verify badge) |
| `delhi_guide.md` | guide | Metro and taxis, vegetarian food, sight closing days, emergency numbers |
| `agra_train_ticket.txt` | ticket | Day trip with a PNR, seats, times, refund rule |

## Intentional trap
The Agra train ticket is for **Friday 12 February 2027**, and the guide says the **Taj Mahal is closed on Fridays**. A good answer to "Is the Taj Mahal open on my Agra day?" combines both documents and warns the traveler.

## Questions and expected answers
| Question | Expected |
|---|---|
| What time is check-out, and can I stay until my flight? | Check-out 12:00 noon on 15 Feb; late check-out until 6:00 PM costs 2,500 INR; the flight is at 11:50 PM |
| Is breakfast included? | Yes, up to 2 guests, 7:00 - 10:30 AM |
| Can I check in when I land? | Landing is 12:05 PM; check-in is 2:00 PM; early check-in from 11:00 AM costs 2,000 INR |
| What time does my train to Agra leave? | 6:15 AM from New Delhi, platform 2; seat 31 in coach C2 |
| Is the Taj Mahal open on my Agra day? | No: 12 Feb is a Friday and it is closed on Fridays |
| How early should I get to the airport? | At least 3 hours before the 11:50 PM departure |
| What is the limit for foreign cash? | Declare above 5,000 USD in notes or 10,000 USD in total (verify badge) |
| What is the emergency number? | 112 |
| What is the passport number or PNR? | Passport masked, never revealed |
| Is there a gym at the hotel? | Not in the documents (should say so) |

Mock live data notes (`LIVE_MODE=mock`): flights other than JL 44 report "on time"; weather uses a generic forecast; **places search only knows Tokyo anchors**, so place searches around the Delhi hotel return an error until Delhi fixtures are added.
