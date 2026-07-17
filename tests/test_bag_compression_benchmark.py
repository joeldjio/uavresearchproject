"""
Tests for bag compression benchmark tool.

Tests the benchmark functionality without requiring actual ROS2 recording.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import os

# Add tools/analysis directory to path (file moved from tools/ to tools/analysis/)
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "analysis"))

from benchmark_bag_compression import CompressionBenchmark, BenchmarkResult


def test_benchmark_result_dataclass():
    """Test BenchmarkResult dataclass."""
    result = BenchmarkResult(
        compression="zstd",
        file_size_mb=10.5,
        duration_sec=30.0,
        message_count=1000,
        cpu_percent_avg=15.5,
        cpu_percent_max=25.0,
        memory_mb_avg=50.0,
        memory_mb_max=75.0,
        compression_ratio=2.5,
        recording_overhead_ms=0.030
    )
    
    assert result.compression == "zstd"
    assert result.file_size_mb == 10.5
    assert result.compression_ratio == 2.5


def test_compression_benchmark_init(tmp_path):
    """Test CompressionBenchmark initialization."""
    output_dir = tmp_path / "test_bags"
    benchmark = CompressionBenchmark(output_dir=str(output_dir))
    
    assert benchmark.output_dir == output_dir
    assert output_dir.exists()
    assert benchmark.results == []
    assert benchmark.baseline_size_mb == 0.0


def test_get_bag_size(tmp_path):
    """Test _get_bag_size method."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    # Create fake bag directory with files
    bag_dir = tmp_path / "test_bag"
    bag_dir.mkdir()
    
    # Create some files
    (bag_dir / "metadata.yaml").write_text("test")
    (bag_dir / "data.db3").write_bytes(b"x" * 1024 * 1024)  # 1 MB
    
    size_mb = benchmark._get_bag_size(bag_dir)
    
    assert size_mb > 0.9  # Should be close to 1 MB
    assert size_mb < 1.1


def test_get_bag_size_nonexistent(tmp_path):
    """Test _get_bag_size with nonexistent bag."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    size_mb = benchmark._get_bag_size(tmp_path / "nonexistent")
    
    assert size_mb == 0.0


@patch('subprocess.run')
def test_get_message_count(mock_run, tmp_path):
    """Test _get_message_count method."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    # Mock ros2 bag info output
    mock_run.return_value = Mock(
        returncode=0,
        stdout="Duration: 30.5s\nMessages: 1500\nTopics: /test"
    )
    
    count = benchmark._get_message_count(tmp_path / "test_bag")
    
    assert count == 1500
    mock_run.assert_called_once()


@patch('subprocess.run')
def test_get_message_count_error(mock_run, tmp_path):
    """Test _get_message_count with error."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    mock_run.return_value = Mock(returncode=1, stdout="")
    
    count = benchmark._get_message_count(tmp_path / "test_bag")
    
    assert count == 0


def test_print_result(tmp_path, capsys):
    """Test _print_result method."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    result = BenchmarkResult(
        compression="zstd",
        file_size_mb=10.5,
        duration_sec=30.0,
        message_count=1000,
        cpu_percent_avg=15.5,
        cpu_percent_max=25.0,
        memory_mb_avg=50.0,
        memory_mb_max=75.0,
        compression_ratio=2.5,
        recording_overhead_ms=0.030
    )
    
    benchmark._print_result(result)
    
    captured = capsys.readouterr()
    assert "10.50 MB" in captured.out
    assert "1000" in captured.out
    assert "15.5%" in captured.out


def test_print_summary_no_results(tmp_path, capsys):
    """Test print_summary with no results."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    benchmark.print_summary()
    
    captured = capsys.readouterr()
    assert "No results" in captured.out


def test_print_summary_with_results(tmp_path, capsys):
    """Test print_summary with results."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    benchmark.results = [
        BenchmarkResult(
            compression="none",
            file_size_mb=50.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=10.0,
            cpu_percent_max=15.0,
            memory_mb_avg=40.0,
            memory_mb_max=50.0,
            compression_ratio=1.0,
            recording_overhead_ms=0.030
        ),
        BenchmarkResult(
            compression="zstd",
            file_size_mb=20.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=15.0,
            cpu_percent_max=25.0,
            memory_mb_avg=50.0,
            memory_mb_max=75.0,
            compression_ratio=2.5,
            recording_overhead_ms=0.030
        ),
        BenchmarkResult(
            compression="lz4",
            file_size_mb=30.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=12.0,
            cpu_percent_max=20.0,
            memory_mb_avg=45.0,
            memory_mb_max=60.0,
            compression_ratio=1.67,
            recording_overhead_ms=0.030
        ),
    ]
    
    benchmark.print_summary()
    
    captured = capsys.readouterr()
    assert "BENCHMARK SUMMARY" in captured.out
    assert "zstd" in captured.out
    assert "lz4" in captured.out
    assert "none" in captured.out
    assert "RECOMMENDATIONS" in captured.out
    assert "Best Compression" in captured.out


def test_save_results(tmp_path):
    """Test save_results method."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    
    benchmark.results = [
        BenchmarkResult(
            compression="zstd",
            file_size_mb=20.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=15.0,
            cpu_percent_max=25.0,
            memory_mb_avg=50.0,
            memory_mb_max=75.0,
            compression_ratio=2.5,
            recording_overhead_ms=0.030
        )
    ]
    
    benchmark.save_results("test_results.json")
    
    result_file = tmp_path / "test_results.json"
    assert result_file.exists()
    
    import json
    with open(result_file) as f:
        data = json.load(f)
    
    assert "timestamp" in data
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["compression"] == "zstd"


def test_cleanup_with_keep(tmp_path):
    """Test cleanup with keep_results=True."""
    output_dir = tmp_path / "test_bags"
    output_dir.mkdir()
    (output_dir / "test_file.txt").write_text("test")
    
    benchmark = CompressionBenchmark(output_dir=str(output_dir))
    benchmark.cleanup(keep_results=True)
    
    assert output_dir.exists()


def test_cleanup_without_keep(tmp_path):
    """Test cleanup with keep_results=False."""
    output_dir = tmp_path / "test_bags"
    output_dir.mkdir()
    (output_dir / "test_file.txt").write_text("test")
    
    benchmark = CompressionBenchmark(output_dir=str(output_dir))
    benchmark.cleanup(keep_results=False)
    
    assert not output_dir.exists()


def test_recommendations_best_compression(tmp_path):
    """Test recommendations identify best compression."""
    benchmark = CompressionBenchmark(output_dir=str(tmp_path))
    benchmark.baseline_size_mb = 100.0
    
    benchmark.results = [
        BenchmarkResult(
            compression="none",
            file_size_mb=100.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=10.0,
            cpu_percent_max=15.0,
            memory_mb_avg=40.0,
            memory_mb_max=50.0,
            compression_ratio=1.0,
            recording_overhead_ms=0.030
        ),
        BenchmarkResult(
            compression="zstd",
            file_size_mb=25.0,  # Best compression
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=20.0,
            cpu_percent_max=30.0,
            memory_mb_avg=60.0,
            memory_mb_max=80.0,
            compression_ratio=4.0,
            recording_overhead_ms=0.030
        ),
        BenchmarkResult(
            compression="lz4",
            file_size_mb=40.0,
            duration_sec=30.0,
            message_count=1000,
            cpu_percent_avg=12.0,  # Lowest CPU
            cpu_percent_max=18.0,
            memory_mb_avg=45.0,
            memory_mb_max=55.0,
            compression_ratio=2.5,
            recording_overhead_ms=0.030
        ),
    ]
    
    # Find best compression (smallest file, excluding "none")
    best = min([r for r in benchmark.results if r.compression != "none"], 
               key=lambda r: r.file_size_mb)
    assert best.compression == "zstd"
    
    # Find lowest CPU
    fastest = min(benchmark.results, key=lambda r: r.cpu_percent_avg)
    assert fastest.compression == "none"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

