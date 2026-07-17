"""
Map Tab — Live OSM map with all drone positions, tracks, waypoints, geofence.
Uses PyQtWebEngine to embed a Leaflet.js map (no Qt Location needed).
"""
import json
import math
from html import escape
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QGroupBox, QCheckBox,
    QDoubleSpinBox, QFormLayout, QListWidget, QListWidgetItem,
    QFrame, QTextEdit
)
from PySide6.QtCore import Qt, QUrl, Slot, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal

from tools.ui.legacy.style import DRONE_COLORS
from tools.ui.legacy.widgets import section_header, h_separator


MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  html, body { margin:0; padding:0; height:100%; background:#0f1117; }
  #map { height:100%; }
  .drone-label {
    background: rgba(15,17,23,0.85);
    color: white;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid rgba(255,255,255,0.2);
    white-space: nowrap;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
var map = L.map('map', {
  center: [48.1374, 11.5754],
  zoom: 16,
  zoomControl: true,
  preferCanvas: true
});

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 22
}).addTo(map);

var drones = {};
var tracks = {};
var waypoints = [];
var geofenceCircle = null;
var bridge = null;

new QWebChannel(qt.webChannelTransport, function(channel) {
  bridge = channel.objects.mapBridge;
  bridge.updateDrones.connect(function(json_str) {
    var data = JSON.parse(json_str);
    updateDroneMarkers(data);
  });
  bridge.updateWaypoints.connect(function(json_str) {
    var wps = JSON.parse(json_str);
    updateWaypoints(wps);
  });
  bridge.updateGeofence.connect(function(lat, lon, radius) {
    updateGeofence(lat, lon, radius);
  });
  bridge.clearTracks.connect(function() {
    for (var id in tracks) { map.removeLayer(tracks[id]); }
    tracks = {};
  });
  bridge.centerMap.connect(function(lat, lon) {
    map.setView([lat, lon], map.getZoom());
  });
});

var COLORS = ["#3b82f6","#22c55e","#f59e0b","#ec4899",
              "#8b5cf6","#14b8a6","#f97316","#06b6d4"];

function droneIcon(color, armed) {
  var c = armed ? color : '#94a3b8';
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' +
    '<circle cx="14" cy="14" r="13" fill="' + c + '33" stroke="' + c + '" stroke-width="2"/>' +
    '<polygon points="14,4 18,18 14,15 10,18" fill="' + c + '"/>' +
    '</svg>';
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}

function updateDroneMarkers(data) {
  var idx = 0;
  for (var id in data) {
    var d = data[id];
    var color = COLORS[idx % COLORS.length];
    idx++;
    if (!d.lat || !d.lon) continue;
    var latlng = [d.lat, d.lon];

    if (!drones[id]) {
      drones[id] = {
        marker: L.marker(latlng, {icon: droneIcon(color, d.armed)}).addTo(map),
        label:  L.marker(latlng, {
          icon: L.divIcon({
            html: '<div class="drone-label">' + id + '</div>',
            className: '', iconAnchor: [-16, 8]
          })
        }).addTo(map)
      };
      tracks[id] = L.polyline([latlng], {color: color, weight: 2, opacity: 0.7}).addTo(map);
    } else {
      drones[id].marker.setLatLng(latlng);
      drones[id].marker.setIcon(droneIcon(color, d.armed));
      drones[id].label.setLatLng(latlng);
      tracks[id].addLatLng(latlng);
    }

    var tip = id + '<br>Alt: ' + (d.alt_rel||0).toFixed(1) + 'm' +
              '<br>Speed: ' + (d.groundspeed||0).toFixed(1) + ' m/s' +
              '<br>' + (d.flight_mode||'UNKNOWN') + (d.armed ? ' [ARMED]' : '');
    drones[id].marker.bindTooltip(tip, {permanent: false});
  }
  // Remove stale drones
  for (var id in drones) {
    if (!data[id]) {
      map.removeLayer(drones[id].marker);
      map.removeLayer(drones[id].label);
      if (tracks[id]) map.removeLayer(tracks[id]);
      delete drones[id];
      delete tracks[id];
    }
  }
}

var wpMarkers = [];
var wpLine = null;
function updateWaypoints(wps) {
  wpMarkers.forEach(function(m){ map.removeLayer(m); });
  wpMarkers = [];
  if (wpLine) { map.removeLayer(wpLine); wpLine = null; }
  if (!wps || wps.length === 0) return;
  var latlngs = [];
  wps.forEach(function(wp, i) {
    var m = L.circleMarker([wp.lat, wp.lon], {
      radius: 8, color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.8,
      weight: 2
    }).addTo(map);
    m.bindTooltip('WP ' + i + '<br>Alt: ' + wp.alt + 'm', {permanent: false});
    wpMarkers.push(m);
    latlngs.push([wp.lat, wp.lon]);
  });
  wpLine = L.polyline(latlngs, {color: '#f59e0b', weight: 2, dashArray: '6 4'}).addTo(map);
}

function updateGeofence(lat, lon, radius) {
  if (geofenceCircle) map.removeLayer(geofenceCircle);
  geofenceCircle = L.circle([lat, lon], {
    radius: radius,
    color: '#ef4444',
    fillColor: '#ef4444',
    fillOpacity: 0.06,
    weight: 2,
    dashArray: '8 4'
  }).addTo(map);
}

map.on('click', function(e) {
  if (bridge) bridge.mapClicked(e.latlng.lat, e.latlng.lng);
});
</script>
</body>
</html>
"""


class MapBridge(QObject):
    """Qt object exposed to JavaScript via WebChannel."""
    updateDrones    = Signal(str)
    updateWaypoints = Signal(str)
    updateGeofence  = Signal(float, float, float)
    clearTracks     = Signal()
    centerMap       = Signal(float, float)

    map_clicked = Signal(float, float)   # from JS → Python

    @Slot(float, float)
    def mapClicked(self, lat: float, lon: float):   # called by JS
        self.map_clicked.emit(lat, lon)


class MapTab(QWidget):

    def __init__(self, swarm_backend, parent=None):
        super().__init__(parent)
        self._swarm    = swarm_backend
        self._waypoints: list = []
        self._add_wp_mode = False
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background: #161b27; border-right: 1px solid #2d3748;")
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(12, 12, 12, 12)
        sb_lay.setSpacing(10)

        sb_lay.addWidget(section_header("Map Controls", "#3b82f6"))

        # Layers
        grp_layers = QGroupBox("Layers")
        lay_layers = QVBoxLayout(grp_layers)
        self._chk_tracks   = QCheckBox("Flight Tracks")
        self._chk_tracks.setChecked(True)
        self._chk_waypoints= QCheckBox("Waypoints")
        self._chk_waypoints.setChecked(True)
        self._chk_geofence = QCheckBox("Geofence")
        self._chk_geofence.setChecked(True)
        for chk in [self._chk_tracks, self._chk_waypoints, self._chk_geofence]:
            lay_layers.addWidget(chk)
        sb_lay.addWidget(grp_layers)

        # Geofence
        grp_gf = QGroupBox("Geofence")
        lay_gf = QFormLayout(grp_gf)
        self._gf_radius = QDoubleSpinBox()
        self._gf_radius.setRange(10, 5000)
        self._gf_radius.setValue(50.0)
        self._gf_radius.setSuffix(" m")
        lay_gf.addRow("Radius:", self._gf_radius)
        btn_gf = QPushButton("Apply Geofence")
        btn_gf.setObjectName("btn_primary")
        btn_gf.clicked.connect(self._apply_geofence)
        lay_gf.addRow(btn_gf)
        sb_lay.addWidget(grp_gf)

        # Waypoints
        grp_wp = QGroupBox("Mission Waypoints")
        lay_wp = QVBoxLayout(grp_wp)
        self._btn_add_wp = QPushButton("📍 Click Map to Add WP")
        self._btn_add_wp.setCheckable(True)
        self._btn_add_wp.setObjectName("btn_warning")
        self._btn_add_wp.toggled.connect(self._toggle_wp_mode)
        lay_wp.addWidget(self._btn_add_wp)
        self._wp_list = QListWidget()
        self._wp_list.setMaximumHeight(120)
        self._wp_list.setStyleSheet("background: #0d1117; border: 1px solid #2d3748; border-radius: 6px;")
        lay_wp.addWidget(self._wp_list)
        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("btn_danger")
        btn_clear.clicked.connect(self._clear_waypoints)
        btn_row.addWidget(btn_clear)
        btn_send = QPushButton("Send")
        btn_send.setObjectName("btn_success")
        btn_row.addWidget(btn_send)
        lay_wp.addLayout(btn_row)
        sb_lay.addWidget(grp_wp)

        # Center map
        btn_center = QPushButton("🎯 Center on Swarm")
        btn_center.clicked.connect(self._center_on_swarm)
        sb_lay.addWidget(btn_center)

        btn_clear_tracks = QPushButton("🗑 Clear Tracks")
        btn_clear_tracks.clicked.connect(self._clear_tracks)
        sb_lay.addWidget(btn_clear_tracks)

        sb_lay.addStretch()

        # Status
        sb_lay.addWidget(h_separator())
        sb_lay.addWidget(section_header("Click Info"))
        self._click_info = QLabel("—")
        self._click_info.setWordWrap(True)
        self._click_info.setStyleSheet("color: #94a3b8; font-size: 11px; font-family: monospace;")
        sb_lay.addWidget(self._click_info)

        root.addWidget(sidebar)

        # ── Map ───────────────────────────────────────────────────────────
        self._web = QWebEngineView()
        self._channel = QWebChannel()
        self._bridge  = MapBridge()
        self._channel.registerObject("mapBridge", self._bridge)
        self._web.page().setWebChannel(self._channel)
        self._web.setHtml(MAP_HTML, QUrl("qrc:/"))
        self._bridge.map_clicked.connect(self._on_map_clicked)
        root.addWidget(self._web, stretch=1)

    def _connect_signals(self):
        self._swarm.swarm_telemetry_updated.connect(self._on_telemetry)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_telemetry(self, all_snaps: dict):
        """
        Update drone positions on map with sanitized telemetry data.
        UI-02 FIX: Validate types and sanitize strings to prevent JSON injection.
        """
        def sanitize_string(s) -> str:
            """Sanitize string for JSON/HTML display to prevent XSS"""
            if not isinstance(s, str):
                s = str(s)
            # Remove control characters, keep only printable + whitespace
            s = ''.join(c for c in s if c.isprintable() or c in '\n\r\t')
            # Escape HTML entities
            return escape(s)
        
        def safe_float(val, default=0.0) -> float:
            """Safely convert to float with fallback"""
            try:
                return float(val)
            except (ValueError, TypeError):
                return default
        
        def safe_bool(val, default=False) -> bool:
            """Safely convert to bool"""
            if isinstance(val, bool):
                return val
            return bool(val) if val else default
        
        payload = {
            did: {
                "lat":         safe_float(snap.get("lat", 0)),
                "lon":         safe_float(snap.get("lon", 0)),
                "alt_rel":     safe_float(snap.get("alt_rel", 0)),
                "groundspeed": safe_float(snap.get("groundspeed", 0)),
                "flight_mode": sanitize_string(snap.get("flight_mode", "UNKNOWN")),
                "armed":       safe_bool(snap.get("armed", False)),
                "heading":     safe_float(snap.get("yaw", 0)),
            }
            for did, snap in all_snaps.items()
        }
        self._bridge.updateDrones.emit(json.dumps(payload))

    def _on_map_clicked(self, lat: float, lon: float):
        """
        Handle map click events with input validation.
        UI-01 FIX: Validate coordinate ranges and sanitize display.
        """
        # Validate coordinate ranges
        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            print(f"[map] Invalid coordinate types: lat={type(lat)}, lon={type(lon)}")
            return
        
        if not (-90 <= lat_float <= 90):
            print(f"[map] Invalid latitude: {lat_float} (must be -90 to 90)")
            return
        
        if not (-180 <= lon_float <= 180):
            print(f"[map] Invalid longitude: {lon_float} (must be -180 to 180)")
            return
        
        # Sanitize for display (escape HTML to prevent XSS)
        safe_lat = escape(f"{lat_float:.6f}")
        safe_lon = escape(f"{lon_float:.6f}")
        self._click_info.setText(f"Lat: {safe_lat}\nLon: {safe_lon}")
        
        if self._add_wp_mode:
            self._waypoints.append({"lat": lat_float, "lon": lon_float, "alt": 10.0})
            self._wp_list.addItem(f"WP{len(self._waypoints)-1}: {lat_float:.5f},{lon_float:.5f}")
            self._bridge.updateWaypoints.emit(json.dumps(self._waypoints))

    def _toggle_wp_mode(self, checked: bool):
        self._add_wp_mode = checked
        self._btn_add_wp.setText(
            "✅ Click to Place WP (active)" if checked else "📍 Click Map to Add WP"
        )

    def _clear_waypoints(self):
        self._waypoints.clear()
        self._wp_list.clear()
        self._bridge.updateWaypoints.emit("[]")

    def _clear_tracks(self):
        self._bridge.clearTracks.emit()

    def _apply_geofence(self):
        snaps = {}
        for did, b in self._swarm.all_backends().items():
            snap = b.get_telemetry_snapshot()
            if snap:
                snaps[did] = snap
        if snaps:
            first = next(iter(snaps.values()))
            lat = first.get("home_lat") or first.get("lat", 0)
            lon = first.get("home_lon") or first.get("lon", 0)
        else:
            lat, lon = 48.1374, 11.5754
        r = self._gf_radius.value()
        self._bridge.updateGeofence.emit(lat, lon, r)

    def _center_on_swarm(self):
        lats, lons = [], []
        for did, b in self._swarm.all_backends().items():
            snap = b.get_telemetry_snapshot()
            if snap and snap.get("lat"):
                lats.append(snap["lat"])
                lons.append(snap["lon"])
        if lats:
            self._bridge.centerMap.emit(sum(lats)/len(lats), sum(lons)/len(lons))
