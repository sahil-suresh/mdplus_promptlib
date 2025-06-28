# app.py
import streamlit as st
from st_supabase_connection import SupabaseConnection
import hashlib
import pandas as pd

# --- APP CONFIGURATION ---
st.set_page_config(page_title="AI Prompt Hub", layout="wide")

# --- HELPER FUNCTIONS ---
def hash_password(password):
    """Hashes a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()

# --- DATABASE CONNECTION ---
# Initialize connection. Uses st.secrets to connect to Supabase.
conn = st.connection("supabase", type=SupabaseConnection)

# --- SESSION STATE MANAGEMENT ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.user_id = 0
    st.session_state.role = ""

# --- LOGIN/LOGOUT/REGISTER SIDEBAR ---
with st.sidebar:
    st.title("👨‍💻 User Hub")

    if st.session_state.logged_in:
        st.success(f"Logged in as **{st.session_state.username}**")
        st.write(f"Role: **{st.session_state.role.capitalize()}**")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.user_id = 0
            st.session_state.role = ""
            st.rerun()

    else:
        login_tab, register_tab = st.tabs(["Login", "Register"])

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                login_button = st.form_submit_button("Login")

                if login_button:
                    password_hash = hash_password(password)
                    user_data = conn.query("*", table="users", count="exact").eq("username", username).eq("password_hash", password_hash).execute()
                    if user_data.count > 0:
                        user = user_data.data[0]
                        st.session_state.logged_in = True
                        st.session_state.username = user['username']
                        st.session_state.user_id = user['id']
                        st.session_state.role = user['role']
                        st.rerun()
                    else:
                        st.error("Invalid username or password")

        with register_tab:
            with st.form("register_form"):
                new_username = st.text_input("Choose a Username")
                new_password = st.text_input("Choose a Password", type="password")
                register_button = st.form_submit_button("Register")

                if register_button:
                    user_exists = conn.query("*", table="users", count="exact").eq("username", new_username).execute()
                    if user_exists.count > 0:
                        st.error("Username already exists.")
                    else:
                        conn.table("users").insert({
                            "username": new_username,
                            "password_hash": hash_password(new_password),
                            "role": "user"
                        }).execute()
                        st.success("Registration successful! Please log in.")

# --- MAIN APP ---
st.title("🚀 AI Prompt Database")
st.markdown("Discover, share, and vote on the best AI prompts.")

tab_view, tab_submit, tab_admin = st.tabs(["View Prompts", "Submit a Prompt", "Admin Panel"])

# --- VIEW PROMPTS TAB ---
with tab_view:
    st.header("🌟 Approved Community Prompts")
    prompts_data = conn.rpc('get_approved_prompts_with_username').execute().data
    
    if not prompts_data:
        st.info("No prompts have been approved yet. Check back later!")
    else:
        prompts_df = pd.DataFrame(prompts_data)
        for index, row in prompts_df.iterrows():
            with st.expander(f"**{row['title']}** (Category: {row['category']})", expanded=False):
                st.markdown(f"*Submitted by: {row['username']}*")
                st.code(row['prompt_text'], language="text")

                # --- Voting Section (NEW NATIVE IMPLEMENTATION) ---
                col1, col2 = st.columns([1, 2])
                with col1:
                    rating_data = conn.query("rating", table="votes", count="exact").eq("prompt_id", row['id']).execute()
                    avg_rating = sum(r['rating'] for r in rating_data.data) / rating_data.count if rating_data.count > 0 else 0
                    st.markdown(f"**Rating: {avg_rating:.2f} / 5** ({rating_data.count} votes)")

                with col2:
                    if st.session_state.logged_in:
                        # Get user's current vote
                        user_vote_data = conn.query("rating", table="votes").eq("prompt_id", row['id']).eq("user_id", st.session_state.user_id).execute().data
                        user_vote = user_vote_data[0]['rating'] if user_vote_data else 0
                        
                        # Display stars as buttons
                        star_cols = st.columns(5)
                        for i, star_col in enumerate(star_cols, 1):
                            with star_col:
                                if st.button("⭐" if i <= user_vote else "☆", key=f"star_{row['id']}_{i}", use_container_width=True):
                                    # New rating is the star number that was clicked
                                    new_rating = i
                                    # If they click the same star they already voted for, it un-votes (sets rating to 0)
                                    if new_rating == user_vote:
                                        new_rating = 0
                                    
                                    # Update or insert the vote in the database
                                    conn.table("votes").upsert({
                                        "prompt_id": row['id'],
                                        "user_id": st.session_state.user_id,
                                        "rating": new_rating
                                    }, on_conflict="prompt_id, user_id").execute()
                                    st.rerun()
                    else:
                        st.warning("Login to vote!")

# --- SUBMIT PROMPT TAB ---
with tab_submit:
    st.header("✍️ Share Your Own Prompt")
    if st.session_state.logged_in:
        with st.form("prompt_submission_form", clear_on_submit=True):
            title = st.text_input("Prompt Title")
            category = st.selectbox("Category", ["General", "Coding", "Creative Writing", "Marketing", "Education"])
            prompt_text = st.text_area("Prompt Text", height=200)
            submitted = st.form_submit_button("Submit for Approval")

            if submitted:
                if title and prompt_text:
                    conn.table("prompts").insert({
                        "title": title, "prompt_text": prompt_text, "category": category,
                        "submitted_by_id": st.session_state.user_id, "status": "pending"
                    }).execute()
                    st.success("Your prompt has been submitted for admin approval. Thank you!")
                else:
                    st.warning("Please fill out all fields.")
    else:
        st.warning("You must be logged in to submit a prompt.")

# --- ADMIN PANEL TAB ---
with tab_admin:
    if st.session_state.role == 'admin':
        st.header("🔑 Admin Approval Queue")
        pending_prompts_data = conn.rpc('get_pending_prompts_with_username').execute().data

        if not pending_prompts_data:
            st.info("No prompts are currently awaiting approval.")
        else:
            pending_df = pd.DataFrame(pending_prompts_data)
            for index, row in pending_df.iterrows():
                with st.container(border=True):
                    st.subheader(f"'{row['title']}' by {row['username']}")
                    st.markdown(f"**Category:** {row['category']}")
                    st.code(row['prompt_text'], language='text')

                    col1, col2, col3 = st.columns([1, 1, 5])
                    with col1:
                        if st.button("Approve", key=f"approve_{row['id']}", type="primary"):
                            conn.table("prompts").update({"status": "approved"}).eq("id", row['id']).execute()
                            st.rerun()
                    with col2:
                        if st.button("Reject", key=f"reject_{row['id']}"):
                            conn.table("prompts").update({"status": "rejected"}).eq("id", row['id']).execute()
                            st.rerun()
    else:
        st.error("You do not have permission to view this page.")