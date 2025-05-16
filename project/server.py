"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.

TODO: For Tier 1, item 1, you don't need to modify this file much.
The core issue is in how the client handles incoming messages.
However, if you want to support multiple clients (i.e. progress through further Tiers), you'll need concurrency here too.
"""

import queue
import socket, threading, time, protocol

from matplotlib.pyplot import disconnect
from protocol import sessions
from battleship import run_two_player_game, Board, BOARD_SIZE, ClientSession

HOST = "127.0.0.1"
PORT = 5000
active_players = []  # active players list
spectators = []  # spectators list
players_lock = threading.Lock()  # lock for active_players and spectators
player_sessions = (
    {}
)  # {username: {"conn": conn, "board": Board, "opponent_board": Board, "game_state": str}}
disconnected = (
    {}
)  # {username: {"conn": conn, "board": Board, "opponent_board": Board, "game_state": str, "disconnect_time": float}}
sessions_lock = threading.Lock()


def broadcast_message(sender_conn, message: str):
    """broadcast message to all clients except the sender"""
    with sessions_lock:
        for conn in list(sessions.keys()):
            try:
                session = sessions[conn]
                if conn != sender_conn:
                    session.send(f"{message}", ptype=protocol.PacketType.CHAT)
            except Exception as e:
                print(f"[ERROR] CHATTING SENDING ERROR: {e}")


def handle_two_player_game(player1_conn, player2_conn):
    global spectators, current_player
    game_restart_event = threading.Event()
    session1 = sessions[player1_conn]
    session2 = sessions[player2_conn]

    def game_session():
        nonlocal player1_conn, player2_conn
        try:
            with sessions_lock:
                p1_name = [k for k, v in player_sessions.items() if v == player1_conn][
                    0
                ]
                p2_name = [k for k, v in player_sessions.items() if v == player2_conn][
                    0
                ]

                # init the board for each player(or reconnect)
                board1 = Board(BOARD_SIZE)
                board2 = Board(BOARD_SIZE)
                init_current_player = 1
                if p1_name in disconnected:
                    board1 = disconnected[p1_name]["board"]
                    init_current_player = disconnected[p1_name].get("current_player", 1)
                if p2_name in disconnected:
                    board2 = disconnected[p2_name]["board"]
                    init_current_player = disconnected[p2_name].get("current_player", 2)

                # clear the disconnected state
                if p1_name in disconnected:
                    del disconnected[p1_name]
                if p2_name in disconnected:
                    del disconnected[p2_name]

            while not game_restart_event.is_set():
                try:
                    board1, board2, current_player = run_two_player_game(
                        session1,
                        session2,
                        spectators,
                        board1,
                        board2,
                        init_current_player,
                    )

                    # ask players if they want to play again
                    session1.send(
                        "GAME_OVER Play again? (Y/N)", use_client_seq=False
                    )
                    session2.send(
                        "GAME_OVER Play again? (Y/N)", use_client_seq=False
                    )
                    try:
                        response1 = session1.recv_buffer.get(timeout=60)
                        response2 = session2.recv_buffer.get(timeout=60)
                    except queue.Empty:
                        print("[INFO] Timeout waiting for play again response.")
                        break

                    if response1 is None or response2 is None:
                        print("[INFO] One player disconnected during play again prompt.")
                        break
                    response1 = response1.strip().upper()
                    response2 = response2.strip().upper()
                    if response1 != "Y" or response2 != "Y":
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
                                "session": sessions[player_sessions[name]],
                                "board": board1 if name == p1_name else board2,
                                "opponent_board": board2 if name == p1_name else board1,
                                "disconnect_time": time.time(),
                                "current_player": current_player,
                                "game_state": "IN_PROGRESS",
                            }
                    break

        finally:
            # clear the game state
            with players_lock:
                try:
                    active_players.remove(player1_conn)
                    active_players.remove(player2_conn)
                except ValueError:
                    pass

                with sessions_lock:
                    timeout = 60
                    pending_reconnects = sum(
                        1
                        for v in disconnected.values()
                        if time.time() - v["disconnect_time"] <= timeout
                    )

                new_players = []
                if pending_reconnects == 0:
                    while len(active_players) < 2 and spectators:
                        spectator_conn = spectators.pop(0)
                        try:
                            session_sp = sessions[spectator_conn]
                            session_sp.send("PING\n")
                            active_players.append(spectator_conn)
                            new_players.append(spectator_conn)
                            session_sp.send("ROLE PLAYER")
                            print(
                                f"[INFO] the spectator promote to player: {spectator_conn.getpeername()}"
                            )
                        except (ConnectionResetError, BrokenPipeError):
                            continue

                if len(new_players) == 2:
                    game_restart_event.set()
                    threading.Thread(
                        target=handle_two_player_game,
                        args=(new_players[0], new_players[1]),
                    ).start()

    # start the game session in a separate thread
    game_thread = threading.Thread(target=game_session)
    game_thread.start()


def handle_client(conn, addr):
    global active_players, spectators, players_lock, disconnected
    print(f"[INFO] Client connected from {addr}")
    session = ClientSession(conn)
    sessions[conn] = session

    def message_handler(username):
        while True:
            try:
                packet = protocol.recv_packet(conn)
                if packet.ptype == protocol.PacketType.CHAT:
                    msg = f"[{username}] {packet.data.decode('utf-8')}"
                    broadcast_message(conn, msg)
                elif packet.ptype == protocol.PacketType.DATA:
                    sessions[conn].recv_buffer.put(packet.data.decode("utf-8"))
            except Exception as e:
                print(f"[ERROR] Connection error: {e}")
                sessions[conn].recv_buffer.put("CONNECTION_ERROR")
                break

    try:
        first_line = session.recv()

        if not first_line.startswith("USER "):
            conn.close()
            return

        username = first_line.split(" ", 1)[1]
        print("[INFO] username: ", username)

        handler_thread = threading.Thread(target=message_handler, args=(username,))
        handler_thread.daemon = True
        handler_thread.start()

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
                            threading.Thread(
                                target=handle_two_player_game, args=(p1, p2)
                            ).start()
                    return
                else:
                    del disconnected[username]

            player_sessions[username] = conn
            print(f"[INFO] A new player: {username}")

        with players_lock:
            if len(active_players) < 2:
                active_players.append(conn)
                session.send("ROLE PLAYER\n")
                print("[INFO] Player added to active players list")
                # check if we have two players
                if len(active_players) == 2:
                    player1, player2 = active_players
                    game_thread = threading.Thread(
                        target=handle_two_player_game, args=(player1, player2)
                    )
                    game_thread.start()
            else:
                spectators.append(conn)
                session.send("ROLE SPECTATOR\n")
                print("[INFO] Client added to spectators list")
    except Exception as e:
        print(f"[ERROR] error in client handling: {e}")
        conn.close()

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
