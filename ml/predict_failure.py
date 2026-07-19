import random

def predict_failure_risk(repo: str, branch: str, files_changed: int) -> int:
    """
    Predicts the risk of a CI/CD pipeline failure (0-100).
    In a real system, this would load a PyTorch or Scikit-Learn model
    trained on historical build logs and git diffs.
    """
    # Heuristic baseline
    base_risk = 10
    
    if "main" not in branch and "master" not in branch:
        base_risk += 15
        
    if files_changed > 50:
        base_risk += 40
    elif files_changed > 10:
        base_risk += 20
        
    # Add model variance
    final_risk = base_risk + random.randint(-5, 15)
    
    # Clamp to 0-100
    return max(0, min(100, final_risk))

if __name__ == "__main__":
    print(f"Risk Score: {predict_failure_risk('cortex/api', 'feature/auth', 12)}")
