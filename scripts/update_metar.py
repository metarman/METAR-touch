#!/usr/bin/env python3
import csv, gzip, json, sys, math
from datetime import datetime, timezone
from pathlib import Path

src=Path(sys.argv[1] if len(sys.argv)>1 else "metars.cache.csv.gz")
dst=Path(sys.argv[2] if len(sys.argv)>2 else "metars_snapshot.json")

# AWC cache has metadata lines before the CSV header. Find the header line.
with gzip.open(src,"rt",encoding="utf-8-sig",errors="replace",newline="") as f:
    lines=f.readlines()

header_i=None
for i,line in enumerate(lines):
    if line.lower().startswith("raw_text,station_id,observation_time,"):
        header_i=i;break
if header_i is None:
    raise SystemExit("Could not find AWC METAR CSV header")

reader=csv.DictReader(lines[header_i:])
features=[]

def num(v):
    try:return float(v)
    except:return None

def first(row,*names):
    for n in names:
        if n in row and row[n] not in ("",None): return row[n]
    return None

def ceiling(row):
    layers=[]
    # Historical AWC cache columns are sky_cover / cloud_base_ft_agl with numbered repeats.
    for suffix in ("","_2","_3","_4"):
        cov=first(row,"sky_cover"+suffix)
        base=first(row,"cloud_base_ft_agl"+suffix)
        if cov and cov not in ("CLR","SKC","CAVOK"):
            if base:
                try: layers.append((cov,int(float(base))))
                except: pass
    ceils=[(c,b) for c,b in layers if c in ("BKN","OVC","OVX")]
    if ceils:
        c,b=min(ceils,key=lambda x:x[1]); return f"{c} {b:,} ft"
    if layers:
        c,b=min(layers,key=lambda x:x[1]); return f"{c} {b:,} ft"
    return "CLR / no ceiling reported"

for row in reader:
    lat=num(first(row,"latitude"));lon=num(first(row,"longitude"))
    if lat is None or lon is None or not (24.0<=lat<=50.0 and -125.5<=lon<=-66.0): continue
    cat=(first(row,"flight_category") or "UNKNOWN").upper()
    if cat not in ("VFR","MVFR","IFR","LIFR"): cat="UNKNOWN"
    ident=first(row,"station_id") or ""
    raw=first(row,"raw_text") or ""
    obs=first(row,"observation_time") or ""
    try: obs_epoch=int(datetime.fromisoformat(obs.replace("Z","+00:00")).timestamp())
    except: obs_epoch=0

    wdir=first(row,"wind_dir_degrees","wind_dir_de")
    wspd=first(row,"wind_speed_kt");wgst=first(row,"wind_gust_kt","wind_gust")
    if wdir in ("0","000") and wspd in ("0","0.0"): wind="Calm"
    elif wdir and wspd: wind=f"{wdir}° / {wspd} kt"+(f" G{wgst}" if wgst else "")
    elif wspd: wind=f"VRB / {wspd} kt"
    else: wind="—"

    vis=first(row,"visibility_statute_mi","visibility")
    vis=(f"{vis} SM" if vis else "—")
    alt=first(row,"altim_in_hg","altim_in")
    if alt:
        try: alt=f"{float(alt):.2f} inHg"
        except: pass
    else: alt="—"

    temp=first(row,"temp_c");dew=first(row,"dewpoint_c")
    tempdew=(f"{temp}°C / {dew}°C" if temp and dew else "—")
    name=first(row,"station_name","name") or ""

    props={"id":ident,"name":name,"cat":cat,"wind":wind,"vis":vis,"ceil":ceiling(row),"alt":alt,"temp":tempdew,"raw":raw,"obsEpoch":obs_epoch}
    features.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},"properties":props})

out={"type":"FeatureCollection","features":features,"metadata":{"generated_utc":datetime.now(timezone.utc).isoformat(),"source":"AWC metars.cache.csv.gz"}}
dst.write_text(json.dumps(out,separators=(",",":")),encoding="utf-8")
print(f"Wrote {len(features)} CONUS METARs to {dst}")
