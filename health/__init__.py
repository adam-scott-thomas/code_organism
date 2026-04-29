# SPDX-License-Identifier: Apache-2.0
"""
Code Organism Health Diagnostics

Analyze code health and detect problematic patterns.
"""

from .complexity import (
    ComplexityAnalyzer,
    analyze_complexity,
)
from .malware import (
    MalwareAnalyzer,
    MalwareMarker,
    MalwareSeverity,
    analyze_for_malware,
)
from .patterns import (
    Pattern,
    PatternDetector,
    PatternSeverity,
    detect_patterns,
)

__all__ = [
    # Patterns
    "PatternDetector",
    "Pattern",
    "PatternSeverity",
    "detect_patterns",
    # Malware
    "MalwareMarker",
    "MalwareAnalyzer",
    "MalwareSeverity",
    "analyze_for_malware",
    # Complexity
    "ComplexityAnalyzer",
    "analyze_complexity",
]
