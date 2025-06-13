#!/usr/bin/env python3
"""
Interactive Setup Wizard for Doc-Monitor-MCP
============================================

This wizard guides users through the complete setup process including:
- Environment configuration
- API key setup
- Database configuration
- Dependency installation
- Health checks

Usage:
    python scripts/setup.py
    python scripts/setup.py --auto  # Non-interactive mode with defaults
"""

import os
import sys
import asyncio
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import getpass
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

class Colors:
    """ANSI color codes for terminal output."""
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class SetupWizard:
    """Interactive setup wizard for Doc-Monitor-MCP."""
    
    def __init__(self, auto_mode: bool = False):
        self.auto_mode = auto_mode
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self.env_template = self.project_root / "env.template"
        self.config = {}
        
    def print_header(self, title: str):
        """Print a formatted header."""
        print(f"\n{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"{Colors.BLUE}{Colors.BOLD}{title.center(60)}{Colors.END}")
        print(f"{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.END}\n")
    
    def print_step(self, step: str, description: str):
        """Print a step description."""
        print(f"{Colors.GREEN}{Colors.BOLD}🔧 {step}{Colors.END}")
        print(f"   {description}\n")
    
    def print_success(self, message: str):
        """Print a success message."""
        print(f"{Colors.GREEN}✅ {message}{Colors.END}")
    
    def print_warning(self, message: str):
        """Print a warning message."""
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
    
    def print_error(self, message: str):
        """Print an error message."""
        print(f"{Colors.RED}❌ {message}{Colors.END}")
    
    def get_input(self, prompt: str, default: str = None, required: bool = True, password: bool = False) -> str:
        """Get user input with validation."""
        if self.auto_mode and default:
            return default
            
        while True:
            if password:
                if default:
                    value = getpass.getpass(f"{prompt} (default: {default}): ")
                else:
                    value = getpass.getpass(f"{prompt}: ")
            else:
                if default:
                    value = input(f"{prompt} (default: {default}): ").strip()
                else:
                    value = input(f"{prompt}: ").strip()
            
            if not value and default:
                return default
            elif not value and required:
                self.print_error("This field is required. Please enter a value.")
                continue
            elif not value and not required:
                return ""
            else:
                return value
    
    def get_yes_no(self, prompt: str, default: bool = True) -> bool:
        """Get yes/no input from user."""
        if self.auto_mode:
            return default
            
        default_str = "Y/n" if default else "y/N"
        while True:
            response = input(f"{prompt} ({default_str}): ").strip().lower()
            if not response:
                return default
            elif response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                self.print_error("Please enter 'y' or 'n'")
    
    def check_system_requirements(self) -> bool:
        """Check system requirements."""
        self.print_step("System Requirements", "Checking system requirements...")
        
        # Check Python version
        python_version = sys.version_info
        if python_version.major == 3 and python_version.minor >= 12:
            self.print_success(f"Python {python_version.major}.{python_version.minor} - OK")
        else:
            self.print_error(f"Python 3.12+ required, found {python_version.major}.{python_version.minor}")
            return False
        
        # Check if uv is available
        try:
            subprocess.run(['uv', '--version'], capture_output=True, check=True)
            self.print_success("uv package manager - OK")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.print_warning("uv not found - will try to install")
            if not self.install_uv():
                return False
        
        # Check internet connectivity
        try:
            urllib.request.urlopen('https://google.com', timeout=5)
            self.print_success("Internet connectivity - OK")
        except:
            self.print_error("No internet connection")
            return False
        
        return True
    
    def install_uv(self) -> bool:
        """Install uv package manager."""
        try:
            self.print_step("Installing uv", "Installing uv package manager...")
            
            # Try pip install first
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'uv'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                self.print_success("uv installed successfully")
                return True
            else:
                self.print_error(f"Failed to install uv: {result.stderr}")
                return False
                
        except Exception as e:
            self.print_error(f"Error installing uv: {e}")
            return False
    
    def setup_environment_config(self):
        """Set up environment configuration."""
        self.print_step("Environment Configuration", 
                       "Setting up your environment variables...")
        
        # Check if .env already exists
        if self.env_file.exists():
            if not self.auto_mode:
                overwrite = self.get_yes_no("🔄 .env file already exists. Overwrite it?", False)
                if not overwrite:
                    self.print_warning("Keeping existing .env file")
                    return
        
        # Get configuration values
        print(f"\n{Colors.BOLD}📝 Configuration Values{Colors.END}")
        print("Please provide the following information:")
        
        # OpenAI Configuration
        print(f"\n{Colors.UNDERLINE}OpenAI Configuration{Colors.END}")
        print("Get your API key from: https://platform.openai.com/api-keys")
        
        openai_key = self.get_input(
            "🔑 OpenAI API Key",
            required=True,
            password=True
        )
        
        openai_model = self.get_input(
            "🤖 OpenAI Model",
            default="gpt-4o-mini",
            required=False
        )
        
        # Supabase Configuration
        print(f"\n{Colors.UNDERLINE}Supabase Configuration{Colors.END}")
        print("Get these from: Supabase Dashboard → Settings → API")
        
        supabase_url = self.get_input(
            "🌐 Supabase Project URL",
            required=True
        )
        
        supabase_key = self.get_input(
            "🔐 Supabase Service Role Key (NOT anon key!)",
            required=True,
            password=True
        )
        
        # Server Configuration
        print(f"\n{Colors.UNDERLINE}Server Configuration{Colors.END}")
        
        host = self.get_input(
            "🖥️  Server Host",
            default="0.0.0.0",
            required=False
        )
        
        port = self.get_input(
            "🔌 Server Port",
            default="8051",
            required=False
        )
        
        transport = self.get_input(
            "🚀 Transport Method (sse/stdio)",
            default="sse",
            required=False
        )
        
        # Advanced Configuration (optional)
        advanced = False
        if not self.auto_mode:
            advanced = self.get_yes_no("\n⚙️  Configure advanced settings?", False)
        
        max_concurrent = "10"
        max_depth = "3"
        chunk_size = "5000"
        
        if advanced:
            print(f"\n{Colors.UNDERLINE}Advanced Configuration{Colors.END}")
            
            max_concurrent = self.get_input(
                "🔄 Max Concurrent Operations",
                default="10",
                required=False
            )
            
            max_depth = self.get_input(
                "📊 Max Crawling Depth",
                default="3",
                required=False
            )
            
            chunk_size = self.get_input(
                "📄 Document Chunk Size",
                default="5000",
                required=False
            )
        
        # Store configuration
        self.config = {
            'OPENAI_API_KEY': openai_key,
            'MODEL_CHOICE': openai_model,
            'SUPABASE_URL': supabase_url,
            'SUPABASE_SERVICE_KEY': supabase_key,
            'HOST': host,
            'PORT': port,
            'TRANSPORT': transport,
            'MAX_CONCURRENT': max_concurrent,
            'MAX_DEPTH': max_depth,
            'CHUNK_SIZE': chunk_size,
            'DEBUG': 'false',
            'VERBOSE_CRAWLING': 'false',
            'AUTO_SETUP_DB': 'false',
            'SETUP_COMPLETED': 'true'
        }
        
        # Write .env file
        self.write_env_file()
    
    def write_env_file(self):
        """Write the .env file with configuration."""
        try:
            env_content = f"""# ====================================================================
# Doc-Monitor-MCP Environment Configuration
# ====================================================================
# Generated by setup wizard on {datetime.now().isoformat()}
# 
# For help, run: make validate
# ====================================================================

# ====================================================================
# SERVER CONFIGURATION
# ====================================================================
HOST={self.config['HOST']}
PORT={self.config['PORT']}
TRANSPORT={self.config['TRANSPORT']}

# ====================================================================
# OPENAI API CONFIGURATION
# ====================================================================
OPENAI_API_KEY={self.config['OPENAI_API_KEY']}
MODEL_CHOICE={self.config['MODEL_CHOICE']}

# ====================================================================
# SUPABASE DATABASE CONFIGURATION  
# ====================================================================
SUPABASE_URL={self.config['SUPABASE_URL']}
SUPABASE_SERVICE_KEY={self.config['SUPABASE_SERVICE_KEY']}

# ====================================================================
# CRAWLING CONFIGURATION
# ====================================================================
MAX_CONCURRENT={self.config['MAX_CONCURRENT']}
MAX_DEPTH={self.config['MAX_DEPTH']}
CHUNK_SIZE={self.config['CHUNK_SIZE']}

# ====================================================================
# DEVELOPMENT CONFIGURATION
# ====================================================================
DEBUG={self.config['DEBUG']}
VERBOSE_CRAWLING={self.config['VERBOSE_CRAWLING']}
AUTO_SETUP_DB={self.config['AUTO_SETUP_DB']}

# ====================================================================
# SETUP VERIFICATION
# ====================================================================
SETUP_COMPLETED={self.config['SETUP_COMPLETED']}
"""
            
            with open(self.env_file, 'w') as f:
                f.write(env_content)
            
            self.print_success(f"Environment configuration saved to {self.env_file}")
            
        except Exception as e:
            self.print_error(f"Failed to write .env file: {e}")
    
    def install_dependencies(self) -> bool:
        """Install Python dependencies."""
        self.print_step("Dependencies", "Installing Python dependencies...")
        
        try:
            # Install dependencies using uv
            result = subprocess.run(
                ['uv', 'pip', 'install', '-e', '.'],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.print_success("Dependencies installed successfully")
                
                # Also install crawl4ai setup
                print("🔧 Setting up Crawl4AI...")
                setup_result = subprocess.run(
                    ['crawl4ai-setup'],
                    capture_output=True,
                    text=True
                )
                
                if setup_result.returncode == 0:
                    self.print_success("Crawl4AI setup completed")
                else:
                    self.print_warning("Crawl4AI setup had issues, but continuing...")
                
                return True
            else:
                self.print_error(f"Dependency installation failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.print_error(f"Error installing dependencies: {e}")
            return False
    
    async def setup_database(self) -> bool:
        """Set up the database schema."""
        self.print_step("Database Setup", "Setting up database schema...")
        
        try:
            # Import and run database setup
            sys.path.insert(0, str(self.project_root / "scripts"))
            from db_setup import DatabaseSetup
            
            db_setup = DatabaseSetup()
            success = await db_setup.run_setup()
            
            if success:
                self.print_success("Database schema set up successfully")
                return True
            else:
                self.print_error("Database setup failed")
                return False
                
        except Exception as e:
            self.print_error(f"Database setup error: {e}")
            return False
    
    async def validate_setup(self) -> bool:
        """Validate the complete setup."""
        self.print_step("Validation", "Validating setup...")
        
        try:
            # Import and run validation
            sys.path.insert(0, str(self.project_root / "scripts"))
            from validate_env import EnvironmentValidator
            
            validator = EnvironmentValidator()
            success = await validator.run_validation()
            
            return success
            
        except Exception as e:
            self.print_error(f"Validation error: {e}")
            return False
    
    def print_next_steps(self):
        """Print next steps for the user."""
        self.print_header("🎉 Setup Complete!")
        
        print(f"{Colors.GREEN}Your Doc-Monitor-MCP is ready to use!{Colors.END}\n")
        
        print(f"{Colors.BOLD}🚀 Next Steps:{Colors.END}")
        print("1. Start the MCP server:")
        print(f"   {Colors.BLUE}make dev{Colors.END} or {Colors.BLUE}uv run src/doc_fetcher_mcp.py{Colors.END}")
        print("")
        print("2. Add to your AI client (e.g., Claude Desktop):")
        print(f"   {Colors.BLUE}See configs/ directory for ready-to-use configurations{Colors.END}")
        print("")
        print("3. Test the system:")
        print(f"   {Colors.BLUE}make health-check{Colors.END}")
        print("")
        print("4. Monitor documentation:")
        print(f"   Use the monitor_documentation MCP tool")
        print("")
        
        print(f"{Colors.BOLD}📚 Documentation:{Colors.END}")
        print("- README.md - Complete setup and usage guide")
        print("- Run 'make help' for available commands")
        print("")
        
        print(f"{Colors.BOLD}🔧 Troubleshooting:{Colors.END}")
        print("- Run 'make validate' to check configuration")
        print("- Run 'make health-check --full' for detailed diagnostics")
        print("- Check logs if the server doesn't start")
    
    async def run_setup(self) -> bool:
        """Run the complete setup process."""
        self.print_header("🛠️ Doc-Monitor-MCP Setup Wizard")
        
        if not self.auto_mode:
            print(f"{Colors.BOLD}Welcome to the Doc-Monitor-MCP Setup Wizard!{Colors.END}")
            print("This wizard will guide you through the complete setup process.\n")
            
            if not self.get_yes_no("🚀 Ready to begin setup?", True):
                print("Setup cancelled.")
                return False
        
        # Step 1: System requirements
        if not self.check_system_requirements():
            self.print_error("System requirements not met. Please fix issues and try again.")
            return False
        
        # Step 2: Environment configuration
        self.setup_environment_config()
        
        # Step 3: Install dependencies
        if not self.install_dependencies():
            self.print_error("Dependency installation failed.")
            return False
        
        # Step 4: Database setup
        if not await self.setup_database():
            self.print_warning("Database setup requires manual intervention.")
            print(f"\n{Colors.YELLOW}📋 NEXT STEPS:{Colors.END}")
            print("1. Open your Supabase project dashboard")
            print("2. Go to SQL Editor")
            print("3. Copy and paste the contents of 'crawled_pages.sql'")
            print("4. Execute the SQL")
            print("5. Run 'make db-validate' to verify")
            print("")
            
            continue_anyway = self.get_yes_no("Continue setup without database? You can set it up later", True)
            if not continue_anyway:
                return False
        
        # Step 5: Validation
        if not await self.validate_setup():
            self.print_warning("Setup validation had issues, but basic setup is complete.")
        
        # Success!
        self.print_next_steps()
        return True

def main():
    """Main setup function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive setup wizard for Doc-Monitor-MCP")
    parser.add_argument("--auto", action="store_true",
                       help="Run in automatic mode with defaults (non-interactive)")
    
    args = parser.parse_args()
    
    wizard = SetupWizard(auto_mode=args.auto)
    
    try:
        success = asyncio.run(wizard.run_setup())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup cancelled by user.{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Setup failed with error: {e}{Colors.END}")
        sys.exit(1)

if __name__ == "__main__":
    main() 