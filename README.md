# Battleship Multiplayer Game

## Table of Contents
- [Project Overview](#project-overview)
- [Environment Requirements](#environment-requirements)
- [Installation](#installation)
- [Running the Game](#running-the-game)
- [Gameplay Instructions](#gameplay-instructions)
- [Features Demonstrated](#features-demonstrated)
- [Troubleshooting](#troubleshooting)

---

## Project Overview
This project implements a networked multiplayer Battleship game ("BEER") with the following features:
- **Tier 1**: 2-player turn-based gameplay, concurrency fixes, message synchronization.
- **Tier 2**: Input validation, timeout handling, disconnection recovery, spectator support.
- **Tier 3**: Multiple concurrent connections, reconnection support, spectator chat.
- **Tier 4**: Custom protocol with CRC-32 checksums, real-time chat (IM channel).

---

## Environment Requirements
- **Python 3.7+** (tested on Python 3.9)
- **No external dependencies** (uses only standard libraries: `socket`, `threading`, `struct`, etc.)

---

## Ensure all files are present

- `server.py`
- `client.py`
- `protocol.py`
- `battleship.py`

---

## Running the Game

### Step 1: Start the Server

```bash
python server.py
```
### Step 2: Start Clients

Open two or more terminal windows and run:

```bash
python client.py
```
The first two clients will become players; additional clients join as spectators.

Gameplay Instructions
Starting a Game
Player Setup:

Enter <username> when connecting (automatically handled by the client).
Players will be prompted to place ships using commands like:
```bash
PLACE A1 H
A1: Starting coordinate.
H: Horizontal placement (V for vertical).
```
Turn-Based Combat:
Players alternate firing at coordinates:
```bash
FIRE B5
Server responds with HIT, MISS, or SINK <ship>.
```
Chat System:
Send messages to all players/spectators:
```bash
CHAT Hello, players!
```
### Spectator Mode

- Spectators receive real-time updates but cannot interact.
- Chat messages from spectators are broadcast to all participants.

---

## Features Demonstrated

- **Concurrency:** Separate threads for receiving and sending messages.
- **Reconnection:** Disconnected players can reconnect within 60 seconds.
- **Custom Protocol:**
  - Packet structure: Sequence number, type, CRC-32 checksum.
  - Corrupted packets are discarded and retransmitted via NACK.
- **Chat System:** `CHAT` packet type for real-time messaging.

---

## Troubleshooting

- **Port Conflicts:**
  - If `Address already in use` occurs, change the port in `server.py` (e.g., `PORT = 5000`).
- **Client Connection Issues:**
  - Ensure the server is running before starting clients.
  - Verify firewall settings allow traffic on port 5000.
- **Checksum Errors:**
  - If `Checksum mismatch` appears, the client will automatically request retransmission.
