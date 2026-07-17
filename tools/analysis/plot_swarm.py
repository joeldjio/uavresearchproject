"""
Multi-UAV Swarm Visualizer — alle Drohnen eines Experiments auf einmal.

Usage:
    python tools/plot_swarm.py                        # letzter Experiment-Run (alle CSVs)
    python tools/plot_swarm.py logs/20260507_193004_* # bestimmter Zeitstempel

Ausgabe:
    plots/<timestamp>_swarm.png   — 5 Graphen:
        1. 2D Karte: Flugpfade aller Drohnen (lat/lon → lokale Meter)
        2. Höhe über Zeit (alle Drohnen)
        3. Groundspeed über Zeit
        4. Batterie % über Zeit
        5. Minimaler Abstand zwischen Drohnen über Zeit (Kollisionsgraph)
"""
import argparse
import csv
import glob
import math
import os
import sys
from collections import defaultdict

# ── Argumente ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("files", nargs="*", help="CSV log files (default: latest run)")
args = parser.parse_args()

if args.files:
    paths = sorted(args.files)
else:
    all_csvs = sorted(glob.glob("logs/*_telemetry.csv"))
    if not all_csvs:
        sys.exit("Keine Log-Dateien in logs/ gefunden.")
    # Letzten Experiment-Run: alle CSVs mit demselben Timestamp-Präfix
    last_ts = "_".join(os.path.basename(all_csvs[-1]).split("_")[:2])
    paths = sorted(glob.glob(f"logs/{last_ts}_*.csv"))
    print(f"Auto-erkannt: Timestamp {last_ts} → {len(paths)} Drohnen")

if not paths:
    sys.exit("Keine Dateien gefunden.")

# ── CSV laden ─────────────────────────────────────────────────────────────────
drones = {}   # drone_id → list of row dicts

for path in paths:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "t":    float(row["timestamp"]),
                    "lat":  float(row["lat"]         or 0),
                    "lon":  float(row["lon"]         or 0),
                    "alt":  float(row["alt_rel"]     or 0),
                    "spd":  float(row["groundspeed"] or 0),
                    "bat":  float(row["battery_pct"] or 0),
                    "id":   row.get("drone_id", os.path.basename(path).split("_telemetry")[0][-6:]),
                })
            except (ValueError, KeyError):
                continue
    if rows:
        did = rows[0]["id"]
        drones[did] = rows

if not drones:
    sys.exit("Keine gültigen Daten in den Log-Dateien.")

print(f"Geladene Drohnen: {sorted(drones.keys())}")

# ── Referenzpunkt: Mittelwert aller Startpositionen ───────────────────────────
ref_lats = [rows[0]["lat"] for rows in drones.values() if rows[0]["lat"] != 0]
ref_lons = [rows[0]["lon"] for rows in drones.values() if rows[0]["lon"] != 0]
ref_lat  = sum(ref_lats) / len(ref_lats) if ref_lats else 0
ref_lon  = sum(ref_lons) / len(ref_lons) if ref_lons else 0

def to_local(lat, lon):
    """GPS → lokale Meter (North/East) relativ zum Referenzpunkt."""
    north = (lat - ref_lat) * 111320.0
    east  = (lon - ref_lon) * 111320.0 * math.cos(math.radians(ref_lat))
    return north, east

# ── Minimaler Abstand zwischen Drohnen über Zeit ──────────────────────────────
def min_separation_over_time(drones_data):
    """Berechnet minimalen paarweisen Abstand per Sekunde."""
    ids = list(drones_data.keys())
    if len(ids) < 2:
        return [], []

    # Interpoliere alle Drohnen auf gemeinsame Zeitachse
    all_ts = sorted({round(r["t"]) for rows in drones_data.values() for r in rows})
    t0 = all_ts[0]
    times = [t - t0 for t in all_ts]

    def interp(rows, ts):
        """Gibt interpolierte Position für Timestamp ts zurück."""
        for i in range(len(rows) - 1):
            if rows[i]["t"] <= ts <= rows[i+1]["t"]:
                f = (ts - rows[i]["t"]) / max(rows[i+1]["t"] - rows[i]["t"], 1e-6)
                lat = rows[i]["lat"] + f * (rows[i+1]["lat"] - rows[i]["lat"])
                lon = rows[i]["lon"] + f * (rows[i+1]["lon"] - rows[i]["lon"])
                alt = rows[i]["alt"] + f * (rows[i+1]["alt"] - rows[i]["alt"])
                return lat, lon, alt
        if ts <= rows[0]["t"]:
            return rows[0]["lat"], rows[0]["lon"], rows[0]["alt"]
        return rows[-1]["lat"], rows[-1]["lon"], rows[-1]["alt"]

    min_dists = []
    for ts in all_ts:
        positions = {}
        for did, rows in drones_data.items():
            lat, lon, alt = interp(rows, ts)
            north, east = to_local(lat, lon)
            positions[did] = (north, east, alt)

        min_d = float("inf")
        for i, id_a in enumerate(ids):
            for id_b in ids[i+1:]:
                a, b = positions[id_a], positions[id_b]
                d = math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)
                min_d = min(min_d, d)
        min_dists.append(min_d if min_d != float("inf") else 0)

    return times, min_dists

# ── Matplotlib ────────────────────────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.cm import get_cmap
except ImportError:
    sys.exit("matplotlib nicht installiert. Run: pip install matplotlib")

COLORS = get_cmap("tab10")
drone_list = sorted(drones.keys())
t0_global  = min(rows[0]["t"] for rows in drones.values())

fig = plt.figure(figsize=(16, 12))
fig.suptitle(f"Swarm Experiment — {len(drone_list)} Drohnen", fontsize=14, fontweight="bold")
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

# ── 1. 2D Karte: Flugpfade ────────────────────────────────────────────────────
ax_map = fig.add_subplot(gs[0:2, 0])
ax_map.set_title("Flugpfade (lokale Meter, Draufsicht)", fontweight="bold")
ax_map.set_xlabel("East (m)")
ax_map.set_ylabel("North (m)")
ax_map.set_aspect("equal")
ax_map.grid(True, alpha=0.3)

for ci, did in enumerate(drone_list):
    rows = drones[did]
    # Nur Punkte mit gültigem GPS
    pts = [(to_local(r["lat"], r["lon"])) for r in rows if r["lat"] != 0]
    if not pts:
        continue
    ns, es = zip(*pts)
    color = COLORS(ci % 10)
    ax_map.plot(es, ns, linewidth=1.2, color=color, alpha=0.7)
    # Startpunkt
    ax_map.scatter(es[0],  ns[0],  marker="o", s=60,  color=color, zorder=5)
    # Endpunkt
    ax_map.scatter(es[-1], ns[-1], marker="x", s=80,  color=color, zorder=5, linewidths=2)
    # Label an letzter Position
    ax_map.annotate(did, (es[-1], ns[-1]), fontsize=7, ha="left",
                    xytext=(3, 3), textcoords="offset points", color=color)

ax_map.scatter([], [], marker="o", s=60,  color="gray", label="Start")
ax_map.scatter([], [], marker="x", s=80,  color="gray", label="Ende", linewidths=2)
ax_map.legend(fontsize=8, loc="upper right")

# ── 2. Höhe über Zeit ─────────────────────────────────────────────────────────
ax_alt = fig.add_subplot(gs[0, 1])
ax_alt.set_title("Höhe (m)")
ax_alt.set_ylabel("m")
ax_alt.grid(True, alpha=0.3)

for ci, did in enumerate(drone_list):
    rows = drones[did]
    T   = [r["t"] - t0_global for r in rows]
    alt = [r["alt"] for r in rows]
    ax_alt.plot(T, alt, linewidth=1.2, color=COLORS(ci % 10), label=did)

ax_alt.legend(fontsize=7, ncol=2, loc="lower right")

# ── 3. Groundspeed über Zeit ──────────────────────────────────────────────────
ax_spd = fig.add_subplot(gs[1, 1])
ax_spd.set_title("Groundspeed (m/s)")
ax_spd.set_ylabel("m/s")
ax_spd.grid(True, alpha=0.3)

for ci, did in enumerate(drone_list):
    rows = drones[did]
    T   = [r["t"] - t0_global for r in rows]
    spd = [r["spd"] for r in rows]
    ax_spd.plot(T, spd, linewidth=1.0, color=COLORS(ci % 10), alpha=0.8)

# ── 4. Batterie % über Zeit ───────────────────────────────────────────────────
ax_bat = fig.add_subplot(gs[2, 0])
ax_bat.set_title("Batterie (%)")
ax_bat.set_ylabel("%")
ax_bat.set_xlabel("Zeit (s)")
ax_bat.grid(True, alpha=0.3)

for ci, did in enumerate(drone_list):
    rows = drones[did]
    T   = [r["t"] - t0_global for r in rows]
    bat = [r["bat"] for r in rows]
    ax_bat.plot(T, bat, linewidth=1.2, color=COLORS(ci % 10))

# ── 5. Minimaler Abstand (Kollisionsgraph) ────────────────────────────────────
ax_sep = fig.add_subplot(gs[2, 1])
ax_sep.set_title("Min. Abstand zwischen Drohnen (m)")
ax_sep.set_ylabel("Abstand (m)")
ax_sep.set_xlabel("Zeit (s)")
ax_sep.grid(True, alpha=0.3)

print("Berechne minimale Abstände ...")
sep_times, sep_dists = min_separation_over_time(drones)
if sep_times:
    ax_sep.plot(sep_times, sep_dists, color="#E91E63", linewidth=1.5)
    ax_sep.axhline(3.0, color="red", linestyle="--", linewidth=1.0, label="Min 3m")
    ax_sep.fill_between(sep_times, sep_dists, 3.0,
                        where=[d < 3.0 for d in sep_dists],
                        color="red", alpha=0.3, label="Kollision!")
    ax_sep.legend(fontsize=8)
    min_overall = min(sep_dists)
    ax_sep.set_ylim(bottom=0)
    print(f"Minimaler Abstand insgesamt: {min_overall:.2f}m")

# ── Speichern ─────────────────────────────────────────────────────────────────
os.makedirs("plots", exist_ok=True)
ts_prefix = "_".join(os.path.basename(paths[0]).split("_")[:2])
out = os.path.join("plots", f"{ts_prefix}_swarm.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nGespeichert: {out}")
plt.show()
