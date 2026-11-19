## How to encode a time expression (`TimeExpr`)

Encode what was SAID; do not compute dates. Python resolves dates from the call timestamp.

| field | meaning |
|---|---|
| `day_ref` | one of the values below |
| `n` | the number for `in_days`, `in_minutes`, `in_hours`, `in_months` |
| `weekday` | lowercase weekday for `weekday`, `this_weekday`, `next_weekday` |
| `day`, `month`, `year` | for `date`; fill `month`/`year` only if actually stated |
| `hour`, `minute` | clock time as spoken ("4" -> 4, "4:30" -> 4 and 30, "16:00" -> 16) |
| `meridiem` | `am`/`pm` only if explicitly said |
| `daypart` | `morning`, `lunch`, `afternoon`, `evening`, `night` if said |

`day_ref` values:
- `unspecified`: only a clock time or daypart, no day ("call me at 4")
- `today`: "today", "this evening", "later today at 6"
- `tomorrow`; `day_after_tomorrow` ("day after tomorrow", "parso")
- `in_days`: "in two days" (n=2)
- `weekday`: a bare weekday ("on Friday", "Sunday then") — the default for any weekday
- `this_weekday`: only when the word "this" is spoken ("this Friday"); `next_weekday`: only when the word "next" is spoken ("next Friday")
- `next_week`: "next week" with nothing finer
- `this_week`: "this week" alone
- `date`: a day number ("on the 26th", "4th November")
- `in_minutes`, `in_hours`: "in 15 minutes", "in 2 hours"
- `in_months`: "after one month"; `next_month`: bare "next month"
- `after_event`: an unbounded event or period without an agreed day ("after Diwali", "after the family function", "next week after my son returns", "after the 22nd" when no specific day was agreed)

Examples: "tomorrow evening" -> `{day_ref: tomorrow, daypart: evening}`. "Friday at 11 AM" -> `{day_ref: weekday, weekday: friday, hour: 11, meridiem: am}`. "on the 4th or 5th" -> two options `{day_ref: date, day: 4}` and `{day_ref: date, day: 5}`.
