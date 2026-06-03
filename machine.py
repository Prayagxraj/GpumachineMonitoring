import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import warnings

# Suppress SQLAlchemy and dateutil warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
warnings.filterwarnings("ignore", message=".*dateutil.*")

st.set_page_config(page_title="Paperspace Machine Manager", layout="wide")

st.title("Paperspace Machine Manager")
st.markdown("### Shared Paperspace GPU Machine Tracker")
st.markdown("**The current user is responsible for turning off the machine.**")

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
        raise RuntimeError("Missing `[postgres]` configuration in Streamlit secrets.")
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

def load_history(limit: int = 100) -> pd.DataFrame:
    # Increased limit to ensure we fetch enough history to find everyone's latest action
    query = "SELECT user_name, action, created_at, status FROM machine_events ORDER BY created_at DESC, id DESC LIMIT %s"
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
    
    # If no rows, return empty DataFrame with correct columns
    if not rows:
        return pd.DataFrame(columns=['Name', 'Action', 'Timestamp', 'Status'])
    
    # Convert RealDictCursor rows to DataFrame directly
    df = pd.DataFrame(rows)
    
    # Rename columns to match expected UI format
    df = df.rename(columns={
        'user_name': 'Name',
        'action': 'Action',
        'created_at': 'Timestamp',
        'status': 'Status'
    })
    
    # Parse Timestamp, convert to local IST time, and format to AM/PM
    if 'Timestamp' in df.columns:
        # 1. Parse raw UTC time from database
        timestamps = pd.to_datetime(df['Timestamp'], format='mixed', errors='coerce')
        # 2. Convert to Indian Standard Time (IST)
        timestamps = timestamps.dt.tz_convert('Asia/Kolkata')
        # 3. Format to readable AM/PM string
        df['Timestamp'] = timestamps.dt.strftime('%b %d, %I:%M %p') 
    
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
            append_event(member, "Check In", "In Use")
        else:
            # Changed from "Available" to "Offline" for better readability
            append_event(member, "Check Out", "Offline")
    except Exception as e:
        st.error(f"Error saving event for {member}: {str(e)}")

def execute_daily_reset():
    """Callback for the End of Day Reset button to safely update UI state."""
    try:
        # Clear the database
        reset_database()
        
        # Reset all toggles in the UI to OFF
        for member in team_members:
            st.session_state[f"toggle_{member}"] = False
            
        # Set a flag so we know to show a success message
        st.session_state['show_reset_success'] = True
    except Exception as e:
        st.session_state['reset_error'] = e

# Initialize database
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

col1, col2 = st.columns([4, 1])
with col1:
    st.subheader("Team Dashboard")
with col2:
    st.button("🔄 End of Day Reset", on_click=execute_daily_reset)
    
# Check flags to show success or error messages after the page reloads
if st.session_state.pop('show_reset_success', False):
    st.success("Database and toggles reset successfully! Ready for a fresh day.")
    
if 'reset_error' in st.session_state:
    st.error("Unable to perform the reset.")
    st.exception(st.session_state.pop('reset_error'))

# Load and display history Dashboard
try:
    history_df = load_history(100)
    
    # Create a clean summary table for the predefined names
    summary_data = []
    
    for member in team_members:
        # Determine current status based on the toggle switch
        is_active = st.session_state.get(f"toggle_{member}", False)
        status_icon = "🔴 In Use" if is_active else "🟢 Offline"
        
        # Default empty times
        last_check_in = "--"
        last_check_out = "--"
        
        if not history_df.empty:
            # Get all logs for this specific person
            member_logs = history_df[history_df['Name'] == member]
            
            # Find their most recent Check In
            check_ins = member_logs[member_logs['Action'] == 'Check In']
            if not check_ins.empty:
                last_check_in = check_ins.iloc[0]['Timestamp']
                
            # Find their most recent Check Out
            check_outs = member_logs[member_logs['Action'] == 'Check Out']
            if not check_outs.empty:
                last_check_out = check_outs.iloc[0]['Timestamp']
        
        # Append to our new predefined table
        summary_data.append({
            "Name": member,
            "Current Status": status_icon,
            "Last Check In": last_check_in,
            "Last Check Out": last_check_out
        })
        
    # Convert to DataFrame and Display the clean Dashboard
    summary_df = pd.DataFrame(summary_data)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    st.caption("This app uses PostgreSQL for shared persistent storage. When you toggle ON, a 'Check In' event is recorded. When you toggle OFF, a 'Check Out' event is recorded.")

    # Keep an expander to view the raw database logs if you ever need to debug
    with st.expander("🔍 View Raw Event Logs & DB Info"):
        st.write(f"**Total records in database:** {get_record_count()}")
        st.write(f"Displaying last {len(history_df)} raw records:")
        st.dataframe(history_df, width='stretch', hide_index=True)

except Exception as exc:
    st.error("❌ Unable to load team dashboard.")
    st.exception(exc)

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