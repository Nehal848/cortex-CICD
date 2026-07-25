import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ml.predict_failure import predict_failure_risk, _RECOMMENDED_ACTIONS, _confidence_label

def test_predict_failure_risk_format():
    """Verify the ML prediction function returns the expected rich output format."""
    result = predict_failure_risk("CortexCICD/main", "main", 10, 120)
    
    assert "risk_score" in result
    assert "failure_type" in result
    assert "confidence" in result
    assert "confidence_label" in result
    assert "recommended_action" in result
    assert "alternative_action" in result
    
    # Ensure confidence label maps correctly
    assert _confidence_label(0.95) == "Very High"
    assert _confidence_label(0.80) == "High"
    assert _confidence_label(0.60) == "Medium"
    assert _confidence_label(0.40) == "Low"

def test_predict_heuristic_fallback():
    """Verify the heuristic fallback behaves predictably."""
    # A branch not named main/master with high file changes should have higher risk
    result1 = predict_failure_risk("CortexCICD/feature-x", "feature-x", 80, 120)
    assert result1["model"] == "heuristic" or result1["model"] == "RandomForest"
    
    if result1["model"] == "heuristic":
        # Risk should be elevated due to feature branch and many files
        assert result1["risk_score"] > 50
        assert result1["failure_type"] != "None"
