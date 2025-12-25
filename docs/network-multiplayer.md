# Network Multiplayer

Play Gin Rummy against another player over a local network.

## Quick Start

### 1. Start the Server

On one machine, start the server:

```bash
uv run gin-server
```

Output:
```
Gin Rummy Server started
Listening on 192.168.1.100:5555
Waiting for 2 players to connect...
```

Note the IP address displayed - players will need this to connect.

### 2. Connect Players

Each player connects from their terminal:

```bash
uv run gin-client 192.168.1.100
```

You'll be prompted for your name:
```
Connected to 192.168.1.100:5555
Enter your name: Alice
Waiting for opponent to connect...
```

Once both players connect, the game begins automatically.

## Command Options

### Server

```bash
uv run gin-server [--port PORT] [--host HOST]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port`, `-p` | 5555 | Port to listen on |
| `--host` | 0.0.0.0 | Host to bind to |

### Client

```bash
uv run gin-client [HOST] [--port PORT] [--name NAME]
```

| Option | Default | Description |
|--------|---------|-------------|
| `HOST` | (prompt) | Server IP address |
| `--port`, `-p` | 5555 | Server port |
| `--name`, `-n` | (prompt) | Your player name |

## Gameplay

The game works the same as local play:

1. **Draw phase**: Choose `1` for deck or `2` for discard pile
2. **Discard phase**: Enter the card number to discard, or `k` to knock
3. After each round, press Enter to continue

Your hand is displayed organized by suit with melds shown in brackets:
```
  ♠: [3♠ 4♠ 5♠] 8♠
  ♥: 2♥ 7♥
  ♦: [Q♦ Q♣ Q♥]
  ♣: 6♣ K♣

  Deadwood: 23
```

## Network Details

- **Protocol**: TCP with JSON messages
- **Default port**: 5555
- **Players**: Exactly 2 required
- **Disconnection**: Game ends if either player disconnects

## Troubleshooting

**"Could not connect"**
- Check the server is running
- Verify the IP address is correct
- Ensure port 5555 is not blocked by firewall

**"Game is full"**
- Server already has 2 players connected
- Start a new server instance

**Connection drops**
- Game will notify the remaining player
- Restart server and reconnect both players
