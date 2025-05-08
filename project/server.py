"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.

TODO: For Tier 1, item 1, you don't need to modify this file much.
The core issue is in how the client handles incoming messages.
However, if you want to support multiple clients (i.e. progress through further Tiers), you'll need concurrency here too.
"""

import socket, threading, time

from matplotlib.pyplot import disconnect

from battleship import run_two_player_game, Board, BOARD_SIZE

HOST = '127.0.0.1'
PORT = 5000
active_players = []  # active players list
spectators = []      # spectators list
players_lock = threading.Lock()  # lock for active_players and spectators
player_sessions = {}  # {username: {"conn": conn, "board": Board, "opponent_board": Board, "game_state": str}}
disconnected = {}  # {username: {"conn": conn, "board": Board, "opponent_board": Board, "game_state": str, "disconnect_time": float}}
sessions_lock = threading.Lock()

def recv(rfile):
    line = rfile.readline().strip()
    if not line:  # if client disconnected, raise an exception
        raise ConnectionError("Client disconnected")
    return line

def send(wfile, msg):
    wfile.write(msg + '\n')
    wfile.flush()


def handle_two_player_game(player1_conn, player2_conn):
    global spectators
    game_restart_event = threading.Event()
    wfile1 = player1_conn.makefile('w')
    wfile2 = player2_conn.makefile('w')
    rfile1 = player1_conn.makefile('r')
    rfile2 = player2_conn.makefile('r')

    def game_session():
        nonlocal player1_conn, player2_conn
        try:
            with sessions_lock:
                p1_name = [k for k, v in player_sessions.items() if v == player1_conn][0]
                p2_name = [k for k, v in player_sessions.items() if v == player2_conn][0]

                # init the board for each player(or reconnect)
                board1 = None
                board2 = None
                if p1_name in disconnected:
                    board1 = disconnected[p1_name]["board"]
                    print(board1)
                if p2_name in disconnected:
                    board2 = disconnected[p2_name]["board"]
                    print(board1)

                # clear the disconnected state
                if p1_name in disconnected: del disconnected[p1_name]
                if p2_name in disconnected: del disconnected[p2_name]

            while not game_restart_event.is_set():
                try:
                    with (player1_conn, player2_conn):
                        run_two_player_game(rfile1, wfile1, rfile2, wfile2, spectators, board1, board2)

                        # ask players if they want to play again
                        send(wfile1, "GAME_OVER Play again? (Y/N)")
                        send(wfile2, "GAME_OVER Play again? (Y/N)")
                        response1 = recv(rfile1).strip().upper()
                        response2 = recv(rfile2).strip().upper()

                        if response1 != 'Y' or response2 != 'Y':
                            break

                        # init the game state
                        board1 = Board(BOARD_SIZE)
                        board2 = Board(BOARD_SIZE)

                except (ConnectionResetError, BrokenPipeError) as e:
                    print(f"[INFO] connected error: {e}")
                    # save the disconnected state
                    with sessions_lock:
                        for name in [p1_name, p2_name]:
                            disconnected[name] = {
                                "conn": player_sessions[name],
                                "board": board1 if name == p1_name else board2,
                                "opponent_board": board2 if name == p1_name else board1,
                                "disconnect_time": time.time(),
                                "game_state": "IN_PROGRESS"
                            }
                    print(board1)
                    print(board2)
                    break

        finally:
            # clear the game state
            with players_lock:
                try:
                    active_players.remove(player1_conn)
                    active_players.remove(player2_conn)
                except ValueError:
                    pass

                # spectators list
                new_players = []
                while len(active_players) < 2 and spectators:
                    spectator_conn = spectators.pop(0)
                    try:
                        wfile = spectator_conn.makefile('w')
                        wfile.write("PING\n")
                        wfile.flush()
                        active_players.append(spectator_conn)
                        new_players.append(spectator_conn)
                        send(wfile, "ROLE PLAYER")
                        print(f"[INFO] the spectator promote to player: {spectator_conn.getpeername()}")
                    except (ConnectionResetError, BrokenPipeError):
                        continue

                if len(new_players) == 2:
                    game_restart_event.set()
                    threading.Thread(
                        target=handle_two_player_game,
                        args=(new_players[0], new_players[1])
                    ).start()

    # start the game session in a separate thread
    game_thread = threading.Thread(target=game_session)
    game_thread.start()

    # # connection monitor
    # def connection_monitor():
    #     while game_thread.is_alive():
    #         time.sleep(1)
    #         try:
    #             player1_conn.send(b'')
    #             player2_conn.send(b'')
    #         except (BrokenPipeError, ConnectionResetError):
    #             game_thread.join(0.1)
    #             break
    #
    # monitor_thread = threading.Thread(target=connection_monitor)
    # monitor_thread.start()

def handle_client(conn, addr):
    global active_players, spectators, players_lock, disconnected
    print(f"[INFO] Client connected from {addr}")

    try:
        rfile = conn.makefile('r')
        wfile = conn.makefile('w')
        first_line = rfile.readline().strip()

        if not first_line.startswith("USER "):
            conn.close()
            return

        username = first_line.split(" ", 1)[1]

        with sessions_lock:
            # check if username already exists
            if username in disconnected:
                entry = disconnected[username]
                if time.time() - entry["disconnect_time"] <= 60:
                    print(f"[INFO] {username} reconnected")
                    # close the old connection
                    try:
                        entry["conn"].close()
                    except:
                        pass
                    # update the player_sessions
                    player_sessions[username] = conn

                    # reactivate the player
                    with players_lock:
                        active_players.append(conn)
                        if len(active_players) == 2:
                            p1, p2 = active_players
                            threading.Thread(target=handle_two_player_game, args=(p1, p2)).start()
                    return
                else:
                    del disconnected[username]

            player_sessions[username] = conn
            print(f"[INFO] A new player: {username}")

        with players_lock:
            if len(active_players) < 2:
                active_players.append(conn)
                wfile = conn.makefile('w')
                wfile.write("ROLE PLAYER\n")
                wfile.flush()
                print("[INFO] Player added to active players list")
                # check if we have two players
                if len(active_players) == 2:
                    player1, player2 = active_players
                    game_thread = threading.Thread(target=handle_two_player_game, args=(player1, player2))
                    game_thread.start()
            else:
                spectators.append(conn)
                wfile = conn.makefile('w')
                wfile.write("ROLE SPECTATOR\n")
                wfile.flush()
                print("[INFO] Client added to spectators list")
    except Exception as e:
        print(f"[ERROR] error in client handling: {e}")
        conn.close()

def cleanup_disconnected():
    """clear disconnected players after 60 seconds"""
    while True:
        with sessions_lock:
            now = time.time()
            to_del = [k for k,v in disconnected.items() if now - v["disconnect_time"] > 60]
            for k in to_del:
                print(f"[INFO] clear the disconnected player: {k}")
                del disconnected[k]
        time.sleep(10)

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)

        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.start()

# HINT: For multiple clients, you'd need to:
# 1. Accept connections in a loop
# 2. Handle each client in a separate thread
# 3. Import threading and create a handle_client function

if __name__ == "__main__":
    main()