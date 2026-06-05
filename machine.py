import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import warnings
import requests
import time

# Suppress SQLAlchemy and dateutil warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
warnings.filterwarnings("ignore", message=".*dateutil.*")

st.set_page_config(page_title="Paperspace Machine Manager", layout="wide")

# Auto-refresh: rerun the app every 3 seconds to sync with other users
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

current_time = time.time()
if current_time - st.session_state.last_refresh > 3:  # Refresh every 3 seconds
    st.session_state.last_refresh = current_time
    st.rerun()

st.title("Paperspace Machine Manager")
st.markdown("### Shared Paperspace GPU Machine Tracker")
st.markdown("**The current user is responsible for turning off the machine.**")

team_members = ["Prayag Raj", "Snigdh Chamoli", "Eisha rawat", "Pranshul Pandey", "Priyanshu"]

try:
    DB_CONFIG = st.secrets["postgres"]
    # THE FIX: Pointing these to the [paperspace] section in your secrets.toml
    PAPERSPACE_API_KEY = st.secrets["paperspace"]["PAPERSPACE_API_KEY"]
    MACHINE_ID = st.secrets["paperspace"]["MACHINE_ID"]
except Exception:
    st.error(
        "Missing Streamlit secrets. Ensure `.streamlit/secrets.toml` contains [postgres], "
        "and a [paperspace] section with PAPERSPACE_API_KEY and MACHINE_ID."
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
    query = "SELECT user_name, action, created_at, status FROM machine_events ORDER BY created_at DESC, id DESC LIMIT %s"
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
    
    if not rows:
        return pd.DataFrame(columns=['Name', 'Action', 'Timestamp', 'Status'])
    
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        'user_name': 'Name',
        'action': 'Action',
        'created_at': 'Timestamp',
        'status': 'Status'
    })
    
    if 'Timestamp' in df.columns:
        timestamps = pd.to_datetime(df['Timestamp'], format='mixed', errors='coerce', utc=True)
        timestamps = timestamps.dt.tz_convert('Asia/Kolkata')
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

def start_machine(user_name: str):
    url = f"https://api.paperspace.io/machines/{MACHINE_ID}/start"
    headers = {
        "x-api-key": PAPERSPACE_API_KEY
    }
    try:
        response = requests.post(url, headers=headers)
        if response.status_code in [200, 204]:
            st.success(f"✅ Machine started successfully by {user_name}!")
            append_event(user_name, "Machine Start", "Booting")
        else:
            st.error(f"❌ Failed to start. Status: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Error starting machine: {str(e)}")

def stop_machine(user_name: str):
    url = f"https://api.paperspace.io/machines/{MACHINE_ID}/stop"
    headers = {
        "x-api-key": PAPERSPACE_API_KEY
    }
    try:
        response = requests.post(url, headers=headers)
        if response.status_code in [200, 204]:
            st.success(f"✅ Machine stopped successfully by {user_name}!")
            append_event(user_name, "Machine Stop", "Shutting Down")
        else:
            st.error(f"❌ Failed to stop. Status: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Error stopping machine: {str(e)}")

def get_current_user_state(member: str) -> bool:
    """Get the current state of a user from the database (most recent event)."""
    query = """
    SELECT status FROM machine_events 
    WHERE user_name = %s 
    ORDER BY created_at DESC, id DESC 
    LIMIT 1
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (member,))
                row = cursor.fetchone()
        
        if row:
            # "In Use" means toggle is ON, anything else means toggle is OFF
            return row["status"] == "In Use"
        return False
    except Exception:
        return False

def on_toggle_change(member: str):
    """Callback when a toggle is changed."""
    toggle_key = f"toggle_{member}"
    current_state = st.session_state.get(toggle_key, False)
    
    try:
        if current_state:
            append_event(member, "Check In", "In Use")
        else:
            append_event(member, "Check Out", "Offline")
    except Exception as e:
        st.error(f"Error saving event for {member}: {str(e)}")

def execute_daily_reset():
    """Callback for the End of Day Reset button to safely update UI state."""
    try:
        reset_database()
        for member in team_members:
            st.session_state[f"toggle_{member}"] = False
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

# Initialize toggle states from database (not hardcoded to False)
for member in team_members:
    toggle_key = f"toggle_{member}"
    if toggle_key not in st.session_state:
        # Load the actual state from the database
        db_state = get_current_user_state(member)
        st.session_state[toggle_key] = db_state

# --- GPU MACHINE CONTROLS SECTION ---
st.markdown("---")
st.subheader("🖥️ GPU Machine Controls")
st.write("Start or stop the shared Paperspace machine directly from here.")

action_user = st.selectbox("Select your name to authorize machine action:", team_members, key="action_user")

col1, col2 = st.columns(2)

with col1:
    if st.button("🟢 Start Machine", use_container_width=True):
        start_machine(action_user)

with col2:
    if st.button("🔴 Stop Machine", use_container_width=True):
        st.session_state.confirm_stop = True

if st.session_state.get("confirm_stop", False):
    st.warning(f"⚠️ **{action_user}**, are you sure you want to stop the machine? Ensure no one else is running jobs.")
    conf_col1, conf_col2 = st.columns(2)
    
    with conf_col1:
        if st.button("✔️ Yes, Stop it", type="primary", use_container_width=True):
            stop_machine(action_user)
            st.session_state.confirm_stop = False
            st.rerun()
            
    with conf_col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.confirm_stop = False
            st.rerun()

st.markdown("---")

st.subheader("User Status Toggles")
st.write("Toggle ON to check in, Toggle OFF to check out:")

# Refresh toggle states from database before displaying
for member in team_members:
    toggle_key = f"toggle_{member}"
    db_state = get_current_user_state(member)
    st.session_state[toggle_key] = db_state

cols = st.columns(len(team_members))
for idx, member in enumerate(team_members):
    toggle_key = f"toggle_{member}"
    with cols[idx]:
        st.toggle(member, key=toggle_key, on_change=on_toggle_change, args=(member,))

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
    
if st.session_state.pop('show_reset_success', False):
    st.success("Database and toggles reset successfully! Ready for a fresh day.")
    
if 'reset_error' in st.session_state:
    st.error("Unable to perform the reset.")
    st.exception(st.session_state.pop('reset_error'))

# Initialize fallback DataFrame to completely guard against NameErrors
history_df = pd.DataFrame(columns=['Name', 'Action', 'Timestamp', 'Status'])

# Load and display history Dashboard
try:
    history_df = load_history(100)
    
    summary_data = []
    for member in team_members:
        is_active = st.session_state.get(f"toggle_{member}", False)
        status_icon = "🟢 In Use" if is_active else " 🔴 Offline"
        
        last_check_in = "--"
        last_check_out = "--"
        
        if not history_df.empty:
            member_logs = history_df[history_df['Name'] == member]
            
            check_ins = member_logs[member_logs['Action'] == 'Check In']
            if not check_ins.empty:
                last_check_in = check_ins.iloc[0]['Timestamp']
                
            check_outs = member_logs[member_logs['Action'] == 'Check Out']
            if not check_outs.empty:
                last_check_out = check_outs.iloc[0]['Timestamp']
        
        summary_data.append({
            "Name": member,
            "Current Status": status_icon,
            "Last Check In": last_check_in,
            "Last Check Out": last_check_out
        })
        
    summary_df = pd.DataFrame(summary_data)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    st.caption("This app uses PostgreSQL for shared persistent storage. When you toggle ON, a 'Check In' event is recorded. When you toggle OFF, a 'Check Out' event is recorded.")

except Exception as exc:
    st.error("❌ Unable to load team dashboard.")
    st.exception(exc)

# Expander is now safe from crashing because history_df is guaranteed to exist
with st.expander("🔍 View Raw Event Logs & DB Info"):
    try:
        st.write(f"**Total records in database:** {get_record_count()}")
        st.write(f"Displaying last {len(history_df)} raw records:")
        st.dataframe(history_df, width='stretch', hide_index=True)
    except Exception as exc:
        st.error("Could not fetch raw log metrics.")

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
