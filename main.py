import streamlit as st
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine
import pandas as pd
import requests
import paramiko
import io
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

# --- Init LLaMA3 (Ollama must be running) ---
llm = ChatOllama(model="llama3")

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Ask AIra", page_icon="🧠", layout="centered")
st.title("🧠 Ask AIra (Ask Database via LLaMA3)")

# --- Session state for connection settings ---
if "connection_config" not in st.session_state:
    st.session_state.connection_config = {
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_user": "",
        "use_ssh_key": False,
        "ssh_password": "",
        "ssh_key_data": "",
        "remote_bind_host": "127.0.0.1",
        "remote_bind_port": 3306,
        "db_user": "",
        "db_pass": "",
        "db_name": "",
    }

# --- Connection Settings Form ---
with st.form("connection_form"):
    st.subheader("🔑 SSH & Database Connection Settings")
    config = st.session_state.connection_config

    config["ssh_host"] = st.text_input("SSH Host", value=config["ssh_host"])
    config["ssh_port"] = st.number_input("SSH Port", value=config["ssh_port"], step=1)
    config["ssh_user"] = st.text_input("SSH Username", value=config["ssh_user"])

    config["use_ssh_key"] = st.checkbox("Use SSH Key Authentication", value=config["use_ssh_key"])
    if config["use_ssh_key"]:
        uploaded_key = st.file_uploader("Upload SSH Private Key (.pem, .key, .txt)", type=["pem", "key", "txt"])
        if uploaded_key is not None:
            config["ssh_key_data"] = uploaded_key.getvalue().decode("utf-8")
            st.success("✅ SSH Private Key uploaded!")
    else:
        config["ssh_password"] = st.text_input("SSH Password", type="password", value=config["ssh_password"])

    config["db_user"] = st.text_input("Database User", value=config["db_user"])
    config["db_pass"] = st.text_input("Database Password", type="password", value=config["db_pass"])
    config["db_name"] = st.text_input("Database Name", value=config["db_name"])

    submitted = st.form_submit_button("Save Settings")
    if submitted:
        st.success("✅ Settings saved! You can now check the connection or ask questions.")


# --- Buttons and Chat Input ---
check_connection = st.button("Check DB Connection")
check_llama = st.button("Check LLaMA3 Status")
user_question = st.chat_input("Ask something about the database")

# --- LLaMA3 Status Check ---
if check_llama:
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in res.json().get("models", [])]
        if any("llama3" in m for m in models):
            st.success("✅ LLaMA3 model is running via Ollama!")
        else:
            st.warning("⚠️ LLaMA3 model is not running. Please run: `ollama run llama3`")
    except Exception as e:
        st.error(f"❌ Ollama connection failed: {e}")

# --- SQL Generation Prompt ---
def get_sql_from_question(question):
    examples = """
Q: What is the total point of user named 'test'?
SQL:
SELECT id, point, basic_point, (point + basic_point) AS total_point FROM synchrochat_users WHERE name = 'test';

Q: Give me the total point for user named 'test'.
SQL:
SELECT id, point, basic_point, (point + basic_point) AS total_point FROM synchrochat_users WHERE name = 'test';

Q: Show id, point, basic point, and their total for the user called 'test'.
SQL:
SELECT id, point, basic_point, (point + basic_point) AS total_point FROM synchrochat_users WHERE name = 'test';

Q: Find the combined point for user 'test'.
SQL:
SELECT id, point, basic_point, (point + basic_point) AS total_point FROM synchrochat_users WHERE name = 'test';

Q: Show all users with their total points
SQL:
SELECT name, (basic_point + point) AS total_points FROM synchrochat_users;

Q: How many users are there?
SQL:
SELECT COUNT(*) FROM synchrochat_users;

Q: Show all failed jobs
SQL:
SELECT * FROM synchrochat_failed_jobs;

Q: Show all active blast
SQL:
SELECT * FROM synchrochat_blasts where status='1';

Q: How many message has been blast by our system?
SQL:
SELECT * from synchrochat_blasts where is_blast='1';

Q: Count the distinct devices that sent blast messages.
SQL:
SELECT COUNT(DISTINCT synchrochat_devices.device_uid) AS total_devices
FROM synchrochat_devices
INNER JOIN synchrochat_blasts 
ON synchrochat_devices.device_uid = synchrochat_blasts.device_uid;

Q: How many unique devices have been used for blasting?
SQL:
SELECT COUNT(DISTINCT synchrochat_devices.device_uid) AS total_devices
FROM synchrochat_devices
INNER JOIN synchrochat_blasts 
ON synchrochat_devices.device_uid = synchrochat_blasts.device_uid;

Q: Get the total number of devices that have done blasts.
SQL:
SELECT COUNT(DISTINCT synchrochat_devices.device_uid) AS total_devices
FROM synchrochat_devices
INNER JOIN synchrochat_blasts 
ON synchrochat_devices.device_uid = synchrochat_blasts.device_uid;

Q: Total devices used for message blasting?
SQL:
SELECT COUNT(DISTINCT synchrochat_devices.device_uid) AS total_devices
FROM synchrochat_devices
INNER JOIN synchrochat_blasts 
ON synchrochat_devices.device_uid = synchrochat_blasts.device_uid;

Q: Did this user has device, blast message?
SQL: 
SELECT synchrochat_users.id, synchrochat_blasts.user_id, synchrochat_devices.user_id
FROM ((synchrochat_users
INNER JOIN synchrochat_blasts ON synchrochat_users.id = synchrochat_blasts.user_id)
INNER JOIN synchrochat_devices ON synchrochat_users.id = synchrochat_devices.user_id);

Q: How many users that are not having any devices?
SQL: 
SELECT COUNT(DISTINCT synchrochat_devices.device_uid = NULL) AS total_no_devices
FROM synchrochat_devices
INNER JOIN synchrochat_users
ON synchrochat_devices.device_uid = synchrochat_users.device_uid;

Q: How many advertisement user amiruladib use in their blast?
SQL: 
SELECT COUNT(*) AS total_usage
FROM synchrochat_blasts
INNER JOIN synchrochat_users 
    ON synchrochat_blasts.user_id = synchrochat_users.user_id
INNER JOIN synchrochat_advertisements       
    ON synchrochat_blasts.user_id = synchrochat_advertisements.user_id
WHERE synchrochat_users.name = 'user name';

Q:How many users does not have an active account?
SQL:
SELECT COUNT(*) FROM synchrochat_users WHERE email_verified_at IS NULL;

Q: how many users that have blast their advertisement before?
SQL:
SELECT COUNT(DISTINCT synchrochat_users.id) AS total_users
FROM synchrochat_users
INNER JOIN synchrochat_blasts
    ON synchrochat_users.id = synchrochat_blasts.user_id
INNER JOIN synchrochat_advertisements
    ON synchrochat_blasts.user_id = synchrochat_advertisements.user_id;

Q: how many users that are not verified yet and don't insert their website yet?
SQL:
SELECT
  COUNT(*) AS total_users
FROM
  synchrochat_users
WHERE
  email_verified_at IS NULL
  AND (
    website IS NULL
    OR website = ''
  );
"""
    template = ChatPromptTemplate.from_template(f"""
You are a helpful AI assistant that writes MySQL queries.

{examples}

Only return the SQL query.

Question: {{question}}
SQL:
""")
    return (template | llm).invoke({"question": question}).content.strip().rstrip(';')

# --- Natural Language Summary Prompt ---
def get_human_answer(question, sql, result):
    template = ChatPromptTemplate.from_template("""
Based on the SQL result below, generate a natural language answer:

Question: {question}
SQL: {sql}
Result: {result}

Answer:
""")
    return (template | llm).invoke({
        "question": question,
        "sql": sql,
        "result": result
    }).content.strip()

# --- Chat Session State ---
if "chat" not in st.session_state:
    st.session_state.chat = []

# --- SSH + DB Logic ---
if user_question or check_connection:
    config = st.session_state.connection_config

    if not config["ssh_host"] or not config["ssh_user"] or not config["db_user"]:
        st.warning("⚠️ Please fill in the SSH and DB settings above before using the app.")
    else:
        try:
            ssh_args = {
                "ssh_username": config["ssh_user"],
                "remote_bind_address": (config["remote_bind_host"], config["remote_bind_port"])
            }

            if config.get("use_ssh_key"):
                if not config.get("ssh_key_data"):
                    st.error("❌ Please upload your SSH private key file.")
                    raise ValueError("Missing SSH Key")

                key_file_obj = io.StringIO(config["ssh_key_data"])
                pkey = paramiko.RSAKey.from_private_key(key_file_obj)
                ssh_args["ssh_private_key"] = pkey
            else:
                ssh_args["ssh_password"] = config["ssh_password"]

            with SSHTunnelForwarder(
                (config["ssh_host"], config["ssh_port"]),
                **ssh_args
            ) as tunnel:
                local_port = tunnel.local_bind_port
                db_uri = f"mysql+pymysql://{config['db_user']}:{config['db_pass']}@127.0.0.1:{local_port}/{config['db_name']}"
                engine = create_engine(db_uri)

                with engine.connect() as conn:
                    if check_connection:
                        st.success("✅ Connected to Synchrochat database!")

                    if user_question:
                        st.session_state.chat.append({"role": "user", "content": user_question})
                        sql = get_sql_from_question(user_question)
                        df = pd.read_sql(sql, con=conn)
                        result = df.to_records(index=False).tolist()
                        answer = get_human_answer(user_question, sql, result)
                        st.session_state.chat.append({"role": "assistant", "content": answer})

        except Exception as e:
            st.error(f"❌ DB Connection failed: {e}")

# --- Chat Display ---
for msg in st.session_state.chat:
    st.chat_message(msg["role"]).markdown(msg["content"])
