# # from sqlmodel import Session, text  # pyright: ignore[reportMissingImports] 
# # from models.database import engine

# # # Run the migration
# # with Session(engine) as session:
# #     session.execute(text("""
# #         ALTER TABLE voicebotmeta 
# #         ADD COLUMN company_name TEXT 
# #         DEFAULT ''
# #     """)) 
# #     session.commit()

# # print("Migration completed successfully!")

# # from sqlmodel import SQLModel, create_engine # pyright: ignore[reportMissingImports]
# # from models.api_keys import BotAPIKey
# # from config.settings import DATABASE_URL

# # # Create tables
# # engine = create_engine(DATABASE_URL)
# # SQLModel.metadata.create_all(engine)

# # print("✅ API keys table created successfully!")

# from sqlmodel import SQLModel # pyright: ignore[reportMissingImports]
# from models.database import engine
# from models.plivo_numbers import AccountPhoneNumber, IncomingCarrier
# from models.voice_bot import VoiceBotMeta, VoiceCallAnalytics

# def create_plivo_tables():
#     """
#     Create the new Plivo-related tables in the database
#     Run this script once to create the tables
#     """

#     print("Creating Plivo-related tables...")
    
#     # Create all tables
#     SQLModel.metadata.create_all(engine)
    
#     print("✓ AccountPhoneNumber table created")
#     print("✓ IncomingCarrier table created")
#     print("✓ All tables created successfully!")

# if __name__ == "__main__":
#     create_plivo_tables()

# migration.py
"""
Database Migration Script - Fixed Version
Adds missing columns to tables without deleting any data
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Your database path
DATABASE_PATH = Path("bots.db")

if not DATABASE_PATH.exists():
    print(f"Error: Database file not found at: {DATABASE_PATH.absolute()}")
    print("Please make sure 'bots.db' exists in the current directory.")
    print(f"Current directory: {Path.cwd()}")
    sys.exit(1)

print(f"Database found at: {DATABASE_PATH.absolute()}")
print("Starting migration...")

# Connect to the database
conn = sqlite3.connect(str(DATABASE_PATH))
cursor = conn.cursor()

try:
    # 1. Check current schema of websitebotmeta
    print("\n1. Checking websitebotmeta table...")
    cursor.execute("PRAGMA table_info(websitebotmeta)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"   Current columns: {columns}")
    
    if 'is_active' not in columns:
        print("   Adding 'is_active' column...")
        cursor.execute("ALTER TABLE websitebotmeta ADD COLUMN is_active BOOLEAN DEFAULT FALSE")
        print("   ✓ Column added")
    else:
        print("   ✓ 'is_active' column already exists")
    
    # 2. Check voicebotmeta
    print("\n2. Checking voicebotmeta table...")
    cursor.execute("PRAGMA table_info(voicebotmeta)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"   Current columns: {columns}")
    
    if 'is_active' not in columns:
        print("   Adding 'is_active' column...")
        cursor.execute("ALTER TABLE voicebotmeta ADD COLUMN is_active BOOLEAN DEFAULT FALSE")
        print("   ✓ Column added")
    else:
        print("   ✓ 'is_active' column already exists")
    
    # 3. Check whatsappbotmeta
    print("\n3. Checking whatsappbotmeta table...")
    cursor.execute("PRAGMA table_info(whatsappbotmeta)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"   Current columns: {columns}")
    
    # Add is_active if missing
    if 'is_active' not in columns:
        print("   Adding 'is_active' column...")
        cursor.execute("ALTER TABLE whatsappbotmeta ADD COLUMN is_active BOOLEAN DEFAULT FALSE")
        print("   ✓ 'is_active' column added")
    else:
        print("   ✓ 'is_active' column already exists")
    
    # Add last_active_toggle if missing
    if 'last_active_toggle' not in columns:
        print("   Adding 'last_active_toggle' column...")
        cursor.execute("ALTER TABLE whatsappbotmeta ADD COLUMN last_active_toggle TIMESTAMP")
        print("   ✓ 'last_active_toggle' column added")
    else:
        print("   ✓ 'last_active_toggle' column already exists")
    
    # 4. Add other missing columns for whatsappbotmeta
    print("\n4. Adding other WhatsApp columns if missing...")
    whatsapp_columns_needed = [
        ('waba_id', 'TEXT'),
        ('phone_number_id', 'TEXT'),
        ('phone_number', 'TEXT'),
        ('business_id', 'TEXT'),
        ('whatsapp_status', 'TEXT DEFAULT "pending"'),
        ('webhook_configured', 'BOOLEAN DEFAULT FALSE'),
        ('created_at', 'TIMESTAMP'),
        ('updated_at', 'TIMESTAMP')
    ]
    
    cursor.execute("PRAGMA table_info(whatsappbotmeta)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    for column_name, column_type in whatsapp_columns_needed:
        if column_name not in existing_columns:
            print(f"   Adding '{column_name}' column...")
            cursor.execute(f"ALTER TABLE whatsappbotmeta ADD COLUMN {column_name} {column_type}")
            print(f"   ✓ '{column_name}' column added")
        else:
            print(f"   ✓ '{column_name}' column already exists")
    
    # 5. Set all existing bots to inactive for safety
    print("\n5. Setting all existing bots to inactive...")
    
    # Website bots
    cursor.execute("UPDATE websitebotmeta SET is_active = FALSE WHERE is_active IS NULL OR is_active = TRUE")
    website_count = cursor.rowcount
    print(f"   Updated {website_count} website bots")
    
    # Voice bots
    cursor.execute("UPDATE voicebotmeta SET is_active = FALSE WHERE is_active IS NULL OR is_active = TRUE")
    voice_count = cursor.rowcount
    print(f"   Updated {voice_count} voice bots")
    
    # WhatsApp bots
    cursor.execute("UPDATE whatsappbotmeta SET is_active = FALSE WHERE is_active IS NULL OR is_active = TRUE")
    whatsapp_count = cursor.rowcount
    print(f"   Updated {whatsapp_count} WhatsApp bots")
    
    # 6. Update timestamps for existing WhatsApp bots if needed
    print("\n6. Updating timestamps for existing bots...")
    
    # Check if we need to set created_at for existing whatsapp bots
    cursor.execute("SELECT COUNT(*) FROM whatsappbotmeta WHERE created_at IS NULL")
    null_timestamps = cursor.fetchone()[0]
    if null_timestamps > 0:
        current_time = datetime.now().isoformat()
        cursor.execute("UPDATE whatsappbotmeta SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        print(f"   Updated timestamps for {null_timestamps} WhatsApp bots")
    
    # 7. Verify the changes
    print("\n7. Verifying migration...")
    
    # Check websitebotmeta
    cursor.execute("SELECT COUNT(*) FROM websitebotmeta")
    total_website = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM websitebotmeta WHERE is_active = FALSE")
    inactive_website = cursor.fetchone()[0]
    print(f"   Website bots: {total_website} total, {inactive_website} inactive")
    
    # Check voicebotmeta
    cursor.execute("SELECT COUNT(*) FROM voicebotmeta")
    total_voice = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM voicebotmeta WHERE is_active = FALSE")
    inactive_voice = cursor.fetchone()[0]
    print(f"   Voice bots: {total_voice} total, {inactive_voice} inactive")
    
    # Check whatsappbotmeta
    cursor.execute("SELECT COUNT(*) FROM whatsappbotmeta")
    total_whatsapp = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM whatsappbotmeta WHERE is_active = FALSE")
    inactive_whatsapp = cursor.fetchone()[0]
    print(f"   WhatsApp bots: {total_whatsapp} total, {inactive_whatsapp} inactive")
    
    # 8. Check if created_at and updated_at columns exist in websitebotmeta and add if missing
    print("\n8. Adding timestamp columns to websitebotmeta...")
    cursor.execute("PRAGMA table_info(websitebotmeta)")
    website_columns = [col[1] for col in cursor.fetchall()]
    
    # Add created_at if missing (without default)
    if 'created_at' not in website_columns:
        print("   Adding 'created_at' to websitebotmeta...")
        cursor.execute("ALTER TABLE websitebotmeta ADD COLUMN created_at TIMESTAMP")
        print("   ✓ 'created_at' added")
        
        # Set default value for existing records
        current_time = datetime.now().isoformat()
        cursor.execute("UPDATE websitebotmeta SET created_at = ? WHERE created_at IS NULL", (current_time,))
        print(f"   Set created_at for existing records")
    else:
        print("   ✓ 'created_at' column already exists")
    
    # Add updated_at if missing (without default)
    if 'updated_at' not in website_columns:
        print("   Adding 'updated_at' to websitebotmeta...")
        cursor.execute("ALTER TABLE websitebotmeta ADD COLUMN updated_at TIMESTAMP")
        print("   ✓ 'updated_at' added")
        
        # Set default value for existing records
        current_time = datetime.now().isoformat()
        cursor.execute("UPDATE websitebotmeta SET updated_at = ? WHERE updated_at IS NULL", (current_time,))
        print(f"   Set updated_at for existing records")
    else:
        print("   ✓ 'updated_at' column already exists")
    
    # Commit all changes
    conn.commit()
    
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\nSummary of changes:")
    print("1. Added 'is_active' column to websitebotmeta table")
    print("2. Added 'is_active' column to voicebotmeta table")
    print("3. Added 'is_active' column to whatsappbotmeta table")
    print("4. Added 'last_active_toggle' column to whatsappbotmeta table")
    print("5. Added other WhatsApp columns if missing")
    print("6. Added timestamp columns to websitebotmeta")
    print("7. Set all existing bots to inactive by default")
    print("\n⚠ Important: All bots are now INACTIVE by default")
    print("⚠ Users must activate their bots using the toggle endpoints")
    print(f"\nDatabase file: {DATABASE_PATH.absolute()}")
    
except sqlite3.Error as e:
    print(f"\n❌ Database error: {e}")
    conn.rollback()
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    conn.rollback()
    sys.exit(1)
    
finally:
    conn.close()

print("\n✅ Migration complete! You can now start your FastAPI application:")
print("python -m uvicorn app:app --reload")