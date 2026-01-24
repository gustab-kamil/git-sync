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
        self._ensure_branch()

    def _init_repo(self):
        try:
            if not os.path.exists(os.path.join(self.repo_path, '.git')):
                self.logger.info(f"Initializing Git repo at {self.repo_path}")
                return Repo.init(self.repo_path)
            return Repo(self.repo_path)
        except Exception as e:
            self.logger.critical(f"Git init failed: {e}")
            raise

    def _ensure_branch(self):
        """Checks out the target branch, creating it if necessary."""
        try:
            # Check if branch exists locally
            if self.branch in self.repo.heads:
                if self.repo.active_branch.name != self.branch:
                    self.logger.info(f"Switching to existing branch: {self.branch}")
                    self.repo.heads[self.branch].checkout()
            else:
                self.logger.info(f"Creating and switching to new branch: {self.branch}")
                self.repo.create_head(self.branch).checkout()
                
        except Exception as e:
            self.logger.critical(f"Failed to switch/create branch {self.branch}: {e}")
            raise

    def get_remote_url(self):
        try:
            if self.remote_name in [r.name for r in self.repo.remotes]:
                return self.repo.remote(name=self.remote_name).url
            return None
        except Exception as e:
            self.logger.error(f"Failed to get remote URL: {e}")
            return None

    def commit_and_push(self, files, commit_message):
        try:
            if isinstance(files, str):
                files = [files]
            
            self.repo.index.add(files)

            # Idempotency check: prevent empty commits
            has_changes = True
            try:
                if self.repo.head.is_valid() and not self.repo.index.diff(self.repo.head.commit):
                    has_changes = False
            except Exception:
                pass # First commit scenario

            if has_changes:
                self.repo.index.commit(commit_message)
                self.logger.info(f"Committed: {commit_message}")
            else:
                self.logger.info("No changes detected. Skipping commit.")

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

def configure_auth_from_remote(git_manager, logger):
    """Automatically configures Git authentication based on remote URL."""
    remote_url = git_manager.get_remote_url()
    
    if not remote_url:
        logger.warning("No remote URL found. Skipping auth configuration.")
        return

    # Check for SSH (git@... or ssh://...)
    if remote_url.startswith("git@") or remote_url.startswith("ssh://"):
        logger.info(f"Detected SSH remote: {remote_url}")
        # We rely on system SSH configuration (agent or ~/.ssh/config)
        # Clearing any potentially conflicting env vars
        os.environ.pop('GIT_SSH_COMMAND', None)
        
    # Check for HTTPS
    elif remote_url.startswith("http://") or remote_url.startswith("https://"):
        logger.info(f"Detected HTTPS remote: {remote_url}")
        # Ensure we don't force SSH
        os.environ.pop('GIT_SSH_COMMAND', None)
    
    else:
        logger.warning(f"Unknown remote protocol: {remote_url}. Assuming standard behavior.")

def main():
    # 1. Parse Arguments
    parser = argparse.ArgumentParser(description="Cisco Configuration Backup Tool")
    parser.add_argument(
        '--branch', 
        default='main', 
        help="Target git branch for backup (default: main)"
    )
    args = parser.parse_args()

    # 2. Setup Logging & Paths
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger = BackupLogger.setup_logging(os.path.join(PROJECT_ROOT, "logs"))
    
    BACKUP_REPO_DIR = os.getenv("BACKUP_REPO_PATH", PROJECT_ROOT)
    
    # 3. Initialize Git Manager & Configure Auth
    git_manager = GitManager(BACKUP_REPO_DIR, branch=args.branch)
    configure_auth_from_remote(git_manager, logger)

    SOURCE_DIR = os.getenv("SOURCE_CONFIG_DIR", os.path.join(PROJECT_ROOT, "source_configs"))
    
    logger.info("Starting backup...")

    try:
        # 4. Fetch Configs
        if not os.path.exists(SOURCE_DIR):
            logger.error(f"Source directory not found: {SOURCE_DIR}")
            sys.exit(1)

        backup_path = os.path.join(BACKUP_REPO_DIR, "backups")
        os.makedirs(backup_path, exist_ok=True)
        
        backup_files = []

        for filename in os.listdir(SOURCE_DIR):
            source_file = os.path.join(SOURCE_DIR, filename)
            
            # Skip directories, only process files
            if not os.path.isfile(source_file):
                continue
                
            device = CiscoDevice(source_file)
            config_content = device.get_config()

            # 5. Write to local storage
            target_file = os.path.join(backup_path, filename)
            
            with open(target_file, 'w') as f:
                f.write(config_content)
            
            backup_files.append(os.path.relpath(target_file, BACKUP_REPO_DIR))

        if not backup_files:
            logger.warning("No configuration files found to backup.")
            sys.exit(0)

        # 6. Sync to Git (Manager already initialized)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        git_manager.commit_and_push(backup_files, f"Auto-backup: {timestamp}")

        logger.info("Backup completed successfully.")

    except Exception as e:
        logger.critical(f"Backup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

