from flask import Flask, jsonify
from flask_cors import CORS
from main import fetch_data

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return jsonify(fetch_data())

if __name__ == "__main__":
    app.run()