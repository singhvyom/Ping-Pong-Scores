from flask import Flask, jsonify
from flask_cors import CORS
import main

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    stats = main.fetch_data()
    return jsonify(stats)

if __name__ == "__main__":
    app.run()