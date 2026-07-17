#!/usr/bin/env python3
"""
Benchmark tool for ROS2 bag compression algorithms.

Compares zstd, lz4, and no compression in terms of:
- File size (compression ratio)
- Recording speed (CPU usage)
- Memory usage
- Playback compatibility

Usage:
    python tools/benchmark_bag_compression.py --duration 60 --topics /fmu/out/vehicle_odometry
"""

import argparse
import subprocess
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import shutil

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False
    print("Warning: psutil not available - CPU/memory monitoring disabled")


@dataclass
class BenchmarkResult:
    """Results from a single compression benchmark."""
    compression: str
    file_size_mb: float
    duration_sec: float
    message_count: int
    cpu_percent_avg: float
    cpu_percent_max: float
    memory_mb_avg: float
    memory_mb_max: float
    compression_ratio: float  # vs uncompressed
    recording_overhead_ms: float  # time per message


class CompressionBenchmark:
    """Benchmark different bag compression algorithms."""
    
    def __init__(self, output_dir: str = "./benchmark_bags"):
        """
        Initialize benchmark.
        
        Args:
            output_dir: Directory for benchmark bag files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.results: List[BenchmarkResult] = []
        self.baseline_size_mb = 0.0  # Uncompressed size for ratio calculation
    
    def run_benchmark(
        self,
        topics: List[str],
        duration_sec: int = 30,
        compressions: List[str] = None
    ) -> List[BenchmarkResult]:
        """
        Run benchmark for all compression modes.
        
        Args:
            topics: List of ROS2 topics to record
            duration_sec: Recording duration in seconds
            compressions: List of compression modes (default: ["none", "lz4", "zstd"])
        
        Returns:
            List of BenchmarkResult objects
        """
        if compressions is None:
            compressions = ["none", "lz4", "zstd"]
        
        print(f"\n{'='*70}")
        print(f"ROS2 Bag Compression Benchmark")
        print(f"{'='*70}")
        print(f"Topics: {', '.join(topics)}")
        print(f"Duration: {duration_sec}s")
        print(f"Compressions: {', '.join(compressions)}")
        print(f"{'='*70}\n")
        
        self.results = []
        
        for compression in compressions:
            print(f"\n[{compression.upper()}] Starting benchmark...")
            result = self._benchmark_single(topics, duration_sec, compression)
            
            if result:
                self.results.append(result)
                self._print_result(result)
                
                # Store baseline for ratio calculation
                if compression == "none":
                    self.baseline_size_mb = result.file_size_mb
            else:
                print(f"[{compression.upper()}] Benchmark failed!")
            
            # Wait between benchmarks
            time.sleep(2.0)
        
        # Calculate compression ratios
        if self.baseline_size_mb > 0:
            for result in self.results:
                if result.compression != "none":
                    result.compression_ratio = self.baseline_size_mb / result.file_size_mb
        
        return self.results
    
    def _benchmark_single(
        self,
        topics: List[str],
        duration_sec: int,
        compression: str
    ) -> BenchmarkResult:
        """Run benchmark for a single compression mode."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bag_name = f"benchmark_{compression}_{timestamp}"
        bag_path = self.output_dir / bag_name
        
        # Build command
        cmd = [
            "ros2", "bag", "record",
            "-o", str(bag_path),
            "-s", compression
        ]
        cmd.extend(topics)
        
        try:
            # Start recording
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor CPU and memory
            cpu_samples = []
            memory_samples = []
            start_time = time.time()
            
            ps_process = None
            if _PSUTIL_OK:
                try:
                    ps_process = psutil.Process(process.pid)
                except Exception:
                    print(f"[{compression}] Failed to get process info")
            
            # Sample every 0.5 seconds
            while time.time() - start_time < duration_sec:
                if _PSUTIL_OK and ps_process:
                    try:
                        cpu_percent = ps_process.cpu_percent(interval=0.1)
                        memory_mb = ps_process.memory_info().rss / (1024 * 1024)
                        
                        cpu_samples.append(cpu_percent)
                        memory_samples.append(memory_mb)
                        
                        time.sleep(0.4)  # Total 0.5s with cpu_percent interval
                        
                    except Exception:
                        break
                else:
                    # No psutil, just wait
                    time.sleep(0.5)
            
            # Stop recording
            process.terminate()
            process.wait(timeout=5.0)
            
            actual_duration = time.time() - start_time
            
            # Get bag info
            file_size_mb = self._get_bag_size(bag_path)
            message_count = self._get_message_count(bag_path)
            
            # Calculate metrics
            cpu_avg = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
            cpu_max = max(cpu_samples) if cpu_samples else 0.0
            memory_avg = sum(memory_samples) / len(memory_samples) if memory_samples else 0.0
            memory_max = max(memory_samples) if memory_samples else 0.0
            
            overhead_ms = (actual_duration * 1000) / message_count if message_count > 0 else 0.0
            
            return BenchmarkResult(
                compression=compression,
                file_size_mb=file_size_mb,
                duration_sec=actual_duration,
                message_count=message_count,
                cpu_percent_avg=cpu_avg,
                cpu_percent_max=cpu_max,
                memory_mb_avg=memory_avg,
                memory_mb_max=memory_max,
                compression_ratio=1.0,  # Will be calculated later
                recording_overhead_ms=overhead_ms
            )
            
        except Exception as e:
            print(f"[{compression}] Error: {e}")
            return None
    
    def _get_bag_size(self, bag_path: Path) -> float:
        """Get total bag size in MB."""
        if not bag_path.exists():
            return 0.0
        
        total_size = 0
        for file in bag_path.rglob("*"):
            if file.is_file():
                total_size += file.stat().st_size
        
        return total_size / (1024 * 1024)
    
    def _get_message_count(self, bag_path: Path) -> int:
        """Get message count from bag info."""
        try:
            result = subprocess.run(
                ["ros2", "bag", "info", str(bag_path)],
                capture_output=True,
                text=True,
                timeout=10.0
            )
            
            if result.returncode != 0:
                return 0
            
            # Parse message count
            for line in result.stdout.split("\n"):
                if "Messages:" in line or "Message count:" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        try:
                            return int(parts[1].strip())
                        except ValueError:
                            pass
            
            return 0
            
        except Exception:
            return 0
    
    def _print_result(self, result: BenchmarkResult):
        """Print benchmark result."""
        print(f"\n  File Size:     {result.file_size_mb:.2f} MB")
        print(f"  Messages:      {result.message_count}")
        print(f"  Duration:      {result.duration_sec:.1f}s")
        print(f"  CPU (avg/max): {result.cpu_percent_avg:.1f}% / {result.cpu_percent_max:.1f}%")
        print(f"  RAM (avg/max): {result.memory_mb_avg:.1f} MB / {result.memory_mb_max:.1f} MB")
        print(f"  Overhead:      {result.recording_overhead_ms:.3f} ms/msg")
    
    def print_summary(self):
        """Print comparison summary."""
        if not self.results:
            print("\nNo results to display")
            return
        
        print(f"\n{'='*70}")
        print(f"BENCHMARK SUMMARY")
        print(f"{'='*70}\n")
        
        # Table header
        print(f"{'Compression':<12} {'Size (MB)':<12} {'Ratio':<8} {'CPU %':<10} {'RAM (MB)':<12} {'Speed':<10}")
        print(f"{'-'*70}")
        
        # Table rows
        for result in self.results:
            ratio_str = f"{result.compression_ratio:.2f}x" if result.compression_ratio > 1.0 else "-"
            print(f"{result.compression:<12} "
                  f"{result.file_size_mb:<12.2f} "
                  f"{ratio_str:<8} "
                  f"{result.cpu_percent_avg:<10.1f} "
                  f"{result.memory_mb_avg:<12.1f} "
                  f"{result.recording_overhead_ms:<10.3f}")
        
        print(f"{'-'*70}\n")
        
        # Recommendations
        self._print_recommendations()
    
    def _print_recommendations(self):
        """Print recommendations based on results."""
        if len(self.results) < 2:
            return
        
        print("RECOMMENDATIONS:")
        print("-" * 70)
        
        # Best compression
        best_compression = min(self.results, key=lambda r: r.file_size_mb if r.compression != "none" else float('inf'))
        print(f"✓ Best Compression:  {best_compression.compression.upper()} "
              f"({best_compression.compression_ratio:.2f}x smaller)")
        
        # Fastest
        fastest = min(self.results, key=lambda r: r.cpu_percent_avg)
        print(f"✓ Lowest CPU Usage:  {fastest.compression.upper()} "
              f"({fastest.cpu_percent_avg:.1f}% avg)")
        
        # Best balance
        # Score: lower is better (size * cpu_usage)
        balanced = min(self.results, 
                      key=lambda r: r.file_size_mb * r.cpu_percent_avg if r.compression != "none" else float('inf'))
        print(f"✓ Best Balance:      {balanced.compression.upper()} "
              f"(size: {balanced.file_size_mb:.1f}MB, cpu: {balanced.cpu_percent_avg:.1f}%)")
        
        print()
    
    def save_results(self, output_file: str = "benchmark_results.json"):
        """Save results to JSON file."""
        output_path = self.output_dir / output_file
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "results": [asdict(r) for r in self.results]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✓ Results saved to {output_path}")
    
    def cleanup(self, keep_results: bool = False):
        """Clean up benchmark bag files."""
        if not keep_results:
            print(f"\nCleaning up benchmark bags in {self.output_dir}...")
            shutil.rmtree(self.output_dir, ignore_errors=True)
            print("✓ Cleanup complete")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark ROS2 bag compression algorithms"
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=["/fmu/out/vehicle_odometry", "/fmu/out/vehicle_attitude"],
        help="ROS2 topics to record (default: odometry + attitude)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Recording duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--compressions",
        nargs="+",
        choices=["none", "lz4", "zstd"],
        default=["none", "lz4", "zstd"],
        help="Compression modes to test (default: all)"
    )
    parser.add_argument(
        "--output-dir",
        default="./benchmark_bags",
        help="Output directory for benchmark bags (default: ./benchmark_bags)"
    )
    parser.add_argument(
        "--keep-bags",
        action="store_true",
        help="Keep benchmark bag files after completion"
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    # Run benchmark
    benchmark = CompressionBenchmark(output_dir=args.output_dir)
    
    try:
        results = benchmark.run_benchmark(
            topics=args.topics,
            duration_sec=args.duration,
            compressions=args.compressions
        )
        
        # Print summary
        benchmark.print_summary()
        
        # Save results
        if args.save_json:
            benchmark.save_results()
        
    finally:
        # Cleanup
        benchmark.cleanup(keep_results=args.keep_bags)


if __name__ == "__main__":
    main()

