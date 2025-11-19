#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Provides performance profiling decorators and context managers.
Requires the 'psutil' package.
"""

import functools
import logging
import os
import time
from typing import Any, Callable, ParamSpec, TypeVar

import psutil

logger = logging.getLogger(__name__)

# Type variables for precise decorator typing
P = ParamSpec("P")
R = TypeVar("R")

try:
    _process = psutil.Process(os.getpid())
    PSUTIL_AVAILABLE = True
except (ImportError, psutil.NoSuchProcess):
    PSUTIL_AVAILABLE = False
    _process = None
    logger.warning(
        "psutil not found or process not found. Performance logging will be limited to time only."
    )


def _format_bytes(b: int) -> str:
    """Helper function to format bytes into a readable string (KB, MB, GB)."""
    try:
        if abs(b) < 1024:
            return f"{b} B"
        elif abs(b) < 1024**2:
            return f"{b / 1024:.2f} KB"
        elif abs(b) < 1024**3:
            return f"{b / 1024**2:.2f} MB"
        else:
            return f"{b / 1024**3:.2f} GB"
    except Exception:
        return "N/A"


def log_performance(func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to log wall time, CPU time, and memory usage of a function.
    Logs at DEBUG level.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # 1. Get "before" stats
        mem_before = 0
        cpu_before = None
        if PSUTIL_AVAILABLE and _process:
            try:
                mem_before = _process.memory_info().rss
                cpu_before = _process.cpu_times()
            except psutil.Error as e:
                logger.warning(f"psutil error before {func.__name__}: {e}")

        start_time = time.perf_counter()

        # 2. Run the function
        result = func(*args, **kwargs)

        # 3. Get "after" stats
        end_time = time.perf_counter()
        mem_after = 0
        cpu_after = None
        if PSUTIL_AVAILABLE and _process:
            try:
                mem_after = _process.memory_info().rss
                cpu_after = _process.cpu_times()
            except psutil.Error as e:
                logger.warning(f"psutil error after {func.__name__}: {e}")

        # 4. Calculate deltas
        wall_elapsed = end_time - start_time

        cpu_elapsed_str = "N/A"
        mem_after_str = "N/A"
        mem_delta_str = "N/A"

        if PSUTIL_AVAILABLE and cpu_before is not None and cpu_after is not None:
            cpu_elapsed = (cpu_after.user - cpu_before.user) + (
                cpu_after.system - cpu_before.system
            )
            cpu_elapsed_str = f"{cpu_elapsed:.4f}s (CPU)"

        if PSUTIL_AVAILABLE and mem_after > 0:
            mem_delta = mem_after - mem_before
            mem_after_str = _format_bytes(mem_after)
            mem_delta_str = _format_bytes(mem_delta)

        # 5. Log the result
        logger.debug(
            f"PERF: {func.__name__} | "
            f"Time: {wall_elapsed:.4f}s (Wall), {cpu_elapsed_str} | "
            f"Mem: {mem_after_str} (RSS), Delta: {mem_delta_str}"
        )

        return result

    return wrapper
