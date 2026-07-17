#!/bin/bash
# PX4 SITL + Gazebo + XRCE-DDS Agent Launcher
# Usage: ./launch_px4_sitl.sh [namespace] [model] [px4_dir]

set -e

# Farben für Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default-Werte (können über Argumente überschrieben werden)
NAMESPACE="${1:-uav_1}"
MODEL="${2:-x500}"
PX4_DIR="${3:-/home/iruz/PX4-Autopilot}"
ROS2_SETUP_1="/opt/ros/humble/setup.bash"
ROS2_SETUP_2="/home/iruz/ws_sensor_combined/install/setup.bash"
XRCE_PORT=8888

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PX4 SITL + Gazebo + XRCE-DDS Launcher${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Namespace:${NC} $NAMESPACE"
echo -e "${YELLOW}Model:${NC} $MODEL"
echo -e "${YELLOW}PX4 Dir:${NC} $PX4_DIR"
echo -e "${YELLOW}XRCE Port:${NC} $XRCE_PORT"
echo ""

# Cleanup-Funktion
cleanup() {
    echo -e "\n${BLUE}Shutting down...${NC}"
    if [ ! -z "$PX4_PID" ]; then
        echo -e "${YELLOW}Stopping PX4 SITL (PID: $PX4_PID)...${NC}"
        kill $PX4_PID 2>/dev/null || true
    fi
    if [ ! -z "$AGENT_PID" ]; then
        echo -e "${YELLOW}Stopping XRCE-DDS Agent (PID: $AGENT_PID)...${NC}"
        kill $AGENT_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Cleanup complete${NC}"
    exit 0
}

# Trap SIGINT (Ctrl+C) und SIGTERM
trap cleanup SIGINT SIGTERM

# Prüfe ob PX4 Directory existiert
if [ ! -d "$PX4_DIR" ]; then
    echo -e "${RED}ERROR: PX4 directory not found: $PX4_DIR${NC}"
    exit 1
fi

# Prüfe ob ROS2 setup files existieren
if [ ! -f "$ROS2_SETUP_1" ]; then
    echo -e "${YELLOW}WARNING: ROS2 setup file not found: $ROS2_SETUP_1${NC}"
fi
if [ ! -f "$ROS2_SETUP_2" ]; then
    echo -e "${YELLOW}WARNING: ROS2 workspace setup file not found: $ROS2_SETUP_2${NC}"
fi

# 1. Start XRCE-DDS Agent
echo -e "${GREEN}[1/2] Starting XRCE-DDS Agent on port $XRCE_PORT...${NC}"
MicroXRCEAgent udp4 -p $XRCE_PORT > /tmp/xrce_agent_${NAMESPACE}.log 2>&1 &
AGENT_PID=$!
echo -e "  ${BLUE}→ PID: $AGENT_PID${NC}"
echo -e "  ${BLUE}→ Log: /tmp/xrce_agent_${NAMESPACE}.log${NC}"
sleep 2

# Prüfe ob Agent läuft
if ! kill -0 $AGENT_PID 2>/dev/null; then
    echo -e "${RED}ERROR: XRCE-DDS Agent failed to start${NC}"
    echo -e "${YELLOW}Check log: /tmp/xrce_agent_${NAMESPACE}.log${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓ XRCE-DDS Agent running${NC}"

# 2. Start PX4 SITL mit Gazebo
echo -e "${GREEN}[2/2] Starting PX4 SITL (namespace: $NAMESPACE, model: $MODEL)...${NC}"

# Source ROS2 und starte PX4
(
    # Source ROS2 setups
    if [ -f "$ROS2_SETUP_1" ]; then
        source "$ROS2_SETUP_1"
        echo -e "  ${BLUE}→ Sourced: $ROS2_SETUP_1${NC}"
    fi
    if [ -f "$ROS2_SETUP_2" ]; then
        source "$ROS2_SETUP_2"
        echo -e "  ${BLUE}→ Sourced: $ROS2_SETUP_2${NC}"
    fi
    
    # Wechsle zu PX4 Directory
    cd "$PX4_DIR"
    
    # Starte PX4 SITL
    PX4_UXRCE_DDS_NS=$NAMESPACE make px4_sitl gz_${MODEL}
) > /tmp/px4_sitl_${NAMESPACE}.log 2>&1 &

PX4_PID=$!
echo -e "  ${BLUE}→ PID: $PX4_PID${NC}"
echo -e "  ${BLUE}→ Log: /tmp/px4_sitl_${NAMESPACE}.log${NC}"

# Warte auf PX4 Startup
echo -e "  ${YELLOW}→ Waiting for PX4 to initialize (10 seconds)...${NC}"
sleep 10

# Prüfe ob PX4 läuft
if ! kill -0 $PX4_PID 2>/dev/null; then
    echo -e "${RED}ERROR: PX4 SITL failed to start${NC}"
    echo -e "${YELLOW}Check log: /tmp/px4_sitl_${NAMESPACE}.log${NC}"
    cleanup
    exit 1
fi
echo -e "  ${GREEN}✓ PX4 SITL running${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ All systems running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}Namespace:${NC} $NAMESPACE"
echo -e "${YELLOW}XRCE Agent PID:${NC} $AGENT_PID"
echo -e "${YELLOW}PX4 SITL PID:${NC} $PX4_PID"
echo ""
echo -e "${BLUE}Logs:${NC}"
echo -e "  XRCE Agent: /tmp/xrce_agent_${NAMESPACE}.log"
echo -e "  PX4 SITL:   /tmp/px4_sitl_${NAMESPACE}.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all processes${NC}"
echo ""

# Warte auf Benutzer-Interrupt
wait $PX4_PID
