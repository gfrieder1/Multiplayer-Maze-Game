from flask import Flask

app = Flask(__name__)

@app.route('/game')
def game():
    return "This is the game"

@app.route('/controller')
def controller():
    return "This is the controller"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)