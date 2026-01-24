import os
import sys
import logging
import datetime
import argparse
from git import Repo, GitCommandError
from dotenv import load_dotenv

load_dotenv()

class BackupLogger:
    @staticmethod
    def setup_logging(log_dir="logs"):
        os.makedirs(log_dir, exist_ok=True)
        # Log to file with rotation based on month
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
        Retrieves config content. 
        TODO: Replace file read with Netmiko/Paramiko SSH connection for production.
        """
        self.logger.info(f"Connecting to source: {self.source_file}")
        try:
            with open(self.source_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            self.logger.error(f"Source file {self.source_file} missing.")
            raise
        except Exception as e:
            self.logger.error(f"Config retrieval failed: {e}")
            raise

class GitManager:
    def __init__(self, repo_path, remote_name='origin', branch='main'):
        self.repo_path = repo_path
        self.remote_name = remote_name
        self.branch = branch
        self.logger = logging.getLogger("CiscoBackup")
        self.repo = self._init_repo()

    def _init_repo(self):
        try:
            if not os.path.exists(os.path.join(self.repo_path, '.git')):
                self.logger.info(f"Initializing Git repo at {self.repo_path}")
                return Repo.init(self.repo_path)
            return Repo(self.repo_path)
        except Exception as e:
            self.logger.critical(f"Git init failed: {e}")
            raise

    def commit_and_push(self, filename, commit_message):
        try:
            self.repo.index.add([filename])

            # Idempotency check: prevent empty commits
            has_changes = True
            try:
                if self.repo.head.is_valid() and not self.repo.index.diff(self.repo.head.commit):
                    has_changes = False
            except Exception:
                pass # First commit scenario

            if not has_changes:
                self.logger.info("No changes detected. Skipping commit.")
                return

            self.repo.index.commit(commit_message)
            self.logger.info(f"Committed: {commit_message}")

            if self.remote_name in [r.name for r in self.repo.remotes]:
                origin = self.repo.remote(name=self.remote_name)
                self.logger.info(f"Pushing to {self.remote_name}/{self.branch}...")
                origin.push(refspec=f'{self.branch}:{self.branch}')
            else:
                self.logger.warning(f"Remote '{self.remote_name}' not configured. Local commit only.")

        except GitCommandError as e:
            self.logger.error(f"Git cmd failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Git operation error: {e}")
            raise

def setup_auth(args, logger):
    """Configures Git authentication based on arguments."""
    mode = args.auth[0]
    
    if mode == 'ssh':
        # Determine key path: User provided OR default
        if len(args.auth) > 1:
            key_path = args.auth[1]
        else:
            key_path = os.path.expanduser('~/.ssh/id_rsa')
            
        if not os.path.exists(key_path):
            logger.warning(f"SSH Key not found at {key_path}. Git may fail if key is required.")
        
        # Set git environment variable to use specific SSH key
        # -o IdentitiesOnly=yes ensures it uses exactly this key and doesn't try others
        os.environ['GIT_SSH_COMMAND'] = f'ssh -i "{key_path}" -o IdentitiesOnly=yes'
        logger.info(f"Auth Mode: SSH (Key: {key_path})")
        
    elif mode == 'pass':
        # Clear env var to allow standard Git https/password prompt behavior
        os.environ.pop('GIT_SSH_COMMAND', None)
        logger.info("Auth Mode: Password/HTTPS (Standard Git behavior)")

def main():
    # 1. Parse Arguments
    parser = argparse.ArgumentParser(description="Cisco Configuration Backup Tool")
    parser.add_argument(
        '--auth', 
        nargs='+', 
        default=['ssh'], 
        help="Authentication mode. Options: 'ssh <path-to-key>' (default) OR 'pass'"
    )
    args = parser.parse_args()

    # 2. Setup Logging & Paths
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger = BackupLogger.setup_logging(os.path.join(PROJECT_ROOT, "logs"))
    
    # 3. Configure Auth
    setup_auth(args, logger)

    SOURCE_CONFIG = os.getenv("SOURCE_CONFIG_PATH", os.path.join(PROJECT_ROOT, "cisco_running_config.cfg"))
    BACKUP_REPO_DIR = os.getenv("BACKUP_REPO_PATH", PROJECT_ROOT)
    BACKUP_FILENAME = "cisco_backup.cfg"
    
    logger.info("Starting backup...")

    try:
        # 4. Fetch Config
        device = CiscoDevice(SOURCE_CONFIG)
        config_content = device.get_config()

        # 5. Write to local storage
        backup_path = os.path.join(BACKUP_REPO_DIR, "backups")
        os.makedirs(backup_path, exist_ok=True)
        target_file = os.path.join(backup_path, BACKUP_FILENAME)
        
        with open(target_file, 'w') as f:
            f.write(config_content)

        # 6. Sync to Git
        git_manager = GitManager(BACKUP_REPO_DIR)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        relative_path = os.path.relpath(target_file, BACKUP_REPO_DIR)
        git_manager.commit_and_push(relative_path, f"Auto-backup: {timestamp}")

        logger.info("Backup completed successfully.")

    except Exception as e:
        logger.critical(f"Backup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

