#!/usr/bin/env python3
"""
Memory profiling tool for skymeshx GCS.

Usage:
    python tools/profile_memory.py

This script monitors memory usage of the running UI and can take snapshots
for comparison. It's a developer tool, not part of the main application.
"""
import tracemalloc
import time
import gc
from typing import Dict, List, Tuple


class MemoryProfiler:
    """Simple memory profiler for development."""
    
    def __init__(self):
        self.snapshots: Dict[str, tracemalloc.Snapshot] = {}
        self.running = False
        
    def start(self):
        """Start memory tracking."""
        if not self.running:
            tracemalloc.start()
            self.running = True
            print("[Profiler] Memory tracking started")
            
    def stop(self):
        """Stop memory tracking."""
        if self.running:
            tracemalloc.stop()
            self.running = False
            print("[Profiler] Memory tracking stopped")
            
    def snapshot(self, name: str):
        """Take a memory snapshot."""
        if not self.running:
            print("[Profiler] Not running - call start() first")
            return
            
        gc.collect()
        snapshot = tracemalloc.take_snapshot()
        self.snapshots[name] = snapshot
        current, peak = tracemalloc.get_traced_memory()
        print(f"[Profiler] Snapshot '{name}' taken: {current / 1024 / 1024:.2f} MB current, {peak / 1024 / 1024:.2f} MB peak")
        
    def compare(self, name1: str, name2: str, top_n: int = 10):
        """Compare two snapshots."""
        if name1 not in self.snapshots or name2 not in self.snapshots:
            print(f"[Profiler] Snapshot not found: {name1} or {name2}")
            return
            
        snap1 = self.snapshots[name1]
        snap2 = self.snapshots[name2]
        
        stats = snap2.compare_to(snap1, 'lineno')
        
        print(f"\n[Profiler] Comparison: {name1} → {name2}")
        print(f"Top {top_n} memory allocations:")
        print("-" * 80)
        
        for i, stat in enumerate(stats[:top_n], 1):
            frame = stat.traceback[0]
            size_diff = stat.size_diff / 1024  # KB
            count_diff = stat.count_diff
            
            print(f"{i:2d}. {frame.filename}:{frame.lineno}")
            print(f"    Size: {size_diff:+.1f} KB ({stat.size / 1024:.1f} KB total)")
            print(f"    Count: {count_diff:+d} ({stat.count} total)")
            
    def get_qt_objects(self) -> Dict[str, int]:
        """Get count of Qt objects in memory."""
        try:
            from PySide6.QtCore import QObject
            counts = {}
            for obj in gc.get_objects():
                if isinstance(obj, QObject):
                    class_name = obj.__class__.__name__
                    counts[class_name] = counts.get(class_name, 0) + 1
            return counts
        except ImportError:
            return {}
            
    def show_qt_objects(self):
        """Show current Qt object counts."""
        counts = self.get_qt_objects()
        if not counts:
            print("[Profiler] No Qt objects found (PySide6 not available?)")
            return
            
        print("\n[Profiler] Qt Object Counts:")
        print("-" * 40)
        for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {name:30s} {count:5d}")
            
    def interactive(self):
        """Run interactive profiling session."""
        print("\n" + "=" * 80)
        print("Memory Profiler - Interactive Mode")
        print("=" * 80)
        print("\nCommands:")
        print("  start          - Start memory tracking")
        print("  stop           - Stop memory tracking")
        print("  snap <name>    - Take snapshot with given name")
        print("  compare <n1> <n2> - Compare two snapshots")
        print("  list           - List all snapshots")
        print("  qt             - Show Qt object counts")
        print("  status         - Show current memory usage")
        print("  help           - Show this help")
        print("  quit           - Exit profiler")
        print()
        
        while True:
            try:
                cmd = input("profiler> ").strip().split()
                if not cmd:
                    continue
                    
                action = cmd[0].lower()
                
                if action == "quit" or action == "exit":
                    if self.running:
                        self.stop()
                    break
                    
                elif action == "start":
                    self.start()
                    
                elif action == "stop":
                    self.stop()
                    
                elif action == "snap" or action == "snapshot":
                    if len(cmd) < 2:
                        print("Usage: snap <name>")
                    else:
                        self.snapshot(cmd[1])
                        
                elif action == "compare" or action == "comp":
                    if len(cmd) < 3:
                        print("Usage: compare <name1> <name2>")
                    else:
                        self.compare(cmd[1], cmd[2])
                        
                elif action == "list" or action == "ls":
                    if not self.snapshots:
                        print("[Profiler] No snapshots taken yet")
                    else:
                        print(f"[Profiler] Snapshots ({len(self.snapshots)}):")
                        for name in self.snapshots.keys():
                            print(f"  - {name}")
                            
                elif action == "qt":
                    self.show_qt_objects()
                    
                elif action == "status":
                    if not self.running:
                        print("[Profiler] Not running")
                    else:
                        current, peak = tracemalloc.get_traced_memory()
                        print(f"[Profiler] Current: {current / 1024 / 1024:.2f} MB, Peak: {peak / 1024 / 1024:.2f} MB")
                        print(f"[Profiler] Snapshots: {len(self.snapshots)}")
                        
                elif action == "help" or action == "?":
                    print("\nCommands:")
                    print("  start, stop, snap <name>, compare <n1> <n2>")
                    print("  list, qt, status, help, quit")
                    
                else:
                    print(f"Unknown command: {action}. Type 'help' for commands.")
                    
            except KeyboardInterrupt:
                print("\n[Profiler] Use 'quit' to exit")
            except Exception as e:
                print(f"[Profiler] Error: {e}")


def main():
    """Run interactive profiler."""
    profiler = MemoryProfiler()
    
    print("\nMemory Profiler for skymeshx GCS")
    print("This is a developer tool for detecting memory leaks.")
    print("\nRecommended workflow:")
    print("  1. Start the UI in another terminal: python -m tools.ui")
    print("  2. In this profiler: start")
    print("  3. Take baseline snapshot: snap baseline")
    print("  4. Perform UI actions (open/close panels, etc.)")
    print("  5. Take another snapshot: snap after_action")
    print("  6. Compare: compare baseline after_action")
    print()
    
    profiler.interactive()


if __name__ == "__main__":
    main()

