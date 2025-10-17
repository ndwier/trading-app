"""Database connection and session management."""

from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging

from config.config import config
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager.
        
        Args:
            database_url: Database URL. If None, uses config.database.DATABASE_URL
        """
        self.database_url = database_url or config.database.DATABASE_URL
        self.engine = None
        self.SessionLocal = None
        self._initialize_engine()
        
    def _initialize_engine(self):
        """Initialize SQLAlchemy engine and session factory."""
        # Engine configuration based on database type
        if self.database_url.startswith("sqlite"):
            # SQLite specific settings
            self.engine = create_engine(
                self.database_url,
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 20
                },
                echo=config.web.DEBUG
            )
            # Enable foreign key constraints for SQLite
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
                
        elif self.database_url.startswith("postgresql"):
            # PostgreSQL specific settings
            self.engine = create_engine(
                self.database_url,
                pool_size=config.database.POOL_SIZE,
                max_overflow=config.database.MAX_OVERFLOW,
                pool_pre_ping=True,
                echo=config.web.DEBUG
            )
        else:
            # Generic settings
            self.engine = create_engine(
                self.database_url,
                echo=config.web.DEBUG
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database engine initialized with URL: {self._mask_url(self.database_url)}")
    
    def _mask_url(self, url: str) -> str:
        """Mask sensitive information in database URL for logging."""
        if "://" in url and "@" in url:
            parts = url.split("://")
            if len(parts) == 2:
                scheme, rest = parts
                if "@" in rest:
                    creds, host = rest.split("@", 1)
                    return f"{scheme}://***:***@{host}"
        return url
    
    def create_tables(self):
        """Create all database tables."""
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")
    
    def drop_tables(self):
        """Drop all database tables. USE WITH CAUTION!"""
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup.
        
        Yields:
            Session: SQLAlchemy session
            
        Example:
            with db_manager.get_session() as session:
                user = session.query(Filer).first()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def execute_raw_sql(self, sql: str, params: Optional[dict] = None):
        """Execute raw SQL statement.
        
        Args:
            sql: SQL statement to execute
            params: Optional parameters for the SQL statement
            
        Returns:
            Result of the SQL execution
        """
        with self.engine.connect() as connection:
            return connection.execute(sql, params or {})
    
    def get_table_info(self) -> dict:
        """Get information about database tables.
        
        Returns:
            Dictionary with table names and row counts
        """
        info = {}
        with self.get_session() as session:
            for table_name in Base.metadata.tables.keys():
                try:
                    count = session.execute(f"SELECT COUNT(*) FROM {table_name}").scalar()
                    info[table_name] = count
                except Exception as e:
                    info[table_name] = f"Error: {e}"
        return info


# Global database manager instance
_db_manager = None


def get_database_manager() -> DatabaseManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Convenience function to get a database session.
    
    Yields:
        Session: SQLAlchemy session
        
    Example:
        from src.database import get_session
        
        with get_session() as session:
            trades = session.query(Trade).limit(10).all()
    """
    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        yield session


def initialize_database():
    """Initialize the database with tables and indexes."""
    db_manager = get_database_manager()
    db_manager.create_tables()
    
    # Create any additional indexes or views
    logger.info("Database initialization complete")


def reset_database():
    """Reset the database by dropping and recreating all tables.
    
    WARNING: This will delete all data!
    """
    db_manager = get_database_manager()
    db_manager.drop_tables()
    db_manager.create_tables()
    logger.warning("Database has been reset - all data deleted!")


if __name__ == "__main__":
    # CLI for database operations
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "init":
            initialize_database()
            print("Database initialized successfully")
        elif command == "reset":
            confirm = input("This will delete all data. Type 'YES' to confirm: ")
            if confirm == "YES":
                reset_database()
                print("Database reset successfully")
            else:
                print("Operation cancelled")
        elif command == "info":
            db_manager = get_database_manager()
            info = db_manager.get_table_info()
            print("\nDatabase Table Information:")
            print("-" * 40)
            for table, count in info.items():
                print(f"{table}: {count}")
        else:
            print("Available commands: init, reset, info")
    else:
        print("Usage: python connection.py [init|reset|info]")
