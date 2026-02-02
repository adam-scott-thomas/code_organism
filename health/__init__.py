"""
Code Organism Health Diagnostics

Analyze code health and detect problematic patterns.
"""

from .patterns import (
    PatternDetector,
    Pattern,
    PatternSeverity,
    detect_patterns,
)

from .malware import (
    MalwareMarker,
    MalwareAnalyzer,
    MalwareSeverity,
    analyze_for_malware,
)

from .complexity import (
    ComplexityAnalyzer,
    analyze_complexity,
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
