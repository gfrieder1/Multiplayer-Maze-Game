from flask import Flask, render_template, render_template_string, request
from flask_socketio import SocketIO, emit, disconnect
import logging
import random
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app)

# Logging config
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Timer state
timer_thread = None
timer_running = False
timer_value = 0

# Maze state
maze = None
player_x = None
player_y = None

# Connected client info
controller_count = 0

# Lock for thread safety
lock = threading.Lock()

# Vote system
allowed_votes = ['Up', 'Left', 'Stop', 'Right', 'Down']
votes = {}

# Define background timer thread
def background_timer():
    global timer_running, timer_value, votes, maze
    while True:
        time.sleep(1)
        with lock:
            if timer_running:
                timer_value += 1
                socketio.emit('timer_update', {'time': timer_value}, namespace='/game')
                # Timer update!
                print(f"\n[Server] Current votes: {votes}")
                process_votes()
                socketio.emit('maze_data', {'maze': maze}, namespace='/game')
# Start background thread once
threading.Thread(target=background_timer, daemon=True).start()

# Maze (2D array) generation function
def generate_maze(width, height):
    global maze, player_x, player_y

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
    player_x, player_y = 1, 1

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

def process_votes():
    global maze, votes
    if not maze:
        return

    # Count votes
    vote_counts = {direction: 0 for direction in allowed_votes}
    for vote in votes.values():
        if vote['direction'] in allowed_votes:
            vote_counts[vote['direction']] += 1

    # Determine the most voted direction
    max_votes = max(vote_counts.values())
    most_voted = [direction for direction, count in vote_counts.items() if count == max_votes and max_votes > 0]

    if most_voted:
        if len(most_voted) == 1:
            chosen_direction = most_voted[0]
        else:
            chosen_direction = 'Stop'
        print(f"[Server] Chosen direction: {chosen_direction}")
        # Here you can implement logic to move the player or change the maze based on the chosen direction
        move_player(chosen_direction)
        
def move_player(direction):
    global player_x, player_y, maze

    print(f"[Server] Moving player in direction: {direction}")
    
    # Implement player movement logic based on the direction
    if direction == 'Stop':
        return
    elif direction == 'Up':
        new_x, new_y = player_x, player_y - 1
    elif direction == 'Down':
        new_x, new_y = player_x, player_y + 1
    elif direction == 'Left':
        new_x, new_y = player_x - 1, player_y
    elif direction == 'Right':
        new_x, new_y = player_x + 1, player_y
    
    # Check if the new position is valid
    if maze[new_y][new_x] == 0 or maze[new_y][new_x] == 3:
        maze[player_y][player_x] = 0  # Clear old position
        maze[new_y][new_x] = 2  # Set new position
        player_x, player_y = new_x, new_y
        print(f"[Server] Player moved to ({player_x}, {player_y})")

@app.route('/game')
def game():
    return render_template('Game.html')

@app.route('/controller')
def controller():
    return render_template('Controller.html')

@socketio.on('connect', namespace='/game')
def handle_game_connect():
    global timer_running, timer_thread, timer_value, maze, authorized_game_sid
    with lock:
        print(f"[Server] Game client connected.")
        if not timer_running:
            # Start a game session!
            timer_running = True
            timer_value = 0
            # Generate a maze
            maze = generate_maze(21,21)
        # Send maze to game client
        socketio.emit('maze_data', {'maze': maze}, namespace='/game')

@socketio.on('connect', namespace='/controller')
def handle_controller_connect():
    global controller_count
    with lock:
        controller_count += 1
        print(f"Controller connected. Total clients: {controller_count}")
        # Initialize votes for this controller
        votes[request.sid] = {'direction': None}

@socketio.on('disconnect', namespace='/game')
def handle_game_disconnect():
    print(f"[Server] Game client disconnected.")

@socketio.on('disconnect', namespace='/controller')
def handle_controller_disconnect():
    global controller_count
    with lock:
        controller_count -= 1
        print(f"Controller disconnected. Total clients: {controller_count}")
        votes.pop(request.sid, None)

@socketio.on('vote', namespace='/controller')
def handle_vote(data):
    direction = data.get('direction')
    print(f"[Server] Vote received: {direction}")
    if direction in allowed_votes:
        with lock:
            votes[request.sid]['direction'] = direction
            # Broadcast updated votes to all clients
            socketio.emit('vote_data', {'votes': votes}, namespace='/controller')
            socketio.emit('vote_data', {'votes': votes}, namespace='/game')
    else:
        print(f"[Server] Invalid vote: {direction}")

@socketio.on('reset_game', namespace='/game')
def handle_reset_game():
    global maze, timer_value, timer_running

    with lock:
        print("[Server] Resetting game...")
        maze = generate_maze(21, 21)
        timer_value = 0
        timer_running = True

        # Broadcast updates to all /game clients
        socketio.emit('maze_data', {'maze': maze}, namespace='/game')
        socketio.emit('timer_update', {'time': timer_value}, namespace='/game')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)