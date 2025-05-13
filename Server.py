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
    if width % 2 == 0: width += 1
    if height % 2 == 0: height += 1

    maze = [[1 for _ in range(width)] for _ in range(height)]

    def carve_passages(x, y):
        directions = [(0, -2), (2, 0), (0, 2), (-2, 0)]
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 < nx < width and 0 < ny < height and maze[ny][nx] == 1:
                maze[ny][nx] = 0
                maze[y + dy // 2][x + dx // 2] = 0
                carve_passages(nx, ny)

    # Start carving from (1,1)
    maze[1][1] = 0
    carve_passages(1, 1)

    # Find all dead ends
    dead_ends = []
    for y in range(1, height - 1, 2):
        for x in range(1, width - 1, 2):
            if maze[y][x] == 0:
                # Count adjacent open cells
                open_neighbors = 0
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if maze[y + dy][x + dx] == 0:
                        open_neighbors += 1
                if open_neighbors == 1:
                    dead_ends.append((x, y))

    # Set start
    maze[1][1] = 2

    # Set exit to random dead end (but not the start)
    exit_candidates = [cell for cell in dead_ends if cell != (1, 1)]
    if exit_candidates:
        ex, ey = random.choice(exit_candidates)
        maze[ey][ex] = 3
        
    add_random_openings(maze, chance=0.15)

    return maze

def add_random_openings(maze, chance):
    height = len(maze)
    width = len(maze[0])
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if maze[y][x] == 1:
                # Check if it's a wall between two open path cells
                if (maze[y][x - 1] == 0 and maze[y][x + 1] == 0) or (maze[y - 1][x] == 0 and maze[y + 1][x] == 0):
                    if random.random() < chance:
                        maze[y][x] = 0

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
            maze = generate_maze(21,21)
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