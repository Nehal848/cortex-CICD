from flask import Blueprint, render_template, request, redirect, url_for, session

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "admin":
            session["logged_in"] = True
            return redirect(url_for("dashboard.dashboard"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("dashboard.index"))
