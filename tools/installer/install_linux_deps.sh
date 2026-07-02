#!/usr/bin/env bash
# SkyMeshX — Linux system dependency installer
# Installs GStreamer (video stream), OpenCV, Qt X11 libs, and optionally
# ROS2 Humble/Jazzy for the full GCS + PX4 bridge stack.
# NOTE: ROS2 is assumed to be already installed — use --ros2 to install it.
#
# Usage:
#   bash tools/installer/install_linux_deps.sh [OPTIONS]
#
# Options:
#   --gstreamer     Install GStreamer plugins for video stream decoding
#   --opencv        Install OpenCV (Python binding)
#   --qt            Install PySide6 / Qt X11 runtime libs
#   --ros2          Also install ROS2 + px4_msgs + XRCE-DDS agent
#   --all           Install everything including ROS2
#   -h, --help      Show this help and exit
#
# Tested on:  Ubuntu 22.04 LTS (Jammy) · Ubuntu 24.04 LTS (Noble)
# Run as:     bash tools/installer/install_linux_deps.sh
# Requires:   sudo privileges

set -euo pipefail

# ── Colour helpers ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argument parsing ─────────────────────────────────────────────────────────
DO_ROS2=0
DO_GST=0
DO_CV=0
DO_QT=0

# Default (no flags): install everything EXCEPT ROS2
if [[ $# -eq 0 ]]; then
    DO_GST=1; DO_CV=1; DO_QT=1
fi

for arg in "$@"; do
    case "$arg" in
        --all)       DO_ROS2=1; DO_GST=1; DO_CV=1; DO_QT=1 ;;
        --ros2)      DO_ROS2=1 ;;
        --gstreamer) DO_GST=1  ;;
        --opencv)    DO_CV=1   ;;
        --qt)        DO_QT=1   ;;
        -h|--help)
            sed -n '3,20p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) die "Unknown argument: $arg  (use --help for usage)" ;;
    esac
done

# ── Detect Ubuntu release ────────────────────────────────────────────────────
if [[ ! -f /etc/os-release ]]; then
    die "Cannot detect OS. This script targets Ubuntu 22.04 / 24.04."
fi
# shellcheck source=/dev/null
source /etc/os-release
UBUNTU_CODENAME="${VERSION_CODENAME:-$(lsb_release -sc 2>/dev/null || echo unknown)}"

case "$UBUNTU_CODENAME" in
    jammy)  ROS2_DISTRO="humble"  ;;
    noble)  ROS2_DISTRO="jazzy"   ;;
    *)
        warn "Unrecognised Ubuntu release '$UBUNTU_CODENAME'."
        warn "Defaulting to ROS2 Humble — adjust ROS2_DISTRO if needed."
        ROS2_DISTRO="humble"
        ;;
esac

info "Detected: Ubuntu $VERSION_ID ($UBUNTU_CODENAME)  →  ROS2 $ROS2_DISTRO"
echo ""

# ── Base system update ───────────────────────────────────────────────────────
info "Updating package lists..."
sudo apt-get update -q

# ── Common build / runtime tools ─────────────────────────────────────────────
info "Installing common runtime tools..."
sudo apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    lsb-release \
    software-properties-common \
    python3 \
    python3-pip \
    python3-dev \
    python3-serial \
    python3-setuptools \
    python3-wheel \
    build-essential \
    git
ok "Common tools installed."

# ─────────────────────────────────────────────────────────────────────────────
# ROS2 Installation
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$DO_ROS2" -eq 1 ]]; then
    echo ""
    info "Installing ROS2 $ROS2_DISTRO..."

    # 1. Add ROS2 apt repository
    if [[ ! -f /usr/share/keyrings/ros-archive-keyring.gpg ]]; then
        info "  Adding ROS2 GPG key..."
        curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
            | sudo gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg
    fi

    ROS2_SOURCES="/etc/apt/sources.list.d/ros2.list"
    if [[ ! -f "$ROS2_SOURCES" ]]; then
        info "  Adding ROS2 apt source..."
        echo "deb [arch=$(dpkg --print-architecture) \
signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
https://packages.ros.org/ros2/ubuntu $UBUNTU_CODENAME main" \
            | sudo tee "$ROS2_SOURCES" > /dev/null
        sudo apt-get update -q
    fi

    # 2. Core ROS2 packages
    info "  Installing ros-${ROS2_DISTRO}-ros-base + development tools..."
    sudo apt-get install -y --no-install-recommends \
        "ros-${ROS2_DISTRO}-ros-base" \
        "ros-${ROS2_DISTRO}-rmw-fastrtps-cpp" \
        python3-colcon-common-extensions \
        python3-rosdep \
        python3-argcomplete

    # 3. Python rclpy binding (also available via pip, but apt is preferred)
    info "  Installing python3-rclpy (ROS2 Python client library)..."
    sudo apt-get install -y --no-install-recommends \
        "ros-${ROS2_DISTRO}-rclpy" || \
        pip3 install --user rclpy

    # 4. Micro XRCE-DDS Agent (PX4 uXRCE-DDS bridge)
    info "  Installing Micro XRCE-DDS Agent (PX4 bridge)..."
    if ! command -v MicroXRCEAgent &>/dev/null; then
        pip3 install --user \
            "git+https://github.com/eProsima/Micro-XRCE-DDS-Agent.git" \
            2>/dev/null || \
        sudo snap install micro-xrce-dds-agent --edge 2>/dev/null || \
        warn "  Could not auto-install MicroXRCEAgent. Install manually:" \
             "  https://micro.ros.org/docs/overview/xrce_dds"
    else
        ok "  MicroXRCEAgent already present."
    fi

    # 5. rosdep init (first run only)
    if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
        info "  Initialising rosdep..."
        sudo rosdep init 2>/dev/null || true
    fi
    rosdep update --rosdistro "$ROS2_DISTRO" 2>/dev/null || true

    # 6. Shell setup hint
    ROS2_SETUP="/opt/ros/${ROS2_DISTRO}/setup.bash"
    if ! grep -qF "source $ROS2_SETUP" ~/.bashrc 2>/dev/null; then
        warn "  Add the following to your ~/.bashrc to auto-source ROS2:"
        warn "    echo 'source $ROS2_SETUP' >> ~/.bashrc"
    fi

    ok "ROS2 $ROS2_DISTRO installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# GStreamer — video stream decoding (rtp-h264-udp, RTSP, …)
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$DO_GST" -eq 1 ]]; then
    echo ""
    info "Installing GStreamer plugins for video stream decoding..."
    sudo apt-get install -y --no-install-recommends \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav \
        gstreamer1.0-rtsp \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        python3-gst-1.0
    ok "GStreamer installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# OpenCV — cv2 used by VideoStreamContext for RTP/H.264 frame decoding
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$DO_CV" -eq 1 ]]; then
    echo ""
    info "Installing OpenCV (python3-opencv)..."
    # Prefer apt build — it links against the system GStreamer backend so that
    # cv2.VideoCapture can open GStreamer pipelines directly.
    sudo apt-get install -y --no-install-recommends \
        python3-opencv \
        libopencv-dev || \
    pip3 install --user opencv-python-headless
    ok "OpenCV installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# Qt / PySide6 X11 runtime dependencies
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$DO_QT" -eq 1 ]]; then
    echo ""
    info "Installing Qt/PySide6 X11 runtime libraries..."
    sudo apt-get install -y --no-install-recommends \
        libegl1 \
        libgl1 \
        libdbus-1-3 \
        libxkbcommon-x11-0 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xinerama0 \
        libxcb-xfixes0 \
        libxcb-util1 \
        libxcb1 \
        libx11-xcb1
    ok "Qt X11 runtime libraries installed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# Python packages (pip)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
info "Installing Python packages (requirements.txt)..."
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

pip3 install --user -r "${PROJECT_ROOT}/requirements.txt"
pip3 install --user -e "${PROJECT_ROOT}"
ok "Python packages installed."

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} SkyMeshX Linux dependency installation complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
[[ "$DO_ROS2" -eq 1 ]] && echo -e "  ${BLUE}ROS2 $ROS2_DISTRO${NC}     ✓ (source /opt/ros/${ROS2_DISTRO}/setup.bash)"
[[ "$DO_GST"  -eq 1 ]] && echo -e "  ${BLUE}GStreamer${NC}      ✓"
[[ "$DO_CV"   -eq 1 ]] && echo -e "  ${BLUE}OpenCV${NC}         ✓"
[[ "$DO_QT"   -eq 1 ]] && echo -e "  ${BLUE}Qt X11 libs${NC}    ✓"
echo ""
if [[ "$DO_ROS2" -eq 1 ]]; then
    echo -e "  ${YELLOW}Next steps for ROS2/PX4:${NC}"
    echo -e "  1. source /opt/ros/${ROS2_DISTRO}/setup.bash"
    echo -e "  2. Build px4_msgs workspace:"
    echo -e "       mkdir -p ~/ros2_ws/src"
    echo -e "       cd ~/ros2_ws/src && git clone https://github.com/PX4/px4_msgs"
    echo -e "       cd ~/ros2_ws && colcon build --packages-select px4_msgs"
    echo -e "       source ~/ros2_ws/install/setup.bash"
    echo -e "  3. Start XRCE-DDS Agent:  MicroXRCEAgent udp4 -p 8888"
    echo ""
fi
