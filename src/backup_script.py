import os
import sys
import logging
import datetime
from git import Repo, GitCommandError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class BackupLogger:
    @staticmethod
    def setup_logging(log_dir="logs"):
        """Configures logging to file and console."""
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"backup_{datetime.datetime.now().strftime('%Y-%m')}.log")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger("CiscoBackup")

class CiscoDevice:
    def __init__(self, source_file):
        self.source_file = source_file
        self.logger = logging.getLogger("CiscoBackup")

    def get_config(self):
        """
        Simulates retrieving configuration from a Cisco device.
        In a real scenario, this would use Netmiko/Paramiko to SSH into the device.
        """
        self.logger.info(f"Connecting to device source: {self.source_file}...")
        try:
            with open(self.source_file, 'r') as f:
                config_data = f.read()
            self.logger.info("Configuration retrieved successfully.")
            return config_data
        except FileNotFoundError:
            self.logger.error(f"Source file {self.source_file} not found.")
            raise
        except Exception as e:
            self.logger.error(f"Error retrieving config: {e}")
            raise

class GitManager:
    def __init__(self, repo_path, remote_name='origin', branch='main'):
        self.repo_path = repo_path
        self.remote_name = remote_name
        self.branch = branch
        self.logger = logging.getLogger("CiscoBackup")
        self.repo = self._init_repo()

    def _init_repo(self):
        """Initialize or load the git repository."""
        try:
            if not os.path.exists(os.path.join(self.repo_path, '.git')):
                self.logger.info(f"Initializing new Git repository at {self.repo_path}")
                repo = Repo.init(self.repo_path)
            else:
                repo = Repo(self.repo_path)
            return repo
        except Exception as e:
            self.logger.critical(f"Failed to initialize Git repo: {e}")
            raise

    def commit_and_push(self, filename, commit_message):
        """Commits changes and pushes to remote."""
        try:
            # Add the specific file to the index
            self.repo.index.add([filename])

            # Check for changes in the index against HEAD (if HEAD exists)
            has_changes = True
            try:
                if self.repo.head.is_valid() and not self.repo.index.diff(self.repo.head.commit):
                    has_changes = False
            except Exception:
                # Fallback or if initial commit
                pass

            if not has_changes:
                self.logger.info("No configuration changes detected. Skipping commit.")
                return

            self.repo.index.commit(commit_message)
            self.logger.info(f"Committed changes: {commit_message}")

            # Check if remote exists before pushing
            if self.remote_name in [r.name for r in self.repo.remotes]:
                origin = self.repo.remote(name=self.remote_name)
                self.logger.info(f"Pushing to remote {self.remote_name}/{self.branch}...")
                origin.push(refspec=f'{self.branch}:{self.branch}')
                self.logger.info("Push successful.")
            else:
                self.logger.warning(f"Remote '{self.remote_name}' not found. Skipping push.")

        except GitCommandError as e:
            self.logger.error(f"Git operation failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during git operations: {e}")

def main():
    # Configuration
    # Determine the project root directory (assuming script is in src/)
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Use environment variables or defaults relative to project root
    SOURCE_CONFIG = os.getenv("SOURCE_CONFIG_PATH", os.path.join(PROJECT_ROOT, "cisco_running_config.cfg"))
    BACKUP_REPO_DIR = os.getenv("BACKUP_REPO_PATH", PROJECT_ROOT)
    BACKUP_FILENAME = "cisco_backup.cfg"
    
    # Logs directory relative to project root
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    logger = BackupLogger.setup_logging(LOG_DIR)
    logger.info("Starting backup process...")

    try:
        # 1. Fetch Configuration
        device = CiscoDevice(SOURCE_CONFIG)
        config_content = device.get_config()

        # 2. Save to Repository Directory
        backup_path = os.path.join(BACKUP_REPO_DIR, "backups")
        os.makedirs(backup_path, exist_ok=True)
        
        target_file = os.path.join(backup_path, BACKUP_FILENAME)
        
        # Write config to file
        with open(target_file, 'w') as f:
            f.write(config_content)
        logger.info(f"Configuration saved to {target_file}")

        # 3. Git Operations
        git_manager = GitManager(BACKUP_REPO_DIR)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"Auto-backup: {timestamp}"
        
        # We need to pass the relative path for git add
        relative_path = os.path.relpath(target_file, BACKUP_REPO_DIR)
        git_manager.commit_and_push(relative_path, commit_msg)

        logger.info("Backup process completed successfully.")

    except Exception as e:
        logger.critical(f"Backup process failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

