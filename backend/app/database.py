# app/database.py
"""
Enhanced Database Module for Chat History Management
Features: Connection pooling, error handling, context managers, and query optimization
"""

import os
import sqlite3
import logging
import time
from typing import List, Tuple, Optional, Dict, Any, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Database configuration
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chat_history.db'))
DB_TIMEOUT = 10  # seconds
DB_ISOLATION_LEVEL = None  # Autocommit mode for better performance

# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)


@dataclass
class ChatMessage:
    """Chat message data class"""
    id: Optional[int] = None
    doc_id: str = ""
    role: str = ""
    message: str = ""
    created_at: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    
    @property
    def timestamp(self) -> datetime:
        """Convert timestamp to datetime object"""
        return datetime.fromtimestamp(self.created_at)
    
    @property
    def formatted_time(self) -> str:
        """Get formatted timestamp"""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "role": self.role,
            "message": self.message,
            "created_at": self.created_at,
            "timestamp": self.formatted_time,
            "metadata": self.metadata
        }


class DatabaseError(Exception):
    """Custom database exception"""
    pass


@contextmanager
def get_connection(
    db_path: str = DB_PATH,
    timeout: int = DB_TIMEOUT
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections with proper error handling
    
    Args:
        db_path: Path to SQLite database
        timeout: Connection timeout in seconds
    
    Yields:
        SQLite connection object
    """
    conn = None
    try:
        conn = sqlite3.connect(
            db_path,
            timeout=timeout,
            isolation_level=DB_ISOLATION_LEVEL
        )
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise DatabaseError(f"Failed to connect to database: {e}")
    finally:
        if conn:
            conn.close()


def init_db(db_path: str = DB_PATH):
    """
    Initialize database with all required tables and indexes
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Create chats table with optimized schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata TEXT DEFAULT NULL,
                    updated_at REAL DEFAULT NULL
                )
            """)
            
            # Create indexes for better query performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chats_doc_id 
                ON chats(doc_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chats_created_at 
                ON chats(created_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chats_role 
                ON chats(role)
            """)
            
            # Create documents table for metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    page_count INTEGER,
                    word_count INTEGER,
                    uploaded_at REAL NOT NULL,
                    last_accessed REAL DEFAULT NULL,
                    total_questions INTEGER DEFAULT 0,
                    total_answers INTEGER DEFAULT 0
                )
            """)
            
            # Create indexes for documents
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at 
                ON documents(uploaded_at DESC)
            """)
            
            # Create analytics table for tracking usage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT DEFAULT NULL,
                    created_at REAL NOT NULL
                )
            """)
            
            # Create index for analytics
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_analytics_doc_id 
                ON analytics(doc_id)
            """)
            
            # Create table for cache entries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    doc_id TEXT DEFAULT NULL
                )
            """)
            
            # Create index for cache cleanup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_expires_at 
                ON cache_entries(expires_at)
            """)
            
            conn.commit()
            
        logger.info(f"Database initialized successfully at: {db_path}")
        
    except DatabaseError as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during initialization: {e}")
        raise


def add_chat_entry(
    doc_id: str,
    role: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: str = DB_PATH
) -> Optional[int]:
    """
    Add a chat entry to the database
    
    Args:
        doc_id: Document ID
        role: Message role (user, assistant, system, document)
        message: Message content
        metadata: Optional metadata dictionary
        db_path: Path to database
    
    Returns:
        ID of inserted record or None on failure
    """
    if not message or not message.strip():
        logger.warning("Attempted to add empty message")
        return None
    
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Serialize metadata if provided
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor.execute(
                """
                INSERT INTO chats (doc_id, role, message, created_at, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc_id, role, message.strip(), time.time(), metadata_json)
            )
            
            record_id = cursor.lastrowid
            
            # Update document last_accessed
            if role in ["user", "assistant"]:
                cursor.execute(
                    """
                    UPDATE documents 
                    SET last_accessed = ?,
                        total_questions = CASE WHEN ? THEN total_questions + 1 ELSE total_questions END,
                        total_answers = CASE WHEN ? THEN total_answers + 1 ELSE total_answers END
                    WHERE doc_id = ?
                    """,
                    (time.time(), role == "user", role == "assistant", doc_id)
                )
            
            conn.commit()
            logger.debug(f"Added chat entry for doc {doc_id} ({role})")
            return record_id
            
    except DatabaseError as e:
        logger.error(f"Failed to add chat entry: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error adding chat entry: {e}")
        return None


def get_history(
    doc_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
    role_filter: Optional[str] = None,
    db_path: str = DB_PATH
) -> List[ChatMessage]:
    """
    Get chat history for a document with pagination and filtering
    
    Args:
        doc_id: Document ID
        limit: Maximum number of records to return
        offset: Number of records to skip
        role_filter: Filter by role (user, assistant, system)
        db_path: Path to database
    
    Returns:
        List of ChatMessage objects
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Build query
            query = "SELECT id, doc_id, role, message, created_at, metadata FROM chats WHERE doc_id = ?"
            params = [doc_id]
            
            if role_filter:
                query += " AND role = ?"
                params.append(role_filter)
            
            query += " ORDER BY created_at ASC"
            
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                ChatMessage(
                    id=row['id'],
                    doc_id=row['doc_id'],
                    role=row['role'],
                    message=row['message'],
                    created_at=row['created_at'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                )
                for row in rows
            ]
            
    except DatabaseError as e:
        logger.error(f"Failed to get history: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting history: {e}")
        return []


def get_conversation_summary(doc_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get summary statistics for a conversation
    
    Args:
        doc_id: Document ID
        db_path: Path to database
    
    Returns:
        Dictionary with conversation statistics
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Get message counts by role
            cursor.execute(
                """
                SELECT role, COUNT(*) as count 
                FROM chats 
                WHERE doc_id = ? 
                GROUP BY role
                """,
                (doc_id,)
            )
            role_counts = {row['role']: row['count'] for row in cursor.fetchall()}
            
            # Get total messages
            cursor.execute(
                "SELECT COUNT(*) as total FROM chats WHERE doc_id = ?",
                (doc_id,)
            )
            total = cursor.fetchone()['total']
            
            # Get first and last message times
            cursor.execute(
                """
                SELECT 
                    MIN(created_at) as first,
                    MAX(created_at) as last
                FROM chats 
                WHERE doc_id = ?
                """,
                (doc_id,)
            )
            times = cursor.fetchone()
            
            return {
                "doc_id": doc_id,
                "total_messages": total,
                "user_messages": role_counts.get("user", 0),
                "assistant_messages": role_counts.get("assistant", 0),
                "system_messages": role_counts.get("system", 0),
                "first_message_at": times['first'],
                "last_message_at": times['last'],
                "conversation_duration": times['last'] - times['first'] if times['first'] and times['last'] else 0
            }
            
    except DatabaseError as e:
        logger.error(f"Failed to get conversation summary: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error getting conversation summary: {e}")
        return {}


def clear_history(doc_id: str, db_path: str = DB_PATH):
    """
    Clear all chat history for a document
    
    Args:
        doc_id: Document ID
        db_path: Path to database
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chats WHERE doc_id = ?", (doc_id,))
            cursor.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()
        logger.info(f"Cleared history for document: {doc_id}")
        
    except DatabaseError as e:
        logger.error(f"Failed to clear history: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error clearing history: {e}")
        raise


def delete_message(message_id: int, db_path: str = DB_PATH) -> bool:
    """
    Delete a specific message by ID
    
    Args:
        message_id: Message ID to delete
        db_path: Path to database
    
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chats WHERE id = ?", (message_id,))
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Deleted message {message_id}")
                return True
            else:
                logger.warning(f"Message {message_id} not found")
                return False
                
    except DatabaseError as e:
        logger.error(f"Failed to delete message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting message: {e}")
        return False


def add_document_metadata(
    doc_id: str,
    file_name: str,
    file_size: int,
    page_count: int = 0,
    word_count: int = 0,
    db_path: str = DB_PATH
):
    """
    Add or update document metadata
    
    Args:
        doc_id: Document ID
        file_name: Original filename
        file_size: File size in bytes
        page_count: Number of pages
        word_count: Number of words
        db_path: Path to database
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO documents 
                (doc_id, file_name, file_size, page_count, word_count, uploaded_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, file_name, file_size, page_count, word_count, time.time(), time.time())
            )
            conn.commit()
            logger.debug(f"Added metadata for document: {doc_id}")
            
    except DatabaseError as e:
        logger.error(f"Failed to add document metadata: {e}")
    except Exception as e:
        logger.error(f"Unexpected error adding document metadata: {e}")


def get_document_metadata(doc_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Get document metadata
    
    Args:
        doc_id: Document ID
        db_path: Path to database
    
    Returns:
        Dictionary with document metadata or None if not found
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT doc_id, file_name, file_size, page_count, word_count, uploaded_at, last_accessed,
                       total_questions, total_answers
                FROM documents 
                WHERE doc_id = ?
                """,
                (doc_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return {
                    "doc_id": row['doc_id'],
                    "file_name": row['file_name'],
                    "file_size": row['file_size'],
                    "page_count": row['page_count'],
                    "word_count": row['word_count'],
                    "uploaded_at": row['uploaded_at'],
                    "last_accessed": row['last_accessed'],
                    "total_questions": row['total_questions'] or 0,
                    "total_answers": row['total_answers'] or 0
                }
            return None
            
    except DatabaseError as e:
        logger.error(f"Failed to get document metadata: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting document metadata: {e}")
        return None


def list_documents(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    List all documents with metadata
    
    Args:
        db_path: Path to database
    
    Returns:
        List of document metadata dictionaries
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT doc_id, file_name, file_size, page_count, word_count, uploaded_at, last_accessed,
                       total_questions, total_answers
                FROM documents 
                ORDER BY uploaded_at DESC
                """
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "doc_id": row['doc_id'],
                    "file_name": row['file_name'],
                    "file_size": row['file_size'],
                    "page_count": row['page_count'],
                    "word_count": row['word_count'],
                    "uploaded_at": row['uploaded_at'],
                    "last_accessed": row['last_accessed'],
                    "total_questions": row['total_questions'] or 0,
                    "total_answers": row['total_answers'] or 0
                }
                for row in rows
            ]
            
    except DatabaseError as e:
        logger.error(f"Failed to list documents: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error listing documents: {e}")
        return []


def add_analytics_event(
    doc_id: str,
    event_type: str,
    event_data: Optional[Dict[str, Any]] = None,
    db_path: str = DB_PATH
):
    """
    Add an analytics event
    
    Args:
        doc_id: Document ID
        event_type: Type of event (upload, ask, etc.)
        event_data: Optional event data
        db_path: Path to database
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analytics (doc_id, event_type, event_data, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (doc_id, event_type, json.dumps(event_data) if event_data else None, time.time())
            )
            conn.commit()
            logger.debug(f"Added analytics event: {event_type}")
            
    except DatabaseError as e:
        logger.error(f"Failed to add analytics event: {e}")
    except Exception as e:
        logger.error(f"Unexpected error adding analytics event: {e}")


def get_analytics_summary(doc_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get analytics summary for a document
    
    Args:
        doc_id: Document ID
        db_path: Path to database
    
    Returns:
        Dictionary with analytics summary
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Get event counts by type
            cursor.execute(
                """
                SELECT event_type, COUNT(*) as count 
                FROM analytics 
                WHERE doc_id = ? 
                GROUP BY event_type
                """,
                (doc_id,)
            )
            event_counts = {row['event_type']: row['count'] for row in cursor.fetchall()}
            
            return {
                "doc_id": doc_id,
                "total_events": sum(event_counts.values()),
                "event_counts": event_counts
            }
            
    except DatabaseError as e:
        logger.error(f"Failed to get analytics summary: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error getting analytics summary: {e}")
        return {}


def cleanup_cache(db_path: str = DB_PATH):
    """
    Remove expired cache entries
    
    Args:
        db_path: Path to database
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cache_entries WHERE expires_at < ?",
                (time.time(),)
            )
            deleted = cursor.rowcount
            conn.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired cache entries")
                
    except DatabaseError as e:
        logger.error(f"Failed to cleanup cache: {e}")
    except Exception as e:
        logger.error(f"Unexpected error cleaning up cache: {e}")


def get_db_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get database statistics
    
    Args:
        db_path: Path to database
    
    Returns:
        Dictionary with database statistics
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Count messages
            cursor.execute("SELECT COUNT(*) FROM chats")
            stats["total_messages"] = cursor.fetchone()[0]
            
            # Count unique documents
            cursor.execute("SELECT COUNT(DISTINCT doc_id) FROM chats")
            stats["total_documents"] = cursor.fetchone()[0]
            
            # Count messages by role
            cursor.execute("SELECT role, COUNT(*) FROM chats GROUP BY role")
            stats["messages_by_role"] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get database size
            db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            stats["database_size_bytes"] = db_size
            stats["database_size_mb"] = db_size / (1024 * 1024)
            
            return stats
            
    except DatabaseError as e:
        logger.error(f"Failed to get database stats: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error getting database stats: {e}")
        return {}


# Backward compatibility functions
def get_history_legacy(doc_id: str, db_path: str = DB_PATH) -> List[Tuple[float, str, str]]:
    """
    Legacy function to maintain backward compatibility
    
    Args:
        doc_id: Document ID
        db_path: Path to database
    
    Returns:
        List of tuples (created_at, role, message)
    """
    messages = get_history(doc_id, db_path=db_path)
    return [(msg.created_at, msg.role, msg.message) for msg in messages]

# Initialize database on import if needed
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")