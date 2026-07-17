"""
Live Swarm Map — Echtzeit-Visualisierung aller Drohnen während eines Experiments.

Liest kontinuierlich die CSV-Logs und zeichnet:
  - 2D Karte mit aktuellen Positionen + Pfadspur
  - Höhe aller Drohnen über Zeit
  - Minimaler Abstand zwischen Drohnen (Kollisionsgraph)

Usage (parallel zum Experiment starten):
    python tools/live_swarm_map.py              # letzter Timestamp
    python tools/live_swarm_map.py 20260507_19  # bestimmter Präfix

Fenster bleibt offen und aktualisiert sich alle 2s.
"""
import argparse
import csv
import glob
import math
import os
import sys
import time
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("prefix", nargs="?", default=None,
                    help="Timestamp-Präfix der Log-Dateien z.B. 20260507_19")
parser.add_argument("--interval", type=float, default=2.0,
                    help="Update-Intervall in Sekunden (default: 2.0)")
parser.add_argument("--tail", type=int, default=300,
                    help="Anzahl der letzten Datenpunkte für Pfadspur (default: 300)")
args = parser.parse_args()

try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import matplotlib.animation as animation
    from matplotlib.cm import get_cmap
except ImportError:
    sys.exit("matplotlib nicht installiert. Run: pip install matplotlib")

COLORS = plt.cm.tab10
TAIL   = args.tail

# ── Log-Dateien bestimmen ─────────────────────────────────────────────────────

def find_log_files(prefix=None):
    all_csvs = sorted(glob.glob("logs/*_telemetry.csv"))
    if not all_csvs:
        return []
    if prefix:
        return sorted(glob.glob(f"logs/{prefix}*_telemetry.csv"))
    last_ts = "_".join(os.path.basename(all_csvs[-1]).split("_")[:2])
    return sorted(glob.glob(f"logs/{last_ts}_*.csv"))

paths = find_log_files(args.prefix)
if not paths:
    sys.exit("Keine Log-Dateien gefunden. Starte zuerst das Experiment.")

drone_ids = []
for p in paths:
    # Extrakt drone_id aus Dateiname: 20260507_213955_D1_telemetry.csv
    parts = os.path.basename(p).replace("_telemetry.csv", "").split("_")
    did = "_".join(parts[2:]) if len(parts) > 2 else parts[-1]
    drone_ids.append(did)

print(f"Live-Map für: {drone_ids}")
print(f"Dateien: {[os.path.basename(p) for p in paths]}")
print("Schließe das Fenster zum Beenden.")

# ── CSV-Leser: liest nur neue Zeilen ──────────────────────────────────────────

file_positions = {p: 0 for p in paths}
drone_data: dict = {did: [] for did in drone_ids}

def read_new_rows():
    for path, did in zip(paths, drone_ids):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                f.seek(file_positions[path])
                reader = csv.DictReader(f) if file_positions[path] == 0 else None
                if file_positions[path] == 0:
                    # Erster Lesevorgang: Header überspringen
                    content = f.read()
                    file_positions[path] = f.tell()
                    lines = content.splitlines()
                    if not lines:
                        continue
                    header = lines[0].split(",")
                    for line in lines[1:]:
                        if not line.strip():
                            continue
                        vals = line.split(",")
                        row = dict(zip(header, vals))
                        _parse_row(did, row)
                else:
                    content = f.read()
                    file_positions[path] = f.tell() if content else file_positions[path]
                    lines = content.splitlines()
                    for line in lines:
                        if not line.strip():
                            continue
                        # Header wiederverwenden
                        with open(path, newline="", encoding="utf-8") as f2:
                            header = next(csv.reader(f2))
                        vals = line.split(",")
                        if len(vals) >= len(header):
                            row = dict(zip(header, vals))
                            _parse_row(did, row)
        except Exception:
            pass

def _parse_row(did, row):
    try:
        lat = float(row.get("lat", 0) or 0)
        lon = float(row.get("lon", 0) or 0)
        alt = float(row.get("alt_rel", 0) or 0)
        ts  = float(row.get("timestamp", 0) or 0)
        if lat == 0 and lon == 0:
            return
        drone_data[did].append({"t": ts, "lat": lat, "lon": lon, "alt": alt})
    except (ValueError, KeyError):
        pass

# Initialer Lesevorgang
read_new_rows()

# ── Referenzpunkt ─────────────────────────────────────────────────────────────

def get_ref():
    lats = [rows[0]["lat"] for rows in drone_data.values() if rows]
    lons = [rows[0]["lon"] for rows in drone_data.values() if rows]
    if not lats:
        return -35.363352, 149.165241
    return sum(lats)/len(lats), sum(lons)/len(lons)

def to_local(lat, lon, ref_lat, ref_lon):
    north = (lat - ref_lat) * 111320.0
    east  = (lon - ref_lon) * 111320.0 * math.cos(math.radians(ref_lat))
    return north, east

def min_sep(data_dict, ref_lat, ref_lon):
    ids = [did for did, rows in data_dict.items() if rows]
    if len(ids) < 2:
        return None
    latest = {}
    for did in ids:
        r = data_dict[did][-1]
        n, e = to_local(r["lat"], r["lon"], ref_lat, ref_lon)
        latest[did] = (n, e, r["alt"])
    min_d = float("inf")
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            pa, pb = latest[a], latest[b]
            d = math.sqrt((pa[0]-pb[0])**2 + (pa[1]-pb[1])**2 + (pa[2]-pb[2])**2)
            min_d = min(min_d, d)
    return min_d if min_d != float("inf") else None

# ── Plot aufbauen ─────────────────────────────────────────────────────────────

fig = plt.figure(figsize=(15, 9))
fig.suptitle("Live Swarm Map", fontsize=13, fontweight="bold")
gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

ax_map = fig.add_subplot(gs[:, 0])   # Karte links (volle Höhe)
ax_alt = fig.add_subplot(gs[0, 1])   # Höhe oben rechts
ax_sep = fig.add_subplot(gs[1, 1])   # Abstand unten rechts

ax_map.set_title("Flugpfade (Draufsicht)", fontweight="bold")
ax_map.set_xlabel("East (m)")
ax_map.set_ylabel("North (m)")
ax_map.set_aspect("equal")
ax_map.grid(True, alpha=0.3)

ax_alt.set_title("Höhe (m)")
ax_alt.set_ylabel("m")
ax_alt.grid(True, alpha=0.3)

ax_sep.set_title("Min. Abstand (m)")
ax_sep.set_ylabel("m")
ax_sep.set_xlabel("Zeit (s)")
ax_sep.axhline(3.0, color="red", linestyle="--", linewidth=1.0, alpha=0.7)
ax_sep.grid(True, alpha=0.3)

sep_times = []
sep_vals  = []
t0_global = [None]

# Matplotlib-Objekte pro Drohne
path_lines  = {}
dot_markers = {}
alt_lines   = {}

for ci, did in enumerate(drone_ids):
    color = COLORS(ci % 10)
    line, = ax_map.plot([], [], linewidth=1.2, color=color, alpha=0.6)
    dot,  = ax_map.plot([], [], "o", markersize=10, color=color, zorder=5)
    ax_map.annotate(did, (0, 0), fontsize=8, color=color,
                    xytext=(5, 5), textcoords="offset points",
                    annotation_clip=False).set_visible(False)
    path_lines[did]  = line
    dot_markers[did] = (dot, ax_map.annotate(
        did, (0, 0), fontsize=8, color=color,
        xytext=(5, 5), textcoords="offset points",
        annotation_clip=False,
    ))
    aline, = ax_alt.plot([], [], linewidth=1.2, color=color, label=did)
    alt_lines[did] = aline

ax_alt.legend(fontsize=7, ncol=2, loc="upper left")
sep_line, = ax_sep.plot([], [], color="#E91E63", linewidth=1.5)
sep_fill  = [None]

status_text = fig.text(0.01, 0.01, "", fontsize=8, color="gray",
                        transform=fig.transFigure)

# ── Animation ─────────────────────────────────────────────────────────────────

def update(_frame):
    read_new_rows()
    ref_lat, ref_lon = get_ref()

    if t0_global[0] is None:
        all_ts = [r["t"] for rows in drone_data.values() for r in rows]
        if all_ts:
            t0_global[0] = min(all_ts)

    t0 = t0_global[0] or 0.0

    # Map-Grenzen dynamisch
    all_east, all_north = [], []

    for ci, did in enumerate(drone_ids):
        rows = drone_data[did]
        if not rows:
            continue

        tail_rows = rows[-TAIL:]
        pts = [to_local(r["lat"], r["lon"], ref_lat, ref_lon) for r in tail_rows]
        ns = [p[0] for p in pts]
        es = [p[1] for p in pts]

        path_lines[did].set_data(es, ns)

        # Aktueller Punkt
        dot, ann = dot_markers[did]
        dot.set_data([es[-1]], [ns[-1]])
        ann.set_position((es[-1], ns[-1]))
        ann.set_visible(True)

        all_east.extend(es)
        all_north.extend(ns)

        # Höhe
        T   = [r["t"] - t0 for r in tail_rows]
        alt = [r["alt"] for r in tail_rows]
        alt_lines[did].set_data(T, alt)

    # Map-Grenzen
    if all_east and all_north:
        pad = max(5.0, (max(all_east) - min(all_east)) * 0.2,
                       (max(all_north) - min(all_north)) * 0.2)
        ax_map.set_xlim(min(all_east) - pad, max(all_east) + pad)
        ax_map.set_ylim(min(all_north) - pad, max(all_north) + pad)

    # Höhenachse
    ax_alt.relim()
    ax_alt.autoscale_view()

    # Minimaler Abstand
    ms = min_sep(drone_data, ref_lat, ref_lon)
    if ms is not None:
        now = time.time() - t0
        sep_times.append(now)
        sep_vals.append(ms)
        sep_line.set_data(sep_times[-500:], sep_vals[-500:])
        ax_sep.relim()
        ax_sep.autoscale_view()
        ax_sep.set_ylim(bottom=0)

    # Status
    n_drones = sum(1 for rows in drone_data.values() if rows)
    latest_t = max((rows[-1]["t"] for rows in drone_data.values() if rows), default=0)
    elapsed  = latest_t - t0 if t0 else 0
    status_text.set_text(
        f"Drohnen mit Daten: {n_drones}/{len(drone_ids)}  |  "
        f"Experiment-Zeit: {elapsed:.0f}s  |  "
        f"Min-Abstand: {ms:.1f}m" if ms else
        f"Drohnen mit Daten: {n_drones}/{len(drone_ids)}"
    )

    return list(path_lines.values()) + [d for d, _ in dot_markers.values()] + \
           list(alt_lines.values()) + [sep_line, status_text]

ani = animation.FuncAnimation(
    fig, update,
    interval=int(args.interval * 1000),
    blit=False,
    cache_frame_data=False,
)

plt.show()
