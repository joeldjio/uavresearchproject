"""
Tests for PX4GazeboCluster automation.

Tests the PX4 SITL + Gazebo + XRCE-DDS automation without actually
starting processes (mocked).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from skymeshx.simulation.px4_gazebo import PX4GazeboCluster
from skymeshx.exceptions import ConfigurationError, InvalidParameterError, SimulationError


class TestPX4GazeboCluster:
    """Test PX4GazeboCluster class."""
    
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_init_default_params(self, mock_isdir):
        """Test initialization with default parameters."""
        mock_isdir.return_value = True
        cluster = PX4GazeboCluster()
        
        assert cluster.num_drones == 1
        assert cluster.model == "x500"
        assert cluster.xrce_port == 8888
        assert cluster._running is False
        assert len(cluster._processes) == 0
    
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_init_custom_params(self, mock_isdir):
        """Test initialization with custom parameters."""
        mock_isdir.return_value = True
        cluster = PX4GazeboCluster(
            num_drones=3,
            px4_dir="/custom/path",
            model="iris",
            xrce_port=9999,
            ros2_setups=["/opt/ros/humble/setup.bash"],
            namespace_prefix="drone"
        )
        
        assert cluster.num_drones == 3
        assert cluster.px4_dir == "/custom/path"
        assert cluster.model == "iris"
        assert cluster.xrce_port == 9999
        assert cluster.namespace_prefix == "drone"
        assert len(cluster.ros2_setups) == 1
    
    def test_init_invalid_num_drones(self):
        """Test that invalid num_drones raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="num_drones"):
            PX4GazeboCluster(num_drones=0)

        with pytest.raises(InvalidParameterError, match="num_drones"):
            PX4GazeboCluster(num_drones=11)

    def test_init_invalid_px4_dir(self):
        """Test that invalid PX4 directory raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="PX4 directory not found"):
            PX4GazeboCluster(px4_dir="/nonexistent/path")
    
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_get_namespaces(self, mock_isdir):
        """Test namespace generation."""
        mock_isdir.return_value = True
        cluster = PX4GazeboCluster(num_drones=3, namespace_prefix="uav")
        namespaces = cluster.get_namespaces()
        
        assert namespaces == ["uav_1", "uav_2", "uav_3"]
    
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_get_namespaces_custom_prefix(self, mock_isdir):
        """Test namespace generation with custom prefix."""
        mock_isdir.return_value = True
        cluster = PX4GazeboCluster(num_drones=2, namespace_prefix="drone")
        namespaces = cluster.get_namespaces()
        
        assert namespaces == ["drone_1", "drone_2"]
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_start_success(self, mock_isdir, mock_sleep, mock_popen):
        """Test successful cluster start."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=1)
        result = cluster.start()
        
        assert result is True
        assert cluster._running is True
        assert len(cluster._processes) == 2  # Agent + 1 SITL
        assert mock_popen.call_count == 2
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_start_already_running(self, mock_isdir, mock_sleep, mock_popen):
        """Test that starting already running cluster returns False."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=1)
        cluster.start()
        
        # Try to start again
        result = cluster.start()
        assert result is False
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_start_agent_fails(self, mock_isdir, mock_sleep, mock_popen):
        """Test that agent failure is handled."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process exited
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=1)
        result = cluster.start()
        
        assert result is False
        assert cluster._running is False
    
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_stop_empty(self, mock_isdir):
        """Test stopping when no processes are running."""
        mock_isdir.return_value = True
        cluster = PX4GazeboCluster()
        cluster.stop()  # Should not raise
        
        assert len(cluster._processes) == 0
        assert cluster._running is False
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    @patch('skymeshx.simulation.px4_gazebo.sys.platform', 'linux')
    def test_stop_graceful(self, mock_isdir, mock_sleep, mock_popen):
        """Test graceful stop."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=1)
        cluster.start()
        cluster.stop()
        
        assert len(cluster._processes) == 0
        assert cluster._running is False
        # On Linux, terminate() should be called
        assert mock_proc.terminate.call_count >= 2  # Agent + SITL
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_is_running(self, mock_isdir, mock_sleep, mock_popen):
        """Test is_running status."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=1)
        
        assert cluster.is_running() is False
        
        cluster.start()
        assert cluster.is_running() is True
        
        cluster.stop()
        assert cluster.is_running() is False
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_context_manager(self, mock_isdir, mock_sleep, mock_popen):
        """Test context manager usage."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        with PX4GazeboCluster(num_drones=1) as cluster:
            assert cluster.is_running() is True
        
        # After context exit, should be stopped
        assert cluster.is_running() is False
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_context_manager_start_failure(self, mock_isdir, mock_popen):
        """Test context manager with start failure."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Fail
        mock_popen.return_value = mock_proc
        
        with pytest.raises(SimulationError, match="Failed to start"):
            with PX4GazeboCluster(num_drones=1):
                pass
    
    @patch('skymeshx.simulation.px4_gazebo.subprocess.Popen')
    @patch('skymeshx.simulation.px4_gazebo.time.sleep')
    @patch('skymeshx.simulation.px4_gazebo.os.path.isdir')
    def test_multi_drone_start(self, mock_isdir, mock_sleep, mock_popen):
        """Test starting multiple drones."""
        mock_isdir.return_value = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        cluster = PX4GazeboCluster(num_drones=3)
        result = cluster.start()
        
        assert result is True
        assert len(cluster._processes) == 4  # 1 agent + 3 SITL
        assert mock_popen.call_count == 4

