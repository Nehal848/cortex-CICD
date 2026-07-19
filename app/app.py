import os
from flask import Flask
from routes import main_bp

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Register routes blueprint
app.register_blueprint(main_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)