"""
Plot flight telemetry from a SkyMeshX CSV log.

Usage:
    python tools/plot_flight.py                        # latest log
    python tools/plot_flight.py logs/20260507_...csv   # specific file
"""
import argparse
import csv
import glob
import os
import sys

# ── argument ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("file", nargs="?", default=None, help="CSV log file path")
args = parser.parse_args()

if args.file:
    path = args.file
else:
    files = sorted(glob.glob("logs/*_telemetry.csv"))
    if not files:
        sys.exit("No log files found in logs/")
    path = files[-1]

print(f"Plotting: {path}")

# ── load ──────────────────────────────────────────────────────────────────────
rows = []
with open(path, newline="") as f:
    for row in csv.DictReader(f):
        try:
            rows.append({
                "t":           float(row["timestamp"]),
                "alt_rel":     float(row["alt_rel"]   or 0),
                "groundspeed": float(row["groundspeed"] or 0),
                "battery_pct": float(row["battery_pct"] or 0),
                "battery_v":   float(row["battery_v"]  or 0),
                "roll":        float(row["roll"]       or 0),
                "pitch":       float(row["pitch"]      or 0),
                "yaw":         float(row["yaw"]        or 0),
                "vz":          float(row["vz"]         or 0),
                "armed":       row["armed"],
                "mode":        row["flight_mode"],
            })
        except (ValueError, KeyError):
            continue

if not rows:
    sys.exit("No valid rows in log file.")

t0 = rows[0]["t"]
T  = [r["t"] - t0 for r in rows]

print(f"{len(rows)} data points over {T[-1]:.1f}s")
print(f"Max altitude:   {max(r['alt_rel'] for r in rows):.1f} m")
print(f"Max speed:      {max(r['groundspeed'] for r in rows):.2f} m/s")
print(f"Battery drain:  {rows[0]['battery_pct']:.0f}% → {rows[-1]['battery_pct']:.0f}%")

# ── plot ──────────────────────────────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
except ImportError:
    print("\nmatplotlib not installed. Run: pip install matplotlib")
    print("Printing text summary instead:\n")
    for i in range(0, len(rows), max(1, len(rows)//20)):
        r = rows[i]
        print(f"  t={T[i]:6.1f}s  alt={r['alt_rel']:6.2f}m  spd={r['groundspeed']:5.2f}m/s  bat={r['battery_pct']:5.1f}%  mode={r['mode']}")
    sys.exit(0)

fig = plt.figure(figsize=(14, 9))
fig.suptitle(f"Flight Log — {os.path.basename(path)}", fontsize=13, fontweight="bold")
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

alt  = [r["alt_rel"]     for r in rows]
spd  = [r["groundspeed"] for r in rows]
bat  = [r["battery_pct"] for r in rows]
batv = [r["battery_v"]   for r in rows]
roll = [r["roll"]        for r in rows]
pitch= [r["pitch"]       for r in rows]
vz   = [r["vz"]          for r in rows]

# 1 — Altitude
ax1 = fig.add_subplot(gs[0, :])
ax1.plot(T, alt, color="#2196F3", linewidth=1.5)
ax1.fill_between(T, alt, alpha=0.15, color="#2196F3")
ax1.set_ylabel("Altitude (m)")
ax1.set_title("Relative Altitude")
ax1.grid(True, alpha=0.3)

# 2 — Groundspeed
ax2 = fig.add_subplot(gs[1, 0])
ax2.plot(T, spd, color="#4CAF50", linewidth=1.5)
ax2.set_ylabel("m/s")
ax2.set_title("Groundspeed")
ax2.grid(True, alpha=0.3)

# 3 — Vertical speed
ax3 = fig.add_subplot(gs[1, 1])
ax3.plot(T, vz, color="#FF9800", linewidth=1.5)
ax3.axhline(0, color="gray", linewidth=0.8, linestyle="--")
ax3.set_ylabel("m/s")
ax3.set_title("Vertical Speed (vz)")
ax3.grid(True, alpha=0.3)

# 4 — Battery %
ax4 = fig.add_subplot(gs[2, 0])
ax4.plot(T, bat, color="#F44336", linewidth=1.5)
ax4.set_ylabel("%")
ax4.set_xlabel("Time (s)")
ax4.set_title("Battery %")
ax4.grid(True, alpha=0.3)

# 5 — Roll / Pitch
ax5 = fig.add_subplot(gs[2, 1])
ax5.plot(T, roll,  label="Roll",  linewidth=1.2)
ax5.plot(T, pitch, label="Pitch", linewidth=1.2)
ax5.axhline(0, color="gray", linewidth=0.8, linestyle="--")
ax5.set_ylabel("degrees")
ax5.set_xlabel("Time (s)")
ax5.set_title("Attitude")
ax5.legend(fontsize=9)
ax5.grid(True, alpha=0.3)

os.makedirs("plots", exist_ok=True)
out = os.path.join("plots", os.path.basename(path).replace(".csv", ".png"))
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved: {out}")
plt.show()
