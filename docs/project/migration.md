# Migration Guide: DroneResearch → SkyMeshX

## Overview

The project has been rebranded from **DroneResearch/UAVResearch** to **SkyMeshX** (v0.3.0).

## What Changed

### Package Name
- **Old:** `droneresearch`
- **New:** `skymeshx`

### CLI Command
- **Old:** `droneresearch`
- **New:** `skymeshx`

### UI Application
- **Old:** UAVResearch GCS
- **New:** SkyMeshX GCS

### Repository
- **Old:** `github.com/joeldjio/uavresearchproject`
- **New:** `github.com/joeldjio/skymeshx`

## Migration Steps

### 1. Update Your Code

Replace all imports:

```python
# Old
from droneresearch import Drone, Swarm
from droneresearch.safety import APFSafetyFilter
from droneresearch.control import MissionEngine

# New
from skymeshx import Drone, Swarm
from skymeshx.safety import APFSafetyFilter
from skymeshx.control import MissionEngine
```

### 2. Update CLI Commands

```bash
# Old
droneresearch connect --port tcp:127.0.0.1:5762
droneresearch arm
droneresearch takeoff --alt 10

# New
skymeshx connect --port tcp:127.0.0.1:5762
skymeshx arm
skymeshx takeoff --alt 10
```

### 3. Update Installation

```bash
# Uninstall old version
pip uninstall droneresearch

# Install new version
pip install skymeshx
# or from source
pip install -e .
```

### 4. Update Requirements Files

```txt
# Old
droneresearch>=0.2.0

# New
skymeshx>=0.3.0
```

### 5. Update Configuration Files

If you have any configuration files referencing the old names, update them:

```yaml
# Old
package: droneresearch
command: droneresearch

# New
package: skymeshx
command: skymeshx
```

## Breaking Changes

### Python API
- All module paths changed from `droneresearch.*` to `skymeshx.*`
- CLI command changed from `droneresearch` to `skymeshx`

### No Functional Changes
- All APIs remain the same
- All features work identically
- Configuration formats unchanged

## Compatibility

### Not Compatible
- Code using `import droneresearch` will fail
- Scripts calling `droneresearch` CLI will fail

### Still Compatible
- MAVLink protocol (unchanged)
- ROS2 topics (unchanged)
- Configuration file formats (unchanged)
- Data file formats (unchanged)

## Why the Rebrand?

**SkyMeshX** better represents the project's focus:
- **Sky** - Aerial/drone domain
- **Mesh** - Network topology for swarm coordination
- **X** - eXtended capabilities, neXt generation

The name emphasizes:
- Multi-drone mesh networking
- Swarm coordination
- Distributed control systems
- Field coverage planning

## Support

- **Documentation:** https://github.com/joeldjio/skymeshx/tree/main/docs
- **Issues:** https://github.com/joeldjio/skymeshx/issues
- **Discussions:** https://github.com/joeldjio/skymeshx/discussions

## Version History

- **v0.3.0** - Rebranded to SkyMeshX
- **v0.2.0** - Last version as DroneResearch