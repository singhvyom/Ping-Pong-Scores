from flask import Flask, jsonify
import main

app = Flask(__name__)

@app.route("/")
def home():
    stats = main.fetch_data()
    return stats

if __name__ == "__main__":
    app.run()