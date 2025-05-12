from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, disconnect
import random
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app)

# Timer state
timer_thread = None
timer_running = False
timer_value = 0

# Maze state
maze = None

# Connected client info
client_count = 0

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

# Maze (2D array) generation function
def generate_maze(width, height):
    if width % 2 == 0:
        width += 1
    if height % 2 == 0:
        height += 1

    maze = [[1 for _ in range(width)] for _ in range(height)]

    # Track the farthest cell visited
    max_depth = [0]
    farthest = [(1, 1)]  # Default to start

    def carve_passages(x, y, depth=0):
        if depth > max_depth[0]:
            max_depth[0] = depth
            farthest[0] = (x, y)

        directions = [(0, -2), (2, 0), (0, 2), (-2, 0)]
        random.shuffle(directions)

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 < nx < width and 0 < ny < height and maze[ny][nx] == 1:
                maze[ny][nx] = 0
                maze[y + dy // 2][x + dx // 2] = 0
                carve_passages(nx, ny, depth + 1)

    # Start at 1,1
    maze[1][1] = 0
    carve_passages(1, 1)

    # Mark start and exit
    sx, sy = 1, 1
    ex, ey = farthest[0]
    maze[sy][sx] = 2  # Start
    maze[ey][ex] = 3  # Exit

    return maze

@app.route('/game')
def game():
    return render_template_string("""
        <html>
        <head>
            <style>
                table { border-collapse: collapse; }
                td {
                    width: 20px;
                    height: 20px;
                    border: 1px solid black;
                }
                .wall {
                    background-color: black;
                }
                .player {
                    background-color: green;
                }
                .exit {
                    background-color: red;
                }
            </style>
        </head>
        <body>
            <h1>This is the game</h1>
            <p>Timer: <span id="timer">...</span> seconds</p>
            <div id="maze_container"></div>

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

                socket.on('maze_data', data => {
                    const maze = data.maze;
                    const container = document.getElementById('maze_container');
                    const table = document.createElement('table');

                    maze.forEach(row => {
                        const tr = document.createElement('tr');
                        row.forEach(cell => {
                            const td = document.createElement('td');
                            if (cell === 1) td.classList.add('wall');
                            else if (cell === 2) td.classList.add('player');
                            else if (cell === 3) td.classList.add('exit');
                            tr.appendChild(td);
                        });
                        table.appendChild(tr);
                    });

                    container.appendChild(table);
                });
            </script>
        </body>
        </html>
    """)

@socketio.on('connect')
def handle_connect():
    global timer_running, timer_thread, timer_value, client_count, maze
    with lock:
        client_count += 1
        print(f"Client connected. Total clients: {client_count}")
        if not timer_running:
            # Start a game session!
            timer_running = True
            timer_value = 0
            # Generate a maze
            maze = generate_maze(31,31)
        # Send maze to client
        emit('maze_data', {'maze': maze})

@socketio.on('disconnect')
def handle_disconnect():
    global timer_running, client_count
    with lock:
        client_count -= 1
        print(f"Client disconnected. Total clients: {client_count}")
        if client_count <= 0: # Should never be negative
            timer_running = False
            timer_value = 0
            maze = None

@app.route('/controller')
def controller():
    return "This is the controller"

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)