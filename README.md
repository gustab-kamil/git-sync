# Cisco Configuration Backup (GitOps)

A professional DevOps automation script written in Python to cyclically backup Cisco network device configurations to a Git repository. This project demonstrates a GitOps approach to network configuration management.

## Features

- **Automated Backup**: Fetches running configuration from Cisco devices (simulated via source file for this demo).
- **Git Integration**: Automatically initializes a Git repository, tracks changes, and pushes updates.
- **Change Detection**: Only commits when actual configuration changes are detected.
- **Logging**: Comprehensive logging with rotation support.
- **Resilience**: Robust error handling for file I/O and Git operations.

## Project Structure

```
├── config/              # Configuration files
├── src/                 # Source code
│   └── backup_script.py # Main application logic
├── backups/             # Destination for backed up configs (Auto-generated)
├── logs/                # Application logs (Auto-generated)
├── cisco_running_config.cfg # Simulated device source
├── requirements.txt     # Python dependencies
└── README.md            # Documentation
```

## Prerequisites

- Python 3.8+
- Git installed and configured

## Installation

1. Clone or download this repository.
2. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The script uses environment variables for configuration. You can create a `.env` file in the root directory:

```bash
SOURCE_CONFIG_PATH=cisco_running_config.cfg
BACKUP_REPO_PATH=.
```

## Usage

### Manual Execution

To run the backup script manually:

```bash
python3 src/backup_script.py
```

Check the `logs/` directory for execution details and `backups/` for the committed configuration.

### Automated Execution (Crontab)

To schedule this script to run automatically (e.g., every hour), use `crontab`.

1. Open the crontab editor:
   ```bash
   crontab -e
   ```

2. Add the following line to schedule the job (adjust paths to match your system):

   ```cron
   # Run Cisco Backup every hour at minute 0
   0 * * * * cd /path/to/project && /usr/bin/python3 src/backup_script.py >> /path/to/project/logs/cron.log 2>&1
   ```

   **Explanation:**
   - `0 * * * *`: Run at minute 0 of every hour.
   - `cd /path/to/project`: Navigate to the project root so relative paths work.
   - `/usr/bin/python3`: Absolute path to Python interpreter (run `which python3` to confirm).
   - `src/backup_script.py`: Path to the script.
   - `>> ... 2>&1`: Redirects standard output and error to a log file for debugging cron issues.

## Customization

To adapt this for real devices:
1. Modify `CiscoDevice` class in `src/backup_script.py`.
2. Integrate `netmiko` or `napalm` to establish SSH connections.
3. Update `get_config` to pull from the live device.

## License

MIT

 
