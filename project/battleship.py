"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import queue
import random, threading, time, protocol
from protocol import sessions

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]


class ClientSession:
    def __init__(self, conn):
        self.conn = conn
        self.client_seq = 0  # the client's sequence number
        self.server_seq = 0  # the server's sequence number
        self.lock = threading.Lock()
        self.recv_buffer = queue.Queue()

    def get_next_server_seq(self):
        """generate the next server sequence number"""
        with self.lock:
            self.server_seq += 1
            return self.server_seq

    def send(self, data: str, ptype=protocol.PacketType.DATA, use_client_seq=False):
        """send the data packet to the client"""
        seq = self.client_seq if use_client_seq else self.get_next_server_seq()
        try:
            protocol.send_packet(
                self.conn,
                protocol.Packet(sequence_number=seq, ptype=ptype, data=data.encode("utf-8")),
            )
        except OSError as e:
            print(f"[ERROR] send failed: {e}")
            raise ConnectionResetError("Client disconnected")

    def recv(self):
        try:
            packet = protocol.recv_packet(self.conn)
            self.client_seq = packet.sequence_number
            return packet.data.decode("utf-8")
        except Exception as e:
            print(f"[ERROR] ClientSession.recv error: {e}")
            return None


class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
      - Each player has their own Board instance.
      - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [["." for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [["." for _ in range(size)] for _ in range(size)]
        self.placed_ships = (
            []
        )  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def reset(self):
        """reset the board to its initial state"""
        self.hidden_grid = [["." for _ in range(self.size)] for _ in range(self.size)]
        self.display_grid = [["." for _ in range(self.size)] for _ in range(self.size)]
        self.placed_ships = []

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations;
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(
                        row, col, ship_size, orientation
                    )
                    self.placed_ships.append(
                        {"name": ship_name, "positions": occupied_positions}
                    )
                    placed = True

    def place_ships_manually(self, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = (
                    input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ")
                    .strip()
                    .upper()
                )

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == "H":
                    orientation = 0
                elif orientation_str == "V":
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(
                        row, col, ship_size, orientation
                    )
                    self.placed_ships.append(
                        {"name": ship_name, "positions": occupied_positions}
                    )
                    break
                else:
                    print(
                        f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again."
                    )

    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if a ship can be placed at the given position and orientation.

        Args:
            row (int): Starting row index.
            col (int): Starting column index.
            ship_size (int): Length of the ship.
            orientation (int): 0 for horizontal, 1 for vertical.

        Returns:
            bool: True if the ship can be placed, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != ".":
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != ".":
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = "S"
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = "S"
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
          - ('hit', None)          if it's a hit but not sunk
          - ('hit', <ship_name>)   if that shot causes the entire ship to sink
          - ('miss', None)         if no ship was there
          - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        cell = self.hidden_grid[row][col]
        if cell == "S":
            # Mark a hit
            self.hidden_grid[row][col] = "X"
            self.display_grid[row][col] = "X"
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ("hit", sunk_ship_name)  # A ship has just been sunk
            else:
                return ("hit", None)
        elif cell == ".":
            # Mark a miss
            self.hidden_grid[row][col] = "o"
            self.display_grid[row][col] = "o"
            return ("miss", None)
        elif cell == "X" or cell == "o":
            return ("already_shot", None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            return ("already_shot", None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Check if a hit at (row, col) causes a ship to sink.

        Args:
            row (int): Row index of the hit.
            col (int): Column index of the hit.

        Returns:
            str or None: The name of the sunk ship if it is fully destroyed, otherwise None.

        Logic:
            - Iterate through all placed ships.
            - If the hit position belongs to a ship, remove it from the ship's positions.
            - If the ship's positions are empty, it is considered sunk.
        """
        for ship in self.placed_ships:
            if (row, col) in ship["positions"]:
                ship["positions"].remove((row, col))
                if len(ship["positions"]) == 0:
                    return ship["name"]
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship["positions"]) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.

        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.

        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord("A") + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    HINT: you might want to add additional input validation here...
    """
    coord_str = coord_str.strip().upper()
    if len(coord_str) < 2 or len(coord_str) > 3:
        raise ValueError("coordinate syntax error，eg：A1 or B10")
    row_letter = coord_str[0]
    if not row_letter.isalpha():
        raise ValueError("row must be the charactor（A-J）")
    col_digits = coord_str[1:]
    if not col_digits.isdigit():
        raise ValueError("col must be the number（1-10）")
    row = ord(row_letter) - ord("A")
    col = int(col_digits) - 1
    if row < 0 or row >= BOARD_SIZE or col < 0 or col >= BOARD_SIZE:
        raise ValueError("input coordinate out of range（A1-J10）")
    return (row, col)


def run_two_player_game(
    session1: ClientSession,
    session2: ClientSession,
    spectators,
    board1=None,
    board2=None,
    current_player=1,
):
    """
    Runs a two-player Battleship game.
    Each player has their own board, and they take turns firing at each other's board.
    """
    try:

        def broadcast_to_spectators(msg):
            """
                Broadcast a message to all spectators.

                Args:
                    msg (str): The message to be sent to all spectators.

                Logic:
                    - Iterate through the list of spectators.
                    - Retrieve each spectator's session from the `sessions` dictionary.
                    - Send the message to the spectator's session.
                    - If an error occurs (e.g., spectator disconnected), log an error message.
            """
            for spectator in spectators:
                try:
                    session_sp = sessions[spectator]
                    session_sp.send(msg + "\n")
                except:
                    print("[ERROR] Failed to send message to spectator")

        def send_board(session, board, show_hidden_board=False):
            """
                Send the current state of the board to the given session.

                Args:
                    session (ClientSession): The session to which the board will be sent.
                    board (Board): The board object containing the game state.
                    show_hidden_board (bool): If True, send the hidden grid (with ship positions).
                                              If False, send the display grid (without ship positions).

                Logic:
                    - Determine which grid to send based on the `show_hidden_board` flag.
                    - Construct a list of strings representing the board:
                        - The first line contains column headers (1, 2, ..., N).
                        - Each subsequent line contains a row label (A, B, ...) followed by the row's contents.
                    - Send each line of the board to the session.
            """
            grid_to_print = (
                board.hidden_grid if show_hidden_board else board.display_grid
            )
            grid_data = []
            grid_data.append("GRID")
            grid_data.append(
                "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size))
            )
            for r in range(board.size):
                row_label = chr(ord("A") + r)
                row_str = " ".join(grid_to_print[r][c] for c in range(board.size))
                grid_data.append(f"{row_label:2} {row_str}")
            for line in grid_data:
                session.send(line)

        def handle_turn(sess1, opponent_board, sess2, player_name, opponent_name):
            while True:
                # Create thread-safe event objects and a shared result container
                timeout_occurred = threading.Event()
                input_received = threading.Event()
                user_input = [None]  # Shared user input between threads

                # Handle user input in a separate thread
                def read_input():
                    try:
                        send_board(sess1, opponent_board)
                        sess1.send(
                            f"{player_name}, enter coordinate to fire at (e.g. B5):",
                            use_client_seq=True,
                        )
                        guess = sess1.recv_buffer.get()
                        if guess == "CONNECTION_ERROR":
                            sess2.send("oppenent player quit the game, plz quit and trying to reconnect")
                            raise ConnectionResetError("Client disconnected")
                        if not timeout_occurred.is_set():  # If timeout has not occurred
                            user_input[0] = guess
                            input_received.set()  # Set input received event
                    except ConnectionError:
                        user_input[0] = "CONNECTION_ERROR"
                        input_received.set()

                # Start the input thread
                input_thread = threading.Thread(target=read_input)
                input_thread.daemon = True
                input_thread.start()

                # wait for user input or timeout
                if not input_received.wait(30):
                    # timeout occurred
                    timeout_occurred.set()
                    sess1.send("ERROR: out of time，skip the turn.")
                    print(f"[INFO] {player_name} out of time，skip the turn")
                    sess2.send(f"{player_name} out of time，its your turn.")
                    broadcast_to_spectators(
                        f"[SPECTATOR] {player_name} out of time，skip the turn"
                    )
                    return True  # proceed to next turn

                # Get the user input
                try:
                    guess = user_input[0]
                except queue.Empty:
                    print("[INFO] Timeout waiting for user input")
                    continue

                if guess.lower().startswith("quit"):
                    sess1.send("Game quit")
                    sess2.send(
                        f"opponent player quit the game."
                    )
                    print(f"[INFO] {player_name} quit.")
                    return False

                if not guess.lower().startswith("fire "):
                    sess1.send("ERROR: Use 'FIRE <coord>'")
                    continue  # request retry

                # Extract the coordinate from the command
                coord_str = guess.split()[1]
                try:
                    row, col = parse_coordinate(coord_str)
                    result, sunk_name = opponent_board.fire_at(row, col)
                    if result == "hit":
                        if sunk_name:
                            sess1.send(f"RESULT SINK {sunk_name}")
                            sess2.send(f"RESULT SINK {sunk_name}")
                            broadcast_to_spectators(
                                f"[SPECTATOR] {player_name} sink {sunk_name}！"
                            )
                            print(f"[INFO] {player_name} sink {sunk_name}！")
                        else:
                            sess1.send("RESULT HIT OPPONENT SHIP")
                            sess2.send("RESULT HIT YOURS SHIP")
                            broadcast_to_spectators(f"[SPECTATOR] {player_name} HIT！")
                            print(f"[INFO] {player_name} HIT！")
                        if opponent_board.all_ships_sunk():
                            sess1.send("GAME_OVER You win! All ships sunk!")
                            sess2.send("GAME_OVER You lose! All your ships are sunk!")
                            broadcast_to_spectators(
                                f"[SPECTATOR] GAME OVER! {player_name} wins!"
                            )
                            print(f"[INFO] GAME OVER! {player_name} wins!")
                            return False
                    elif result == "miss":
                        sess1.send("RESULT MISS")
                        sess2.send("RESULT MISS")
                        broadcast_to_spectators(f"[SPECTATOR] {player_name} MISS！")
                        print(f"[INFO] {player_name} MISS！")
                except ValueError:
                    sess1.send("ERROR: Invalid coordinate")
                    continue  # request retry

                # Update the display grid for the opponent
                broadcast_to_spectators("GRID")
                for r in range(opponent_board.size):
                    row_label = chr(ord("A") + r)
                    row_str = " ".join(
                        opponent_board.display_grid[r][c]
                        for c in range(opponent_board.size)
                    )
                    broadcast_to_spectators(f"{row_label:2} {row_str}")
                broadcast_to_spectators("")

                return True  # proceed to next turn

        def place_ships_manually(board, session, player_name):
            session.send(
                f"{player_name}, place your ships on the board.", use_client_seq=True
            )
            for ship_name, ship_size in SHIPS:
                while True:
                    session.send(f"PLACE {ship_name} (size {ship_size})")
                    session.send("FORMAT: PLACE <coord> <H/V>", use_client_seq=True)
                    try:
                        cmd = session.recv_buffer.get(timeout=30)
                    except ConnectionError:
                        if session == session1:
                            session2.send("QUIT", use_client_seq=True)
                            print(f"[INFO] {player_name} quit.")
                            return False
                        else:
                            session1.send("QUIT", use_client_seq=True)
                            print(f"[INFO] {player_name} quit.")
                            return False
                    if cmd.lower().startswith("quit"):
                        session.send(
                            "Thanks for playing. Goodbye.", use_client_seq=True
                        )
                        if session == session1:
                            session2.send(
                                f"opponent player quit the game, Thanks for playing. Goodbye.",
                                use_client_seq=True,
                            )
                        else:
                            session1.send(
                                f"opponent player quit the game, Thanks for playing. Goodbye.",
                                use_client_seq=True,
                            )
                        return False
                    if not cmd.lower().startswith("place "):
                        session.send(
                            "ERROR: Invalid command. Use 'PLACE <coord> <H/V>'",
                            use_client_seq=True,
                        )
                        continue
                    parts = cmd.split()
                    print(parts)
                    if len(parts) != 3:
                        session.send(
                            "ERROR: Invalid format. Example: PLACE A1 H BATTLESHIP",
                            use_client_seq=True,
                        )
                        continue
                    coord_str, orientation_str = parts[1], parts[2]
                    try:
                        row, col = parse_coordinate(coord_str)
                        if orientation_str.upper() not in ["H", "V"]:
                            session.send(
                                "ERROR: direction must be 'H' or 'V'",
                                use_client_seq=True,
                            )
                            continue
                        orientation = 0 if orientation_str == "H" else 1
                        if board.can_place_ship(row, col, ship_size, orientation):
                            occupied = board.do_place_ship(
                                row, col, ship_size, orientation
                            )
                            board.placed_ships.append(
                                {"name": ship_name, "positions": occupied}
                            )
                            session.send(
                                f"SUCCESS: {ship_name} placed at {coord_str}",
                                use_client_seq=True,
                            )
                            send_board(session, board, show_hidden_board=True)
                            break
                        else:
                            session.send(
                                "ERROR: Cannot place ship here", use_client_seq=True
                            )
                    except ValueError as e:
                        session.send(f"ERROR: {e}", use_client_seq=True)

        # Initialize boards for both players

        session1.send("Welcome to Battleship! You are Player 1.", use_client_seq=False)
        session2.send("Welcome to Battleship! You are Player 2.", use_client_seq=False)

        if board1.placed_ships == []:
            board1 = Board(BOARD_SIZE)
            place_ships_manually(board1, session1, "Player 1")
        else:
            session1.send("[INFO] restore game progress")

        if board2.placed_ships == []:
            board2 = Board(BOARD_SIZE)
            place_ships_manually(board2, session2, "Player 2")
        else:
            session1.send("[INFO] restore game progress")

        session1.send("All ships placed. Game starts now!", use_client_seq=False)
        session2.send("All ships placed. Game starts now!", use_client_seq=False)

        while True:
            if current_player == 1:
                if not handle_turn(session1, board2, session2, "Player 1", "Player 2"):
                    break
                current_player = 2
            else:
                if not handle_turn(session2, board1, session1, "Player 2", "Player 1"):
                    break
                current_player = 1

    finally:
        return board1, board2, current_player


if __name__ == "__main__":
    # Optional: run this file as a script to test single-player mode
    run_single_player_game_locally()
