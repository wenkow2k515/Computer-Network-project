"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import random, threading, time

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


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
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def reset(self):
        """reset the board to its initial state"""
        self.hidden_grid = [['.' for _ in range(self.size)] for _ in range(self.size)]
        self.display_grid = [['.' for _ in range(self.size)] for _ in range(self.size)]
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
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
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
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")


    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
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
        if cell == 'S':
            # Mark a hit
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)  # A ship has just been sunk
            else:
                return ('hit', None)
        elif cell == '.':
            # Mark a miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
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
            row_label = chr(ord('A') + r)
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
    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1
    if row < 0 or row >= BOARD_SIZE or col < 0 or col >= BOARD_SIZE:
        raise ValueError("input coordinate out of range（A1-J10）")
    return (row, col)


def run_two_player_game(rfile1, wfile1, rfile2, wfile2, spectators, board1 = None, board2 = None):
    """
    Runs a two-player Battleship game.
    Each player has their own board, and they take turns firing at each other's board.
    """
    try:
        def broadcast_to_spectators(msg):
            for spectator in spectators:
                try:
                    wfile = spectator.makefile('w')
                    wfile.write(msg + "\n")
                    wfile.flush()
                except:
                    spectators.remove(spectator)

        def send(wfile, msg):
            wfile.write(msg + '\n')
            wfile.flush()

        def send_board(wfile, board, show_hidden_board=False):
            grid_to_print = board.hidden_grid if show_hidden_board else board.display_grid
            wfile.write("GRID\n")
            wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
            for r in range(board.size):
                row_label = chr(ord('A') + r)
                row_str = " ".join(grid_to_print[r][c] for c in range(board.size))
                wfile.write(f"{row_label:2} {row_str}\n")
            wfile.write('\n')
            wfile.flush()

        def recv(rfile):
            line = rfile.readline()
            if not line:  # if client disconnected, raise an exception
                raise ConnectionError("Client disconnected")
            line = line.strip()
            return line

        def handle_turn(player_rfile, player_wfile, opponent_board, opponent_wfile, player_name, opponent_name):
            # Create thread-safe event objects and a shared result container
            timeout_occurred = threading.Event()
            input_received = threading.Event()
            user_input = [None]  # Shared user input between threads

            # Handle user input in a separate thread
            def read_input():
                try:
                    send_board(player_wfile, opponent_board)
                    send(player_wfile, f"{player_name}, enter coordinate to fire at (e.g. B5):")
                    guess = recv(player_rfile)
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
                send(player_wfile, "ERROR: out of time，skip the turn.")
                print(f"[INFO] {player_name} out of time，skip the turn")
                send(opponent_wfile, f"{player_name} out of time，its your turn.")
                broadcast_to_spectators(f"[SPECTATOR] {player_name} out of time，skip the turn")
                return True  # proceed to next turn

            # Get the user input
            guess = user_input[0]

            # if guess == "CONNECTION_ERROR":
            #     print(f"[INFO] {player_name} disconnected. Waiting for reconnection...")
            #     send(opponent_wfile, f"{player_name} disconnected. Waiting for reconnection...")
            #
            #     # Wait for reconnection within 60 seconds
            #     timeout = 60
            #     start_time = time.time()
            #     reconnected = False
            #
            #     while time.time() - start_time < timeout:
            #         try:
            #             # Attempt to read from the player's file to check if they reconnected
            #             guess = recv(player_rfile)
            #             reconnected = True
            #             break
            #         except ConnectionError:
            #             time.sleep(1)  # Wait for 1 second before retrying
            #
            #     if not reconnected:
            #         print(f"[INFO] {player_name} failed to reconnect within {timeout} seconds.")
            #         send(opponent_wfile, f"{player_name} failed to reconnect. Game over.")
            #         return False
            #     else:
            #         print(f"[INFO] {player_name} reconnected.")
            #         send(player_wfile, "Reconnected successfully. It's your turn.")
            #         send(opponent_wfile, f"{player_name} reconnected. Continuing the game.")
            #         return True  # Allow the player to continue their turn

            if guess.lower().startswith("quit"):
                send(player_wfile, "Thanks for playing. Goodbye.")
                send(opponent_wfile, f"opponent player quit the game, Thanks for playing. Goodbye.")
                print(f"[INFO] {player_name} quit.")
                return False

            if not guess.lower().startswith("fire "):
                send(player_wfile, "ERROR: Use 'FIRE <coord>'")
                return True  # request retry

            # Extract the coordinate from the command
            coord_str = guess.split()[1]
            try:
                row, col = parse_coordinate(coord_str)
                result, sunk_name = opponent_board.fire_at(row, col)
                if result == 'hit':
                    if sunk_name:
                        send(player_wfile, f"RESULT SINK {sunk_name}")
                        send(opponent_wfile, f"RESULT SINK {sunk_name}")
                        broadcast_to_spectators(f"[SPECTATOR] {player_name} sink {sunk_name}！")
                        print(f"[INFO] {player_name} sink {sunk_name}！")
                    else:
                        send(player_wfile, "RESULT HIT")
                        send(opponent_wfile, "RESULT HIT")
                        broadcast_to_spectators(f"[SPECTATOR] {player_name} HIT！")
                        print(f"[INFO] {player_name} HIT！")
                    if opponent_board.all_ships_sunk():
                        send(player_wfile, "GAME_OVER You win! All ships sunk!")
                        send(opponent_wfile, "GAME_OVER You lose! All your ships are sunk!")
                        broadcast_to_spectators(f"[SPECTATOR] GAME OVER! {player_name} wins!")
                        print(f"[INFO] GAME OVER! {player_name} wins!")
                        return False
                elif result == 'miss':
                    send(player_wfile, "RESULT MISS")
                    send(opponent_wfile, "RESULT MISS")
                    broadcast_to_spectators(f"[SPECTATOR] {player_name} MISS！")
                    print(f"[INFO] {player_name} MISS！")
            except ValueError:
                send(player_wfile, "ERROR: Invalid coordinate")
                return True  # request retry

            # Update the display grid for the opponent
            broadcast_to_spectators("GRID")
            for r in range(opponent_board.size):
                row_label = chr(ord('A') + r)
                row_str = " ".join(opponent_board.display_grid[r][c] for c in range(opponent_board.size))
                broadcast_to_spectators(f"{row_label:2} {row_str}")
            broadcast_to_spectators("")

            return True  # proceed to next turn

        def place_ships_manually(board, rfile, wfile, player_name):
            send(wfile, f"{player_name}, place your ships on the board.")
            for ship_name, ship_size in SHIPS:
                while True:
                    send(wfile, f"PLACE {ship_name} (size {ship_size})")
                    send(wfile, "FORMAT: PLACE <coord> <H/V>")
                    try:
                        cmd = recv(rfile)
                    except ConnectionError:
                        if wfile == wfile1:
                            send(wfile2, "QUIT")
                            print(f"[INFO] {player_name} quit.")
                            return False
                        else:
                            send(wfile1, "QUIT")
                            print(f"[INFO] {player_name} quit.")
                            return False
                    if cmd.lower().startswith("quit"):
                        send(wfile, "Thanks for playing. Goodbye.")
                        if wfile == wfile1:
                            send(wfile2, f"opponent player quit the game, Thanks for playing. Goodbye.")
                        else:
                            send(wfile1, f"opponent player quit the game, Thanks for playing. Goodbye.")
                        return False
                    if not cmd.lower().startswith("place "):
                        send(wfile, "ERROR: Invalid command. Use 'PLACE <coord> <H/V>'")
                        continue
                    parts = cmd.split()
                    print(parts)
                    if len(parts) != 3:
                        send(wfile, "ERROR: Invalid format. Example: PLACE A1 H BATTLESHIP")
                        continue
                    coord_str, orientation_str = parts[1], parts[2]
                    try:
                        row, col = parse_coordinate(coord_str)
                        if orientation_str.upper() not in ['H', 'V']:
                            send(wfile, "ERROR: direction must be 'H' or 'V'")
                            continue
                        orientation = 0 if orientation_str == 'H' else 1
                        if board.can_place_ship(row, col, ship_size, orientation):
                            occupied = board.do_place_ship(row, col, ship_size, orientation)
                            board.placed_ships.append({'name': ship_name, 'positions': occupied})
                            send(wfile, f"SUCCESS: {ship_name} placed at {coord_str}")
                            send_board(wfile, board, show_hidden_board=True)
                            break
                        else:
                            send(wfile, "ERROR: Cannot place ship here")
                    except ValueError as e:
                        send(wfile, f"ERROR: {e}")

        # Initialize boards for both players

        send(wfile1, "Welcome to Battleship! You are Player 1.")
        send(wfile2, "Welcome to Battleship! You are Player 2.")

        if board1.placed_ships == []:
            board1 = Board(BOARD_SIZE)
            place_ships_manually(board1, rfile1, wfile1, "Player 1")
        else:
            send(wfile1, "[INFO] restore game progress")
            send_board(wfile1, board1, show_hidden_board=False)  # show hidden board

        if board2.placed_ships == []:
            board2 = Board(BOARD_SIZE)
            place_ships_manually(board2, rfile2, wfile2, "Player 2")
        else:
            send(wfile2, "[INFO] restore game progress")
            send_board(wfile2, board2, show_hidden_board=False)

        send(wfile1, "All ships placed. Game starts now!")
        send(wfile2, "All ships placed. Game starts now!")

        current_player = 1

        while True:
            if current_player == 1:
                if not handle_turn(rfile1, wfile1, board2, wfile2, "Player 1", "Player 2"):
                    break
                current_player = 2
            else:
                if not handle_turn(rfile2, wfile2, board1, wfile1, "Player 2", "Player 1"):
                    break
                current_player = 1

    finally:
        return board1, board2


if __name__ == "__main__":
    # Optional: run this file as a script to test single-player mode
    run_single_player_game_locally()

