from flask import Flask, jsonify
import main

app = Flask(__name__)

@app.route("/")
def fetch_data():
    stats = main.fetch_data()
    return jsonify(stats)

if __name__ == "__main__":
    app.run()