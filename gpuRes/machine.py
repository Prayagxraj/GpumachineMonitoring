import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import warnings

# Suppress SQLAlchemy and dateutil warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
warnings.filterwarnings("ignore", message=".*dateutil.*")

st.set_page_config(page_title="Paperspace Machine Manager", layout="wide")

st.title("Paperspace Machine Manager")
st.markdown("### Shared Paperspace GPU Machine Tracker")
st.markdown(
    "**The current user is responsible for turning off the machine.**"
)

team_members = ["Prayag Raj", "Snigdh Chamoli", "Eisha rawat", "Pranshul Pandey", "Priyanshu"]

try:
    DB_CONFIG = st.secrets["postgres"]
except Exception:
    st.error(
        "No Streamlit secrets were found. Create `.streamlit/secrets.toml` with a [postgres] section, "
        "or copy `.streamlit/secrets.toml.example` and fill in your database credentials."
    )
    st.stop()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS machine_events (
    id SERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
)
"""


def get_db_connection():
    if not DB_CONFIG:
        raise RuntimeError(
            "Missing `[postgres]` configuration in Streamlit secrets."
        )

    return psycopg2.connect(
        host=DB_CONFIG.get("host"),
        port=DB_CONFIG.get("port", 5432),
        dbname=DB_CONFIG.get("dbname"),
        user=DB_CONFIG.get("user"),
        password=DB_CONFIG.get("password"),
        cursor_factory=RealDictCursor,
    )


def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
        conn.commit()


def append_event(user_name: str, action: str, status: str):
    query = "INSERT INTO machine_events (user_name, action, status, created_at) VALUES (%s, %s, %s, NOW())"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (user_name, action, status))
        conn.commit()


def load_history(limit: int = 20) -> pd.DataFrame:
    query = "SELECT user_name, action, created_at, status FROM machine_events ORDER BY created_at DESC, id DESC LIMIT %s"
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
    
    # If no rows, return empty DataFrame with correct columns
    if not rows:
        return pd.DataFrame(columns=['Name', 'Action', 'Timestamp', 'Status'])
    
    # Convert RealDictCursor rows to DataFrame
    df = pd.DataFrame([dict(row) for row in rows])
    
    # Rename columns to match expected format
    df = df.rename(columns={
        'user_name': 'Name',
        'action': 'Action',
        'created_at': 'Timestamp',
        'status': 'Status'
    })
    
    # Parse and format Timestamp column
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    return df


def reset_database():
    """Clear all records from the machine_events table."""
    query = "DELETE FROM machine_events"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
        conn.commit()


def get_record_count():
    """Get the count of records in the database."""
    query = "SELECT COUNT(*) as count FROM machine_events"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
    return row["count"] if row else 0


def on_toggle_change(member: str):
    """Callback when a toggle is changed."""
    toggle_key = f"toggle_{member}"
    
    current_state = st.session_state.get(toggle_key, False)
    
    try:
        if current_state:
            # Toggle turned ON → Check In
            append_event(member, "Check In", "In Use")
        else:
            # Toggle turned OFF → Check Out
            append_event(member, "Check Out", "Available")
    except Exception as e:
        st.error(f"Error saving event for {member}: {str(e)}")


try:
    init_db()
except Exception as exc:
    st.error("Unable to initialize the database. Verify your Streamlit secrets and database connection.")
    st.exception(exc)
    st.stop()

# Initialize toggle states in session_state
for member in team_members:
    toggle_key = f"toggle_{member}"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = False

st.subheader("User Status Toggles")
st.write("Toggle ON to check in, Toggle OFF to check out:")

cols = st.columns(len(team_members))
for idx, member in enumerate(team_members):
    toggle_key = f"toggle_{member}"
    with cols[idx]:
        st.toggle(member, key=toggle_key, on_change=on_toggle_change, args=(member,))

# Count active users
active_users = [member for member in team_members if st.session_state.get(f"toggle_{member}", False)]

st.markdown("---")
st.subheader("Current Status")

if len(active_users) == 0:
    st.success("🟢 Machine is FREE - No users active")
elif len(active_users) == 1:
    st.warning(
        f"🚨 **ALERT:** Only {active_users[0]} is using the machine. "
        f"**You are responsible for shutting down the machine!**"
    )
else:
    status_list = "\n".join([f"• {user}" for user in active_users])
    st.info(
        f"**Machine is IN USE by {len(active_users)} users:**\n{status_list}"
    )

st.markdown("---")
st.subheader("Usage History")

col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🔄 Reset Table"):
        try:
            reset_database()
            st.success("Table reset successfully!")
            st.rerun()
        except Exception as exc:
            st.error("Unable to reset the table.")
            st.exception(exc)

# Show diagnostic info
try:
    record_count = get_record_count()
    st.write(f"**Total records in database:** {record_count}")
except Exception as e:
    st.warning(f"Could not fetch record count: {str(e)}")

# Load and display history
try:
    history_df = load_history(20)
    
    st.write(f"**Records found:** {len(history_df)}")
    
    if history_df.empty:
        st.write("✋ No history records available yet. Toggle a user ON/OFF to create records.")
    else:
        st.write(f"Displaying {len(history_df)} records:")
        
        # Debug: show column info
        st.write(f"**Columns:** {list(history_df.columns)}")
        
        st.dataframe(history_df, width='stretch', hide_index=True)
except Exception as exc:
    st.error("❌ Unable to load usage history.")
    st.exception(exc)

st.caption(
    "This app uses PostgreSQL for shared persistent storage. When you toggle ON, a 'Check In' event is recorded. When you toggle OFF, a 'Check Out' event is recorded."
)

# Debug section
with st.expander("🔧 Debug Info"):
    st.write("**Database Configuration:**")
    st.write(f"- Host: {DB_CONFIG.get('host')}")
    st.write(f"- Port: {DB_CONFIG.get('port', 5432)}")
    st.write(f"- Database: {DB_CONFIG.get('dbname')}")
    st.write(f"- User: {DB_CONFIG.get('user')}")
    
    st.write("\n**Test Database Connection:**")
    try:
        test_conn = get_db_connection()
        test_conn.close()
        st.success("✅ Database connection successful!")
    except Exception as e:
        st.error(f"❌ Connection failed: {str(e)}")
    
    st.write("\n**Raw Query Test:**")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_name, action, created_at, status FROM machine_events LIMIT 5")
                rows = cursor.fetchall()
        st.write(f"Found {len(rows)} rows:")
        if rows:
            for row in rows:
                st.json(dict(row))
        else:
            st.write("No rows found in database")
    except Exception as e:
        st.error(f"Query failed: {str(e)}")
