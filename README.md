# Downtown Eats

A one-page restaurant dashboard for Gramercy / East Village / LES / West Village –
82 spots on a map, filterable by category, rating, price, and booking platform,
with live "free tables tonight" data pulled from Resy and SevenRooms.

## Use it

Open `index.html` in a browser (or serve the folder). Everything is static –
no build step, no keys.

- **Category chips** – the 8 groups from the master list (pizza, bagels, sushi, …).
- **Filters** – minimum rating, price tier, booking platform, plus a
  **Free tables today** toggle that shows only spots with a bookable slot left today.
- **Cards** – tap a card to fly the map to it; tap a time chip to jump straight to
  the booking page.

## Refresh availability

```
python3 scripts/refresh_availability.py            # party of 2, today
python3 scripts/refresh_availability.py --party 4  # party of 4
```

Writes `data/availability.js` with a checked-at stamp shown in the header.
Notes:

- **Resy** – checked via their public widget API. Rate-limited: fine once or twice
  a day, but back-to-back runs get 403s for a while (the script backs off, spaces
  requests ~1s apart, caches venue IDs in `data/.resy_ids.json`, and keeps the
  previous run's numbers for any venue that errors).
- **SevenRooms** (Semma, Rezdôra, Dhamaka, Raku) – checked via their widget API.
- **OpenTable** – blocks scripted checks entirely; those venues show
  "Availability not checked" plus their booking link.
- Walk-in spots are labeled walk-in and never checked.

## Data

`data/restaurants.js` is the master list (name, address, coordinates, Google
rating snapshot from July 2026, price, platform, booking URL, note, categories).
Edit it directly to add or remove spots; `id` just needs to be unique.

Dropped as permanently closed during the July 2026 research pass: Red Bamboo,
Baar Baar, Stretch Pizza (Park Ave S). Casa Carmen was mapped to its Flatiron
location; Maki Kosaka to its current 55 W 19th St home.
