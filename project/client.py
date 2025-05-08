"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.

TODO: Fix the message synchronization issue using concurrency (Tier 1, item 1).
"""

import socket, threading, time

HOST = '127.0.0.1'
PORT = 5000

# HINT: The current problem is that the client is reading from the socket,
# then waiting for user input, then reading again. This causes server
# messages to appear out of order.
#
# Consider using Python's threading module to separate the concerns:
# - One thread continuously reads from the socket and displays messages
# - The main thread handles user input and sends it to the server
#
# import threading

def main():
    username = input("Enter your username: ").strip()

    while True:
        try:
            # try to connect to the server
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))

            # send username to the server
            wfile = s.makefile('w')
            wfile.write(f"USER {username}\n")
            wfile.flush()

            # receive the server's response
            rfile = s.makefile('r')
            receiver_thread = threading.Thread(target=receive_messages, args=(rfile, wfile))
            receiver_thread.daemon = True
            receiver_thread.start()

            # handle user input
            handle_user_input(wfile)
            break

        except (ConnectionRefusedError, socket.timeout) as e:
            print(f"[INFO]connecting error: {e}, will try after 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[ERROR]: {e}")
            break

# HINT: A better approach would be something like:
#
def handle_user_input(wfile):
    """handle user input and send it to the server"""
    try:
        while True:
            try:
                user_input = input(">> ").strip()
                wfile.write(user_input + '\n')
                wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                print("\n[ERROR] disconnected, trying to reconnected ...")
                main()  # reconnect to the server
                break
    except KeyboardInterrupt:
        print("\n[INFO] client exiting...")

def receive_messages(rfile, wfile):
    """keep receiving messages from the server"""
    try:
        while True:
            line = rfile.readline()
            if not line:
                print("\n[INFO] server closed the connection")
                break

            line = line.strip()

            # handle special cases
            if line == "RECONNECTED":
                print("\n[SUCCESS] reconnected to the server")
                continue
            elif line == "ROLE PLAYER":
                print("\n[INFO] You are now a player")
            elif line == "ROLE SPECTATOR":
                print("\n[INFO] You are now a spectator")

            if line == "GRID":
                print("\n[INFO] Grid:")
                while True:
                    grid_line = rfile.readline().strip()
                    if not grid_line:
                        break
                    print(grid_line)
            else:
                print(line)

    except ConnectionResetError:
        print("\n[ERROR] Connection reset by server")
    except Exception as e:
        print(f"\n[ERROR] A error happen in received message : {e}")
#
# def main():
#     # Set up connection
#     # Start a thread for receiving messages
#     # Main thread handles sending user input

if __name__ == "__main__":
    main()