#!/usr/bin/env python3
"""Database setup and initialization script."""

import sys
import os
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import DatabaseManager, initialize_database
from config.config import config


def setup_logging():
    """Setup logging for the setup script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def create_directories():
    """Create necessary directories."""
    logger = logging.getLogger(__name__)
    
    directories = [
        config.scraping.RAW_DATA_DIR,
        config.scraping.PROCESSED_DATA_DIR,
        config.logging.LOG_DIR,
        project_root / "data" / "backtest_results",
        project_root / "data" / "exports"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {directory}")


def setup_database():
    """Initialize database with tables."""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Initializing database...")
        initialize_database()
        
        # Test connection
        db_manager = DatabaseManager()
        with db_manager.get_session() as session:
            logger.info("Database connection successful")
        
        # Show table info
        table_info = db_manager.get_table_info()
        logger.info("Database tables created:")
        for table, count in table_info.items():
            logger.info(f"  {table}: {count} rows")
        
        return True
        
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        return False


def check_environment():
    """Check environment configuration."""
    logger = logging.getLogger(__name__)
    
    logger.info("Checking environment configuration...")
    
    # Check database URL
    db_url = config.database.DATABASE_URL
    if db_url.startswith("sqlite"):
        logger.info(f"Using SQLite database: {db_url}")
        
        # Ensure SQLite file directory exists
        if ":///" in db_url:
            db_path = Path(db_url.split("///")[1])
            db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        logger.info(f"Using external database: {db_url.split('@')[0]}@***")
    
    # Check API keys
    api_keys = {
        "Quiver": config.api.QUIVER_API_KEY,
        "Finnhub": config.api.FINNHUB_API_KEY,
        "Alpha Vantage": config.api.ALPHA_VANTAGE_API_KEY
    }
    
    for name, key in api_keys.items():
        if key:
            logger.info(f"✓ {name} API key configured")
        else:
            logger.warning(f"✗ {name} API key not configured (optional)")
    
    # Check data directories
    logger.info(f"Raw data directory: {config.scraping.RAW_DATA_DIR}")
    logger.info(f"Processed data directory: {config.scraping.PROCESSED_DATA_DIR}")
    logger.info(f"Log directory: {config.logging.LOG_DIR}")
    
    return True


def create_sample_data():
    """Create some sample data for testing."""
    logger = logging.getLogger(__name__)
    
    try:
        from src.database import get_session, Filer, FilerType
        
        with get_session() as session:
            # Check if sample data already exists
            existing = session.query(Filer).first()
            if existing:
                logger.info("Sample data already exists")
                return True
            
            # Create sample filers
            sample_filers = [
                {
                    "name": "Nancy Pelosi",
                    "filer_type": FilerType.POLITICIAN,
                    "party": "Democrat",
                    "state": "CA",
                    "chamber": "House",
                    "position": "Former Speaker"
                },
                {
                    "name": "Paul Pelosi",
                    "filer_type": FilerType.POLITICIAN,
                    "party": "Democrat", 
                    "state": "CA"
                },
                {
                    "name": "Elon Musk",
                    "filer_type": FilerType.CORPORATE_INSIDER,
                    "company": "Tesla Inc",
                    "title": "CEO"
                }
            ]
            
            for filer_data in sample_filers:
                filer = Filer(**filer_data)
                session.add(filer)
            
            session.commit()
            logger.info(f"Created {len(sample_filers)} sample filers")
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")
        return False


def main():
    """Main setup function."""
    logger = setup_logging()
    
    logger.info("Starting Trading App database setup...")
    
    success = True
    
    # Step 1: Check environment
    logger.info("\n=== Step 1: Environment Check ===")
    if not check_environment():
        success = False
    
    # Step 2: Create directories
    logger.info("\n=== Step 2: Create Directories ===")
    try:
        create_directories()
    except Exception as e:
        logger.error(f"Failed to create directories: {e}")
        success = False
    
    # Step 3: Setup database
    logger.info("\n=== Step 3: Database Setup ===")
    if not setup_database():
        success = False
    
    # Step 4: Create sample data
    logger.info("\n=== Step 4: Sample Data ===")
    if not create_sample_data():
        logger.warning("Sample data creation failed (non-critical)")
    
    # Summary
    logger.info("\n" + "="*50)
    if success:
        logger.info("✓ Setup completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Copy env_template.txt to .env and configure API keys")
        logger.info("2. Run data ingestion: python -m src.ingestion.politician_scraper")
        logger.info("3. Start web interface: python app.py")
    else:
        logger.error("✗ Setup failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
