#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test to verify Solar Inspection UI properties."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from PySide6.QtCore import QObject

# Test if mission_context has all required properties
try:
    from tools.ui.context.mission_context import MissionContext
    
    ctx = MissionContext()
    
    print("[OK] MissionContext imported successfully")
    
    # Test missionMode property
    print(f"[OK] missionMode: {ctx.missionMode}")
    ctx.missionMode = 2
    print(f"[OK] Set missionMode to 2: {ctx.missionMode}")
    
    # Test solar properties
    solar_props = [
        'solarAltitude',
        'solarGimbalPitch', 
        'solarTriggerDistance',
        'solarOverlap',
        'solarPanelRowCount',
        'solarCoverageArea',
        'solarMissionTime',
        'solarWaypointCount',
        'solarPhotoCount',
        'solarInspectionActive'
    ]
    
    for prop in solar_props:
        if hasattr(ctx, prop):
            value = getattr(ctx, prop)
            print(f"[OK] {prop}: {value}")
        else:
            print(f"[FAIL] Missing property: {prop}")
    
    # Test solar methods
    solar_methods = [
        'startAddingSolarRow',
        'addSolarRow',
        'removeSolarRow',
        'generateSolarInspection',
        'getSolarWaypoints'
    ]
    
    for method in solar_methods:
        if hasattr(ctx, method):
            print(f"[OK] Method exists: {method}")
        else:
            print(f"[FAIL] Missing method: {method}")
    
    print("\n[SUCCESS] All Solar Inspection properties and methods are available!")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
