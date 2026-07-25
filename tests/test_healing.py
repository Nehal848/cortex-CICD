import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.healing.engine import HealingEngine
from app.healing.strategies import _STRATEGY_MAP

class MockDB:
    def commit(self): pass

class MockHealingEvent:
    def __init__(self, **kwargs): pass

class MockPipelineRun:
    @staticmethod
    def query():
        pass # mock

def test_strategy_mapping():
    """Verify that failure types map to the correct healing strategies."""
    from app.healing.strategies import choose_strategy
    
    # Test correct mapping for known types
    assert choose_strategy("OOM — Pod Evicted").__class__.__name__ == "PodRestartStrategy"
    assert choose_strategy("High CPU Saturation").__class__.__name__ == "ScaleUpStrategy"
    assert choose_strategy("Dependency Resolution").__class__.__name__ == "RollbackStrategy"
    assert choose_strategy("Test Suite Timeout").__class__.__name__ == "AutoRetryStrategy"
    
    # Test default fallback mapping
    assert choose_strategy("Unknown Failure Type").__class__.__name__ == "RollbackStrategy"
