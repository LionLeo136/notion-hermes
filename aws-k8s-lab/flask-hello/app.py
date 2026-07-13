from flask import Flask

app = Flask(__name__)

@app.route("/", methods=["GET"])
def hello():
    return "hello world!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)   # 0.0.0.0 để nhận từ ngoài container
