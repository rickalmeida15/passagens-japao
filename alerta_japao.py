#!/usr/bin/env python3
"""
Alerta de passagens SÓ IDA: São Paulo -> Japão (NGO, KIX, HND, NRT).
Descarta itinerários com conexão na América do Norte (EUA, Canadá, México).
Manda notificação no celular (ntfy.sh) quando o preço por pessoa fica abaixo do seu limite.

Exemplo:
  export SERPAPI_KEY="..."   # serpapi.com (grátis, ~100 buscas/mês)
  export NTFY_TOPIC="japao-fulano-123"   # escolha um nome difícil de adivinhar; instale o app ntfy e assine
  python3 alerta_japao.py --dates 2027-03-10,2027-03-17,2027-03-24 \
      --classes 1,3 --max-price 1:5000,3:14000

Classes: 1=econômica 2=premium economy 3=executiva 4=primeira
Preços são POR PESSOA, em BRL (multiplique por 2 para você e sua esposa).
"""
import argparse, os, sys, json, urllib.parse, urllib.request
from datetime import date, timedelta

NA_AIRPORTS = set("""
ATL ORD DFW DEN JFK EWR LGA LAX SFO SEA LAS MCO MIA CLT PHX IAH BOS MSP DTW FLL PHL BWI
SLC SAN DCA IAD TPA PDX HNL OGG ANC STL MCI AUS BNA RDU IND CLE CMH PIT SJC SMF OAK SAT
MSY MDW HOU DAL CVG MKE SNA JAX RSW ONT BUF SJU GUM
YYZ YVR YUL YYC YOW YEG YWG YHZ YQB
MEX CUN GDL MTY TIJ SJD PVR
""".split())
CLASS_NAMES = {1: "Economica", 2: "Premium", 3: "Executiva", 4: "Primeira"}


def search(key, origin, dests, day, travel_class):
    params = {
        "engine": "google_flights", "departure_id": origin, "arrival_id": dests,
        "outbound_date": day, "type": "2", "travel_class": str(travel_class),
        "adults": "1", "currency": "BRL", "hl": "pt-br", "gl": "br", "api_key": key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    except Exception as e:
        print(f"erro {day} classe {travel_class}: {e}", file=sys.stderr)
        return None


def best_valid(data, blocked):
    if not data:
        return None
    best = None
    for offer in data.get("best_flights", []) + data.get("other_flights", []):
        price = offer.get("price")
        segs = offer.get("flights", [])
        if price is None or not segs:
            continue
        stops = [l.get("id") for l in offer.get("layovers", [])]
        stops += [s.get("arrival_airport", {}).get("id") for s in segs[:-1]]
        if any(s in blocked for s in stops):
            continue
        if best is None or price < best["price"]:
            best = {
                "price": price,
                "arrival": segs[-1].get("arrival_airport", {}).get("id", "?"),
                "stops": sorted({s for s in stops if s}),
                "airlines": sorted({s.get("airline", "?") for s in segs}),
                "hours": round(offer.get("total_duration", 0) / 60, 1),
            }
    return best


def notify(topic, title, body, click):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
        headers={"Title": title, "Click": click, "Priority": "high", "Tags": "airplane"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"falha ao notificar: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", default="GRU")
    ap.add_argument("--dest", default="NGO,KIX,HND,NRT")
    ap.add_argument("--dates", help="datas separadas por vírgula (AAAA-MM-DD)")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--step", type=int, default=7)
    ap.add_argument("--classes", default="1,3")
    ap.add_argument("--max-price", default="1:5000,3:14000",
                    help="limite por pessoa e por classe, ex: 1:5000,3:14000")
    ap.add_argument("--block", default="")
    ap.add_argument("--out", default="data/history.json")
    a = ap.parse_args()

    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("Defina SERPAPI_KEY.")
    topic = os.environ.get("NTFY_TOPIC")

    if a.dates:
        days = a.dates.split(",")
    elif a.start and a.end:
        d, days = date.fromisoformat(a.start), []
        while d <= date.fromisoformat(a.end):
            days.append(d.isoformat()); d += timedelta(days=a.step)
    else:
        sys.exit("Informe --dates ou --start/--end.")

    limits = {int(k): float(v) for k, v in (p.split(":") for p in a.max_price.split(","))}
    blocked = NA_AIRPORTS | {x.strip().upper() for x in a.block.split(",") if x.strip()}

    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")
    new_records = []
    for c in [int(x) for x in a.classes.split(",")]:
        for day in days:
            b = best_valid(search(key, a.origin, a.dest, day, c), blocked)
            if not b:
                print(f"{day} {CLASS_NAMES[c]}: nada valido")
                continue
            new_records.append({"ts": now, "date": day, "cls": c, "origin": a.origin, **b})
            line = (f"{day} {CLASS_NAMES[c]}: R$ {b['price']:,.0f}/pessoa (R$ {2*b['price']:,.0f} casal) "
                    f"-> {b['arrival']} via {'/'.join(b['stops']) or 'direto'} | {'/'.join(b['airlines'])} | {b['hours']}h")
            print(line)
            if c in limits and b["price"] <= limits[c] and topic:
                link = (f"https://www.google.com/travel/flights?q=Flights%20from%20{a.origin}"
                        f"%20to%20{b['arrival']}%20on%20{day}%20one%20way")
                notify(topic, f"Passagem Japao {CLASS_NAMES[c]} R$ {b['price']:,.0f}", line, link)

    # histórico para o app (data/history.json)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        with open(a.out, encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        hist = {"records": []}
    hist["records"].extend(new_records)
    hist["updated"] = now
    hist["limits"] = limits
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
