from flask import render_template, request, jsonify, redirect, url_for, session
from . import main_bp

# Mock pipeline data
mock_runs = [
    {"id": "RUN-4819", "repo": "CortexCICD/Self-Healing-CI-CD", "branch": "main", "status": "Success", "triggered_by": "GitPush", "timestamp": "10 mins ago"},
    {"id": "RUN-4818", "repo": "CortexCICD/Self-Healing-CI-CD", "branch": "main", "status": "Healed", "triggered_by": "GitPush", "timestamp": "1 hr ago"},
    {"id": "RUN-4817", "repo": "CortexCICD/Self-Healing-CI-CD", "branch": "feature/ui-update", "status": "Success", "triggered_by": "Manual", "timestamp": "3 hrs ago"},
    {"id": "RUN-4816", "repo": "CortexCICD/Self-Healing-CI-CD", "branch": "main", "status": "Failed", "triggered_by": "GitPush", "timestamp": "5 hrs ago"},
]

@main_bp.route("/")
def index():
    return render_template("index.html")

@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Simple mock credentials checking
        if username == "admin" and password == "admin":
            session["logged_in"] = True
            return redirect(url_for("main.dashboard"))
        else:
            return render_template("login.html", error="Invalid username or password")
            
    return render_template("login.html")

@main_bp.route("/dashboard")
def dashboard():
    # Allow bypass for development/testing, but check session
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("dashboard.html", runs=mock_runs)

@main_bp.route("/self-healing")
def self_healing():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("self_healing.html")

@main_bp.route("/deployments")
def deployments():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("deployments.html")

@main_bp.route("/pipeline")
def pipeline():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("pipeline.html")

@main_bp.route("/kubernetes")
def kubernetes():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("kubernetes.html")

@main_bp.route("/monitoring")
def monitoring():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("monitoring.html")

@main_bp.route("/logs")
def logs():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("logs.html")

@main_bp.route("/prediction")
def prediction():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("prediction.html")

@main_bp.route("/alerts")
def alerts():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("alerts.html")

@main_bp.route("/settings")
def settings():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return render_template("settings.html")

@main_bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("main.index"))

@main_bp.route("/api/pipeline/run", methods=["POST"])
def run_pipeline():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    # Return mock response representing pipeline run init
    return jsonify({
        "success": True,
        "message": "Pipeline run triggered successfully.",
        "run": {
            "id": "RUN-4820",
            "repo": "CortexCICD/Self-Healing-CI-CD",
            "branch": "main",
            "status": "In Progress",
            "triggered_by": "Manual",
            "timestamp": "Just now"
        }
    })
