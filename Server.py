from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, disconnect
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app)

# Timer state
timer_thread = None
timer_running = False
timer_value = 0

# Connected client info
game_client_count = 0

# Lock for thread safety
lock = threading.Lock()

# Define background timer thread
def background_timer():
    global timer_value
    while True:
        time.sleep(1)
        with lock:
            if timer_running:
                timer_value += 1
                socketio.emit('timer_update', {'time': timer_value})                
# Start background thread once
threading.Thread(target=background_timer, daemon=True).start()

@app.route('/game')
def game():
    return render_template_string("""
        <h1>This is the game</h1>
        <p>Timer: <span id="timer">...</span> seconds</p>
        <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
        <script>
            const socket = io();
            socket.on('connect', () => {
                console.log('Connected to server');
            });

            socket.on('disconnect', () => {
                console.log('Disconnected from server');
            });

            socket.on('timer_update', data => {
                document.getElementById('timer').innerText = data.time;
            });
        </script>
    """)

@socketio.on('connect')
def handle_connect():
    global timer_running, timer_thread, timer_value, game_client_count
    with lock:
        game_client_count += 1
        print(f"Client connected to /game. Total game clients: {game_client_count}")
        if not timer_running:
            timer_running = True
            timer_value = 0

@socketio.on('disconnect')
def handle_disconnect():
    global timer_running, game_client_count
    with lock:
        game_client_count -= 1
        print(f"Client disconnected. Total clients: {game_client_count}")
        if game_client_count <= 0: # Should never be negative
            timer_running = False
            timer_value = 0

@app.route('/controller')
def controller():
    return "This is the controller"

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)