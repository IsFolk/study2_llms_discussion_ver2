import streamlit as st
import asyncio
import re
from autogen import UserProxyAgent
from autogen import ConversableAgent
import pandas as pd
import plotly.express as px
import os
import time
import uuid

import os
import markdown2
import io
import datetime
import streamlit as st
from supabase import create_client
import requests
import json


os.environ["AUTOGEN_USE_DOCKER"] = "0"

# 從 secrets 讀取
SUPABASE_URL = st.secrets["supabase"]["url"].strip()
SUPABASE_SERVICE_KEY = st.secrets["supabase"]["service_key"].strip()
SUPABASE_SCHEMA = st.secrets["supabase"]["schema"].strip()


supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def store_messages(silent: bool = False):
    # 取得本輪訊息
    messages_this_round = st.session_state.get(f"{user_session_id}_messages", [])
    selected_ideas = list(st.session_state.get(f"{user_session_id}_selected_persistent_ideas", {}).keys())

    # 準備要寫入的資料，加入 selected_ideas 欄位
    record = {
        "session_id": user_session_id,
        "round": st.session_state.get(f"{user_session_id}_round_num", 0),
        "user_question": st.session_state.get(f"{user_session_id}_user_question", ""),
        "messages": messages_this_round,
        "selected_ideas": selected_ideas  # <== 新增這一行
    }

    # API 基本資訊
    endpoint = f"{SUPABASE_URL}/rest/v1/conversations"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
        "Content-Profile": SUPABASE_SCHEMA
    }

    # 檢查是否已有記錄
    check_response = requests.get(f"{endpoint}?session_id=eq.{user_session_id}", headers=headers)

    if check_response.status_code == 200 and check_response.json():
        # 已存在，更新
        existing_id = check_response.json()[0]["id"]
        update_endpoint = f"{endpoint}?id=eq.{existing_id}"
        update_response = requests.patch(update_endpoint, headers=headers, json=record)

        if not silent:
            if update_response.status_code in [200, 204]:
                st.toast("已更新 Supabase 記錄（包含收藏 Ideas）", icon="✅")
            else:
                st.error(f"❌ 更新失敗: {update_response.status_code} - {update_response.text}")

        return update_response.status_code in [200, 204]

    else:
        # 不存在，新增
        response = requests.post(endpoint, headers=headers, json=record)

        if not silent:
            if response.status_code in [200, 201]:
                st.toast("已新增到 Supabase（包含收藏 Ideas）", icon="✅")
            else:
                st.error(f"❌ 新增失敗: {response.status_code} - {response.text}")

        return response.status_code in [200, 201]


# 設定 Streamlit 頁面
st.set_page_config(page_title="LLM + Human Discussion Framework", page_icon="🧑", layout="wide")


provided_uuid = st.query_params.get("uid")

# 沒有 uid → 自動產生並寫入 URL
if not provided_uuid:
    new_uuid = str(uuid.uuid4())

    st.write("🔄 產生 Session UUID 中，請稍後...")

    # ✅ 直接改 URL（不是 redirect）
    st.query_params["uid"] = new_uuid

    # ✅ 重新執行 app（關鍵）
    st.rerun()

# 有 uid → 正常使用
if "user_session_id" not in st.session_state:
    st.session_state["user_session_id"] = st.query_params["uid"]

user_session_id = st.session_state["user_session_id"]

# =========================
# 語言選擇前置頁
# =========================
if f"{user_session_id}_language_selected" not in st.session_state:
    st.session_state[f"{user_session_id}_language_selected"] = False

if f"{user_session_id}_language" not in st.session_state:
    st.session_state[f"{user_session_id}_language"] = "zh-TW"


if not st.session_state[f"{user_session_id}_language_selected"]:
    st.title("Please select your language / 請選擇語言")

    selected_lang = st.radio(
        "Language / 語言",
        options=["zh-TW", "en"],
        format_func=lambda x: "繁體中文" if x == "zh-TW" else "English"
    )

    if st.button("Continue / 繼續"):
        st.session_state[f"{user_session_id}_language"] = selected_lang
        st.session_state[f"{user_session_id}_language_selected"] = True
        st.rerun()

    st.stop()


# 載入語言包
@st.cache_data
def load_locale(lang):
    with open(f"locale/{lang}.json", "r", encoding="utf-8") as f:
        return json.load(f)

# 國際化翻譯函式
def t(key, **kwargs):
    lang = st.session_state.get(f"{user_session_id}_language", "zh-TW")
    locale = load_locale(lang)

    keys = key.split(".")
    val = locale
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return key

    if val is None:
        return key

    if isinstance(val, str) and kwargs:
        return val.format(**kwargs)

    return val
    
with st.sidebar:
    with st.expander("**Session UUID**", expanded=False):
        if user_session_id:
            st.success(f"✅ 目前 Session UUID: {user_session_id}")

if f"{user_session_id}_messages" not in st.session_state:
    # 🟢 建立 RESTful API 查詢 URL - 改為 api schema
    history_api_url = f"{SUPABASE_URL}/rest/v1/conversations?session_id=eq.{user_session_id}&order=round.asc"

    # print(f"🔍 查詢歷史紀錄的 API URL: {history_api_url}")  # Debug 用

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
        "Accept-Profile": SUPABASE_SCHEMA  # ✅ GET 要用 Accept-Profile
    }

    # 🟢 發送 GET 請求
    response = requests.get(history_api_url, headers=headers)

    # 🟢 檢查回應
    if response.status_code == 200:
        history_data = response.json()

        if history_data:
            # 取得最新的紀錄
            latest_record = history_data[-1]
            latest_messages = latest_record.get("messages", [])
            latest_round = latest_record.get("round", 0)
            latest_selected_ideas = latest_record.get("selected_ideas", [])  # 讀取收藏的 Ideas


            # 還原狀態
            st.session_state[f"{user_session_id}_messages"] = latest_messages
            st.session_state[f"{user_session_id}_round_num"] = latest_round
            st.session_state[f"{user_session_id}_discussion_started"] = True

            # 還原收藏的 Ideas
            st.session_state[f"{user_session_id}_selected_persistent_ideas"] = {idea: latest_round for idea in latest_selected_ideas}


            if f"{user_session_id}_idea_options" not in st.session_state:
                st.session_state[f"{user_session_id}_idea_options"] = {}

            # 直接遍歷 latest_messages
            st.session_state[f"{user_session_id}_idea_options"][f"round_{latest_round}"] = [
                idea.get("content", "") for idea in latest_messages if idea.get("role") == "Assistant"
            ]

            st.toast(t("ui.backup_success"), icon="📝")

        else:
            st.info(t("ui.backup_not_found"), icon="ℹ️")
    else:
        st.error(f"❌ {t('ui.request_failed')}: {response.status_code} {response.text}")

# # 顯示從 URL 讀到的參數
# st.write(f"🔍 從 URL 讀取到的 uid 參數： `{provided_uuid}`")

# # 顯示目前有效的 user_session_id
# st.write(f"🆔 目前有效的 user_session_id： `{user_session_id}`")

st.markdown("---")

st.cache_data.clear()  # **確保每個使用者的快取是獨立的**
st.cache_resource.clear()

user_session_id = st.session_state["user_session_id"]

# 從 st.secrets 讀取 API Key
api_key = st.secrets["api_keys"]["OPENAI_API_KEY"]

is_locked = st.session_state.get(f"{user_session_id}_discussion_started", False)


if f"{user_session_id}_use_persona" not in st.session_state:
    st.session_state[f"{user_session_id}_use_persona"] = True  # 預設開啟

if f"{user_session_id}_enable_scamper_input" not in st.session_state:
    st.session_state[f"{user_session_id}_enable_scamper_input"] = True  # 預設開啟

if f"{user_session_id}_onboarding_done" not in st.session_state:
    st.session_state[f"{user_session_id}_onboarding_done"] = False



if not st.session_state.get(f"{user_session_id}_onboarding_done", False):
    st.title(t("ui.feature_settings"))
    st.write(t("ui.select_features"))


    # ❗用中繼變數來接收 checkbox 狀態
    use_persona_temp = st.checkbox(
        t("ui.enable_persona"),
        value=st.session_state.get(f"{user_session_id}_use_persona", True)
    )
    enable_scamper_temp = st.checkbox(
        t("ui.enable_scamper"),
        value=st.session_state.get(f"{user_session_id}_enable_scamper_input", True)
    )

    if st.button(t("ui.settings_done")):
        # ❗只在這邊真正寫入 session_state
        st.session_state[f"{user_session_id}_use_persona"] = use_persona_temp
        st.session_state[f"{user_session_id}_enable_scamper_input"] = enable_scamper_temp
        st.session_state[f"{user_session_id}_onboarding_done"] = True
        st.rerun()

    st.stop()


st.markdown(
    """
<style>
div[data-testid="stDialog"] div[role="dialog"]:has(.big-dialog) {
    width: 80vw;
    max-height: 95vh;
    overflow-y: auto;
}
</style>
""",
    unsafe_allow_html=True,
)

import base64

def get_image_base64(image_path):
    with open(image_path, "rb") as img_file:
        encoded = base64.b64encode(img_file.read()).decode()
    return f"data:image/png;base64,{encoded}"



@st.dialog(t("ui.system_intro"), width="large")
def show_onboarding_tabs():
    st.html("<span class='big-dialog'></span>")
    st.warning(t("ui.system_hint"), icon="⚠️")

    # 構建頁面
    pages = build_onboarding_pages()
    tab_titles = [p["title"] for p in pages]

    tabs = st.tabs(tab_titles)
    for tab, page in zip(tabs, pages):
        with tab:
            st.write(page["content"])
            if "image" in page:
                # 使用 HTML 方式顯示圖片
                img_src = get_image_base64(f"./{page["image"]}")

                st.markdown(
                    f"""
                    <div style='text-align: center;'>
                        <img src="{img_src}" style="max-width:70%; max-height:auto;" />
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    if st.button(t("ui.start_using"), type="primary"):
        st.session_state[f"{user_session_id}_show_onboarding_modal"] = False
        st.rerun()




def build_onboarding_pages():
    pages = []

    if st.session_state.get(f"{user_session_id}_use_persona", True):
        pages.append({
            "title": t("ui.system_welcome_title"),
            "content": t("ui.system_welcome_content"),
            "image": "personas_main_ui.png"
        })

        pages.append({
            "title": t("ui.system_role_title"),
            "content": t("ui.system_role_content"),
            "image": "personas_intro.png"
        })

        pages.append({
            "title": t("ui.system_ai_feedback_title"),
            "content": t("ui.system_ai_feedback_content"),
            "image": "persona_ai_feedback.png"
        })
        
    else:
        pages.append({
            "title": t("ui.system_welcome_title"),
            "content": t("ui.system_welcome_content"),
            "image": "no_personas_main_ui.png"
        })

        pages.append({
            "title": t("ui.system_role_title"),
            "content": t("ui.system_role_content"),
            "image": "no_personas_intro.png"
        })

        pages.append({
            "title": t("ui.system_ai_feedback_title"),
            "content": t("ui.system_ai_feedback_content"),
            "image": "no_persona_ai_feedback.png"
        })

    

    pages.append({
        "title": t("ui.system_saved_ideas_title"),
        "content": t("ui.system_saved_ideas_content"),
        "image": "collect.gif"
    })

    if st.session_state.get(f"{user_session_id}_enable_scamper_input", True):
        pages.append({
            "title": t("ui.system_free_input_title"),
            "content": t("ui.system_free_input_content"),
            "image": "free_text.png"
        })


        pages.append({
            "title": t("ui.system_scamper_input_title"),
            "content": t("ui.system_scamper_input_content"),
            "image": "scamper.png"
        })
    else:
        pages.append({
            "title": t("ui.system_free_input_title"),
            "content": t("ui.system_free_input_content"),
            "image": "free_text.png"
        })

    return pages

if st.session_state.get(f"{user_session_id}_show_onboarding_modal", True):
    show_onboarding_tabs()  # 原本那一段顯示多頁的流程邏輯
    

# 側邊欄：配置本地 API（折疊式）
with st.sidebar:
    with st.expander(f"**{t('ui.model_settings')}**", expanded=False):  # 預設折疊
        st.header(t("ui.model_settings"))
        selected_model = st.selectbox(t("ui.select_model"), ["gpt-4o-mini", "gpt-4o"], index=1, disabled=is_locked)
        base_url = None
        if "gpt" not in selected_model:
            base_url = st.text_input(t("ui.api_endpoint"), "http://127.0.0.1:1234/v1")
        rounds = st.slider(t("ui.rounds"), min_value=1, max_value=999, value=999, disabled=is_locked)
        temperature = st.slider(t("ui.temperature"), min_value=0.0, max_value=2.0, value=1.0, step=0.1, disabled=is_locked)


        if is_locked:
            st.info(t("ui.system_locked"))

        
with st.sidebar:
    with st.expander(f"**{t('ui.usage_guide')}**", expanded=True):
        st.markdown(t("ui.usage_guide_content"))
        if st.button(t("ui.review_guide_again")):
            st.session_state[f"{user_session_id}_show_onboarding_modal"] = True
            st.rerun()



# 根據角色設定是否啟用決定 title
if st.session_state[f"{user_session_id}_use_persona"]:
    if st.session_state[f"{user_session_id}_enable_scamper_input"]:
        title_setting = "LLM + Human Discussion Framework \n"
        title_setting += "✔ Personas + ✔ Free Text Input + ✔ SCAMPER"
    else:
        title_setting = "LLM + Human Discussion Framework \n"
        title_setting += "✔ Personas + ✔ Free Text Input + ✘ SCAMPER"
else:
    if st.session_state[f"{user_session_id}_enable_scamper_input"]:
        title_setting = "LLM + Human Discussion Framework \n"
        title_setting += "✘ Personas + ✔ Free Text Input + ✔ SCAMPER"
    else:
        title_setting = "LLM + Human Discussion Framework \n"
        title_setting += "✘ Personas + ✔ Free Text Input + ✘ SCAMPER"
st.title(title_setting)

# 停止執行如果 API 端點未設置
if not base_url and "gpt" not in selected_model:
    st.warning(t("ui.enter_api_endpoint"), icon="⚠️")
    st.stop()

# LLM 配置
# llm_config = {
#     "config_list": [
#         {
#             "model": selected_model,
#             "api_key": api_key,
#             "base_url": base_url,
#             "temperature": temperature,
#             "stream": True
#         }
#     ]
# }

if f"{user_session_id}_llm_config" not in st.session_state:
    st.session_state[f"{user_session_id}_llm_config"] = {
        "config_list": [
            {
                "model": selected_model,
                "api_key": api_key,
                "base_url": base_url,
                "temperature": temperature,
                "stream": False
            }
        ]
    }


@st.cache_data
def load_prompts(lang):
    with open(f"prompts/{lang}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def get_prompt(key):
    lang = st.session_state.get(f"{user_session_id}_language", "zh-TW")
    prompts = load_prompts(lang)

    keys = key.split(".")
    val = prompts
    for k in keys:
        val = val.get(k, {})

    return val if val else key

Businessman_prompt = get_prompt("agents.businessman.prompt")

Engineer_prompt = get_prompt("agents.engineer.prompt")

neutral_prompt = get_prompt("agents.neutral.prompt")


AGENT_CONFIG = {
    "Agent A": {
        "persona_name": "Businessman",
        "persona_prompt": Businessman_prompt,
        "neutral_name": "Agent A",
        "avatar": "businessman.png"
    },
    "Agent B": {
        "persona_name": "Engineer",
        "persona_prompt": Engineer_prompt,
        "neutral_name": "Agent B",
        "avatar": "engineer.png"
    }
}


llm_config = st.session_state[f"{user_session_id}_llm_config"]


def get_display_name(tag: str) -> str:
    if st.session_state[f"{user_session_id}_use_persona"]:
        return AGENT_CONFIG[tag]["persona_name"]
    return AGENT_CONFIG[tag]["neutral_name"]

def get_avatar_by_agent_role(role_name: str) -> str:
    # 先看是不是 Assistant 或 User
    if role_name == "Assistant":
        return "🛠️"
    elif role_name == "User":
        return "🧑"

    # 判斷是否 persona 模式有開啟
    if st.session_state.get(f"{user_session_id}_use_persona", True):
        # persona 模式開啟：用 persona name 對應圖
        for tag, config in AGENT_CONFIG.items():
            if role_name == config["persona_name"]:
                return config["avatar"]
    else:
        # persona 模式關閉：用 neutral name 對應不同圖（像 agent_a.png）
        if role_name == "Agent A":
            return "agent_a.png"
        elif role_name == "Agent B":
            return "agent_b.png"

    # fallback
    return "🤖"

def get_avatar_by_agent_name(name: str) -> str:
    # 根據現在 persona 開關，找到目前對應的名字
    for tag, config in AGENT_CONFIG.items():
        if name in [config["persona_name"], config["neutral_name"]]:
            return agent_avatars.get(get_display_name(tag), "🤖")
    return agent_avatars.get(name, "🤖")  # fallback 給 Assistant 或 User


# Function to sanitize names
def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

def format_peer_responses(responses: dict, current_agent: str) -> tuple[str, str]:
    peer_lines = []
    self_line = ""

    for name, resp in responses.items():
        display_name = name  # 預設
        # 根據目前模式，從 agent config 找到對應顯示名
        for tag, config in AGENT_CONFIG.items():
            if name in [config["persona_name"], config["neutral_name"]]:
                display_name = get_display_name(tag)

        if name == current_agent:
            self_line = f"{t('prompt.self_previous')}\n{resp.strip()}"
        elif name != "User":
            peer_lines.append(f"{t('prompt.peer_said').format(name=display_name)}\n{resp.strip()}")

    peer_block = "\n\n".join(peer_lines)
    return self_line, peer_block


# Initialize question
if f"{user_session_id}_user_question" not in st.session_state:
    st.session_state[f"{user_session_id}_user_question"] = ""
# Initialize chat history
if f"{user_session_id}_messages" not in st.session_state:
    st.session_state[f"{user_session_id}_messages"] = []

if f"{user_session_id}_discussion_started" not in st.session_state:
    st.session_state[f"{user_session_id}_discussion_started"] = False

if f"{user_session_id}_round_num" not in st.session_state:
    st.session_state[f"{user_session_id}_round_num"] = 0

# Initialize or retrieve user input storage
if f"{user_session_id}_user_inputs" not in st.session_state:
    st.session_state[f"{user_session_id}_user_inputs"] = {}

if f"{user_session_id}_show_input" not in st.session_state:
    st.session_state[f"{user_session_id}_show_input"] = True

if f"{user_session_id}_this_round_combined_responses" not in st.session_state:
    st.session_state[f"{user_session_id}_this_round_combined_responses"] = {}

if f"{user_session_id}_proxy_message_showed" not in st.session_state:
    st.session_state[f"{user_session_id}_proxy_message_showed"] = False

if f"{user_session_id}_selected_technique" not in st.session_state:
    st.session_state[f"{user_session_id}_selected_technique"] = {}

if f"{user_session_id}_idea_options" not in st.session_state:
    st.session_state[f"{user_session_id}_idea_options"] = {}

if f"{user_session_id}_idea_list" not in st.session_state:
    st.session_state[f"{user_session_id}_idea_list"] = []

if f"{user_session_id}_selected_persistent_ideas" not in st.session_state:
    st.session_state[f"{user_session_id}_selected_persistent_ideas"] = {}

if f"{user_session_id}_current_input_method" not in st.session_state:
    st.session_state[f"{user_session_id}_current_input_method"] = {1: "free_input"}
    
if f"{user_session_id}_agent_restriction" not in st.session_state:
    st.session_state[f"{user_session_id}_agent_restriction"] = {0: list(AGENT_CONFIG.keys())}

if f"{user_session_id}_ai_feedback_enabled" not in st.session_state:
    st.session_state[f"{user_session_id}_ai_feedback_enabled"] = True


# 初始化每輪的完成狀態
rounds = 99  # 假設總輪數是 99，可以根據需求調整
for i in range(rounds + 1):  # 包括第 0 輪
    if f"{user_session_id}_round_{i}_completed" not in st.session_state:
        st.session_state[f"{user_session_id}_round_{i}_completed"] = False

# 初始化每輪的完成狀態
rounds = 99  # 假設總輪數是 99，可以根據需求調整
for i in range(rounds + 1):  # 包括第 0 輪
    if f"{user_session_id}_round_{i}_input_completed" not in st.session_state:
        st.session_state[f"{user_session_id}_round_{i}_input_completed"] = False


# 初始化代理的回覆狀態
def initialize_agent_states(round_num, agents):
    if f"{user_session_id}_round_{round_num}_agent_states" not in st.session_state:
        st.session_state[f"{user_session_id}_round_{round_num}_agent_states"] = {
            agent_name: False for agent_name in agents.keys()
        }

def safe_markdown_blocks(text):
    lines = text.split('\n')
    blocks = [line.strip() for line in lines if line.strip()]
    return blocks
import re

def smart_sentence_split(text: str) -> list[str]:
    # 暫時把 markdown 粗體/斜體句子抽出來
    markdown_blocks = {}

    def replacer(match):
        key = f"__MARKDOWN_BLOCK_{len(markdown_blocks)}__"
        markdown_blocks[key] = match.group(0)
        return key

    # 把所有 **...** 或 __...__ 保護起來
    protected_text = re.sub(r'(\*\*.*?\*\*|__.*?__)', replacer, text)

    # 正常切句（句號等）
    sentences = re.split(r'(?<=[。！？.!?])', protected_text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 還原被保護的 markdown 區塊
    restored = []
    for s in sentences:
        for key, value in markdown_blocks.items():
            s = s.replace(key, value)
        restored.append(s)

    return restored

def get_dynamic_agent_avatars() -> dict:
    avatars = {}
    for tag, config in AGENT_CONFIG.items():
        current_name = get_display_name(tag)

        if st.session_state[f"{user_session_id}_use_persona"]:
            # persona 模式開啟，顯示對應 persona 頭像
            avatars[current_name] = config["avatar"]
        else:
            # persona 模式關閉，對應 neutral_name 顯示專屬圖示
            if current_name == "Agent A":
                avatars[current_name] = "agent_a.png"
            elif current_name == "Agent B":
                avatars[current_name] = "agent_b.png"

    avatars["Assistant"] = "🛠️"
    avatars["User"] = "🧑"
    return avatars

agent_avatars = get_dynamic_agent_avatars()

# with st.sidebar:
#     st.write(agent_avatars)

for message in st.session_state[f"{user_session_id}_messages"]:
    avatar_display = get_avatar_by_agent_name(message["role"])

    if message["role"] == "user":
        # 先把 Markdown 轉換成 HTML
        html_content = markdown2.markdown(message["content"])  # 解析 Markdown 為 HTML

        st.markdown(
            f"""
            <div style="display: flex; justify-content: flex-end; margin: 10px 0;">
                <div style="
                    background-color: #DCF8C6; 
                    padding: 12px 16px;
                    border-radius: 18px;
                    max-width: 50%;
                    text-align: left;
                    box-shadow: 1px 1px 5px rgba(0,0,0,0.1);
                    white-space: normal;
                ">
                    {html_content}  <!-- 這裡的內容會正確解析 -->
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if message["role"] == "assistant":
            with st.chat_message("assistant"):
                sentences = smart_sentence_split(message["content"])
                for sentence in sentences:
                    html = markdown2.markdown(sentence)
                    st.markdown(html, unsafe_allow_html=True)
        else:
            with st.chat_message(message["role"], avatar=avatar_display):
                sentences = smart_sentence_split(message["content"])
                for sentence in sentences:
                    html = markdown2.markdown(sentence)
                    st.markdown(html, unsafe_allow_html=True)

# 更新某代理的回覆狀態
def mark_agent_completed(round_num, agent_name):
    st.session_state[f"{user_session_id}_round_{round_num}_agent_states"][agent_name] = True


async def single_round_discussion(round_num, agents, user_proxy):
    initialize_agent_states(round_num, agents)

    # 確保 agent_restriction 本輪有設定
    current_round = st.session_state[f"{user_session_id}_round_num"]
    if current_round not in st.session_state[f"{user_session_id}_agent_restriction"]:
        st.session_state[f"{user_session_id}_agent_restriction"][current_round] = list(AGENT_CONFIG.keys())


    if round_num == 0:

        discussion_message = get_prompt("discussion.round_start").format(
            round=round_num,
            question=st.session_state[f"{user_session_id}_user_question"]
        )

        discussion_message_for_showing = t("ui.round_start_display").format(
            question=st.session_state[f"{user_session_id}_user_question"]
        )

    else:

        # 上一輪的討論紀錄  
        last_round_response = {}
        for agent_name, response in st.session_state[f"{user_session_id}_this_round_combined_responses"].items():
            if agent_name in ["User"]:
                continue
            last_round_response[agent_name] = response

        current_method = st.session_state[f"{user_session_id}_current_input_method"].get(
            st.session_state[f"{user_session_id}_round_num"],
            "free_input"
        )

        if current_method == "scamper_input":
            SCAMPER_KEYS = [
                "substitute",
                "combine",
                "adapt",
                "modify",
                "put_to_use",
                "eliminate",
                "reverse"
            ]

            label_to_key = {
                t(f"ui.scamper.{k}.label"): k for k in SCAMPER_KEYS
            }

            selected_technique = st.session_state[f"{user_session_id}_selected_technique"].get(round_num - 1, "")
            selected_key = label_to_key.get(selected_technique)

            technique_description = (
                t(f"ui.scamper.{selected_key}.description")
                if selected_key
                else "（未找到對應的解釋）"
            )

            selected_idea = st.session_state[f"{user_session_id}_user_inputs"].get(round_num - 1, "")

            discussion_message = get_prompt("discussion.scamper_input").format(
                question=st.session_state[f"{user_session_id}_user_question"],
                round=round_num,
                idea=selected_idea,
                technique_label=selected_technique,
                technique_description=technique_description
            )

        elif current_method == "free_input":
            user_input = st.session_state[f"{user_session_id}_user_inputs"].get(round_num - 1, "")

            discussion_message = get_prompt("discussion.free_input").format(
                question=st.session_state[f"{user_session_id}_user_question"],
                round=round_num,
                user_input=user_input
            )

            discussion_message_for_showing = user_input            

    for agent_name, agent in agents.items():
        # 最後一個 agent 後等待user_input後再進行下一輪
        if agent_name == "User":
            this_round_method = st.session_state[f"{user_session_id}_selected_technique"].get(round_num, "")
            this_round_idea = st.session_state[f"{user_session_id}_user_inputs"].get(round_num, "")

            # st.write(f"this_round_method: {this_round_method}")
            # st.write(f"this_round_idea: {this_round_idea}")


            # 處理用戶輸入，只針對當前輪次
            if this_round_idea != "":
                next_round = st.session_state.get(f"{user_session_id}_round_num", 0) + 1
                agents = st.session_state[f"{user_session_id}_agent_restriction"].get(next_round, ["未選擇"])

                feedback_text = t("ui.feedback_yes") if st.session_state[f"{user_session_id}_ai_feedback_enabled"] else t("ui.feedback_no")
                agent_text = ", ".join([get_display_name(a) for a in agents])

                if this_round_method == "":
                    this_round_user_idea = f"{this_round_idea}\n\n"
                    this_round_user_idea_show_feedback = t("ui.user_feedback_free").format(
                        idea=this_round_idea,
                        agents=agent_text,
                        feedback=feedback_text
                    )
                else:

                    this_round_user_idea = t("ui.user_feedback_scamper").format(
                        idea=this_round_idea,
                        technique=f"SCAMPER：{this_round_method}",
                        description=t(f"scamper.{this_round_method}.description"),
                        agents=agent_text,
                        feedback=feedback_text
                    )
                    this_round_user_idea_show_feedback = this_round_user_idea

                # Add user message to chat history
                st.session_state[f"{user_session_id}_messages"].append({"role": "user", "content": this_round_user_idea_show_feedback})
                st.session_state[f"{user_session_id}_round_{round_num}_input_completed"] = True
                st.session_state[f"{user_session_id}_this_round_combined_responses"]["User"] = this_round_method
                st.session_state[f"{user_session_id}_selected_technique"][round_num] = this_round_method
                st.session_state[f"{user_session_id}_user_inputs"][round_num] = this_round_idea
                st.session_state[f"{user_session_id}_proxy_message_showed"] = False

                return True
            else:
                # 等待輸入
                return False
        elif agent_name == "Assistant":
            # pass
            if f"{user_session_id}_round_{round_num}_agent_states" in st.session_state and st.session_state[f"{user_session_id}_round_{round_num}_agent_states"][agent_name]:
                # st.write(f"{agent_name} 已完成")
                continue

            this_round_response = {}
            for agent_name_each, response in st.session_state[f"{user_session_id}_this_round_combined_responses"].items():
                if agent_name_each in ["User", "Assistant"]:
                    continue
                this_round_response[agent_name_each] = response

            category_prompt = get_prompt("assistant.category_prompt").format(
                responses=this_round_response
            )

            response = await agent.a_initiate_chat(user_proxy, message=category_prompt, max_turns=1, clear_history=True)
            response = response.chat_history[-1]["content"].strip()
            st.session_state[f"{user_session_id}_this_round_combined_responses"][agent_name] = response
            
            mark_agent_completed(round_num, agent_name)

            # **解析 Assistant 產出的可選 Idea**
            idea_options = re.findall(r"✅ Idea \d+: (.+)", response)
            st.session_state[f"{user_session_id}_idea_options"][f"round_{round_num}"] = idea_options

            for idea in idea_options:
                if idea not in st.session_state[f"{user_session_id}_idea_list"]:
                    st.session_state[f"{user_session_id}_idea_list"].append(idea)

            # st.write(f"登記 {agent_name} 完成")


        elif agent_name in st.session_state[f"{user_session_id}_agent_restriction"][st.session_state[f"{user_session_id}_round_num"]]:
            # 第0輪之後才限制字數
            if round_num == 0:
                persona_info = f"{agents[agent_name].system_message}\n\n" if st.session_state[f"{user_session_id}_use_persona"] else ""

                discussion_message_temp = discussion_message + get_prompt("agent_response.round0_suffix").format(
                    persona_info=persona_info
                )
                
                # discussion_message_for_showing = discussion_message_for_showing + (
                #     f"\n\n- 請根據你的專業視角回答！\n\n"
                #     # f"\n\n🎭 {agents[agent_name].system_message}\n\n"
                #     f"\n\n- 請僅從你的專業領域知識出發，不要提供一般性的回答！\n\n"
                #     f"\n\n- 請勿脫離你的專業範圍，不要提供非專業的建議或回應。\n\n"
                # )

            else:                
                # 額外加上 peer feedback 區塊
                peer_feedback_block = ""

                if st.session_state.get(f"{user_session_id}_ai_feedback_enabled", False):
                    last_round_response = {
                        k: v for k, v in st.session_state[f"{user_session_id}_this_round_combined_responses"].items()
                        if k not in ["User", "Assistant"]
                    }

                    self_response, peer_feedback = format_peer_responses(last_round_response, current_agent=agent_name)

                    if peer_feedback != "":
                        peer_feedback_block += get_prompt("agent_response.peer_feedback_with_others").format(
                            self_response=self_response.strip(),
                            peer_feedback=peer_feedback.strip()
                        )
                else:
                    last_round_response = {
                        k: v for k, v in st.session_state[f"{user_session_id}_this_round_combined_responses"].items()
                        if k not in ["User", "Assistant"]
                    }

                    self_response, peer_feedback = format_peer_responses(last_round_response, current_agent=agent_name)

                    if peer_feedback != "":
                        peer_feedback_block += (
                            f"---\n\n"
                            f"你自己上次的觀點：\n\n「{self_response.strip()}」\n\n"
                        )

                
                discussion_message_temp = discussion_message  # 先從第一段開始組


                if current_method == t("ui.free_input"):
                    section1 = get_prompt("agent_response.section1_free_input")
                else:
                    technique = st.session_state[f"{user_session_id}_selected_technique"].get(round_num, t("ui.not_specified"))
                    section1 = get_prompt("agent_response.section1_scamper").format(
                        technique=technique
                    )

                # =========================
                # 🧩 組合 Agent 回答格式（identity_block）
                # =========================

                # 🔹 Step 1：決定是否需要「第2段（回應其他 Agent）」
                # 有開啟 AI feedback → 要 section2
                # 沒開 → 不需要
                section2 = (
                    get_prompt("agent_response.section2_with_feedback")
                    if st.session_state[f"{user_session_id}_ai_feedback_enabled"]
                    else get_prompt("agent_response.section2_without_feedback")
                )

                # 🔹 Step 2：決定範例（有沒有包含第2段）
                example_text = (
                    get_prompt("agent_response.example_with_feedback")
                    if st.session_state[f"{user_session_id}_ai_feedback_enabled"]
                    else get_prompt("agent_response.example_without_feedback")
                )

                # 🔹 Step 3：決定使用哪種 Prompt 模板
                # 有 persona → 帶角色設定
                # 沒 persona → 中立版本
                template_key = (
                    "agent_response.identity_with_persona"
                    if st.session_state[f"{user_session_id}_use_persona"]
                    else "agent_response.identity_without_persona"
                )

                # 🔹 Step 4：組合完整 Prompt
                # ⚠️ 真正的 prompt 內容在 JSON（prompts/*.json）
                # 這裡只是把變數塞進去
                identity_block = get_prompt(template_key).format(
                    persona=agents[agent_name].system_message,  # 角色描述（Businessman / Engineer）
                    section1=section1,                         # 第一段指示（前面已組好）
                    section2=section2,                         # 是否包含第二段
                    example=example_text                       # 範例（幫助模型理解格式）
                )

                # 🧩 組合成完整 prompt
                discussion_message_temp = discussion_message

                if peer_feedback_block:
                    discussion_message_temp += "\n\n" + peer_feedback_block

                discussion_message_temp += "\n\n" + identity_block

                # with st.chat_message("assistant"):
                #     st.write("主設定值:", st.session_state.get(f"{user_session_id}_ai_feedback_enabled"))
                #     st.write("FreeInput:", st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input"))
                #     st.write("SCAMPER:", st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input"))
                #     st.markdown(discussion_message_temp)


            # 可能不會用到, 因為User輸入為主
            if not st.session_state[f"{user_session_id}_proxy_message_showed"]:
                if round_num == 0: # 現在只有第0輪會顯示
                    with st.chat_message("assistant"):
                        st.markdown(discussion_message_for_showing)

                    st.session_state[f"{user_session_id}_proxy_message_showed"] = True

                    st.session_state[f"{user_session_id}_messages"].append({"role": "assistant", "content": discussion_message_for_showing})

                
            if f"{user_session_id}_round_{round_num}_agent_states" in st.session_state and st.session_state[f"{user_session_id}_round_{round_num}_agent_states"][agent_name]:
                # st.write(f"{agent_name} 已完成")
                continue

            response = await agent.a_initiate_chat(user_proxy, message=discussion_message_temp, max_turns=1, clear_history=True)
            response = response.chat_history[-1]["content"].strip()
            st.session_state[f"{user_session_id}_this_round_combined_responses"][agent_name] = response

            # 切成句子（也可以自訂切法）
            # sentences = re.split(r'(?<=[。！？])', response.strip())
            # sentences = [s.strip() for s in sentences if s.strip()]
            # js_array = "[" + ",".join([f"`{s}`" for s in sentences]) + "]"
            
            avatar_display = get_avatar_by_agent_name(agent_name)
            with st.chat_message(agent_name, avatar=avatar_display):
                fadein_markdown(response)

            

            # Add assistant response to chat history
            st.session_state[f"{user_session_id}_messages"].append({"role": agent_name, "content": response})
            mark_agent_completed(round_num, agent_name)
            # st.write(f"登記 {agent_name} 完成")
 
    # return True

def fadein_markdown(md_text, delay=0.4):
    # 切句：遇到中英文標點就分句
    sentences = smart_sentence_split(md_text)

    # 注入 fade-in CSS
    st.markdown("""
    <style>
    .fade-in {
        opacity: 0;
        animation: fadeInAnim 0.6s ease forwards;
    }
    @keyframes fadeInAnim {
        to { opacity: 1; }
    }
    </style>
    """, unsafe_allow_html=True)

    # 一句一句顯示
    for sentence in sentences:
        html = markdown2.markdown(sentence)
        st.markdown(f"<div class='streamlit-default fade-in'>{html}</div>", unsafe_allow_html=True)
        time.sleep(delay)


# 在輸入框消失後顯示提示，然後再顯示下一輪輸入框
if not st.session_state[f"{user_session_id}_show_input"]:
    st.write(
        t(
            "ui.round_input_completed",
            round=st.session_state[f"{user_session_id}_round_num"] - 1
        )
    )
    st.session_state[f"{user_session_id}_show_input"] = True

if f"{user_session_id}_user_proxy" not in st.session_state:
    st.session_state[f"{user_session_id}_user_proxy"] = UserProxyAgent(
        name=sanitize_name(f"User_{user_session_id}"),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )


# 建議改成這樣
if f"{user_session_id}_agents" not in st.session_state:
    agents = {}

    for tag, config in AGENT_CONFIG.items():
        display_name = get_display_name(tag)  # 用於 prompt / 顯示
        system_message = config["persona_prompt"] if st.session_state[f"{user_session_id}_use_persona"] else neutral_prompt
        agents[tag] = ConversableAgent(  # <== 用 tag 當 key，例如 Agent A / Agent B
            name=sanitize_name(f"{tag}_{user_session_id}"),  # 或 display_name 也行
            llm_config=llm_config,
            system_message=system_message,
            code_execution_config={"use_docker": False}
        )

    agents["Assistant"] = ConversableAgent(
        name=sanitize_name(f"Assistant_{user_session_id}"),
        llm_config=llm_config,
        system_message=get_prompt("agents.assistant.prompt"),
        code_execution_config={"use_docker": False}
    )

    agents["User"] = UserProxyAgent(
        name=sanitize_name(f"User_{user_session_id}"),
        llm_config=llm_config,
        human_input_mode="NEVER",
        code_execution_config={"use_docker": False}
    )

    st.session_state[f"{user_session_id}_agents"] = agents

# with st.sidebar:
#     st.write(st.session_state[f"{user_session_id}_agents"])
    
if not st.session_state.get(f"{user_session_id}_discussion_started", False):
    question_options = [
        t("questions.placeholder"),
        t("questions.q1"),
        t("questions.q2"),
        t("questions.q3"),
        # t("questions.custom")
    ]
    
    selected_question = st.selectbox(t("ui.select_question"), question_options)

    # **如果選擇 "🔧 自訂問題"，顯示輸入框**
    if selected_question == t("questions.custom"):
        custom_question = st.text_input(
            t("questions.custom_input"),
            value=st.session_state.get(f"{user_session_id}_user_question", "")
        )
        question = custom_question if custom_question else t("questions.custom_input")
    else:
        question = selected_question

    # **確保 question 存入 session_state**
    if question != t("questions.placeholder"):
        st.session_state[f"{user_session_id}_user_question"] = question

        # **開始按鈕**
        if st.button(t("ui.start_discussion")):
            for agent in st.session_state[f"{user_session_id}_agents"].values():
                agent.clear_history()  # 清空內部記憶

            st.session_state[f"{user_session_id}_discussion_started"] = True
            st.session_state[f"{user_session_id}_round_num"] = 0
            st.session_state[f"{user_session_id}_integrated_message"] = t(
                "ui.integrated_message_round0",
                round=0,
                question=st.session_state[f"{user_session_id}_user_question"]
            )
            st.rerun()  # **強制重新整理頁面，隱藏選擇問題的 UI**

if st.session_state[f"{user_session_id}_discussion_started"] and st.session_state[f"{user_session_id}_round_num"] <= rounds:
    
    round_num = st.session_state[f"{user_session_id}_round_num"]
    # 執行單輪討論
    completed = asyncio.run(single_round_discussion(
        st.session_state[f"{user_session_id}_round_num"], st.session_state[f"{user_session_id}_agents"], st.session_state[f"{user_session_id}_user_proxy"]
    ))

    # **每輪結束後，讓使用者選擇 AI 產生的 Idea**
    round_num = st.session_state[f"{user_session_id}_round_num"]
    idea_options = st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", [])

    if idea_options:
        with st.expander(f"**{t('ui.round_idea_expander', round=round_num)}**", expanded=True):
            st.write(t("ui.round_idea_summary"))

            for idea in idea_options:
                if idea in st.session_state[f"{user_session_id}_selected_persistent_ideas"]:
                    continue  # **如果 Idea 已收藏，就不顯示在這裡**

                # **使用 Checkbox 來選擇收藏**
                if st.checkbox(f"{idea}", key=f"select_{round_num}_{idea}"):
                    # **加入收藏並記錄輪數**
                    st.session_state[f"{user_session_id}_selected_persistent_ideas"][idea] = round_num
                    st.toast(t("ui.idea_saved_toast", idea=idea, round=round_num))  # 顯示通知
                    st.rerun()  # **重新刷新頁面**

    if not st.session_state[f"{user_session_id}_round_{round_num}_input_completed"]:

        enable_scamper_input = st.session_state[f"{user_session_id}_enable_scamper_input"]
    
        tab_labels = [t("ui.free_input"), t("ui.scamper_input")] if enable_scamper_input else [t("ui.free_input")]
        tabs = st.tabs(tab_labels)


        for i, tab in enumerate(tabs):
            if tab_labels[i] == t("ui.free_input"):
                with tab:
                    with st.container(border=True):
                        user_inputs = st.text_area(
                            f"**{t('ui.input_round_idea', round_num=st.session_state[f'{user_session_id}_round_num'])}**"
                        )
                    
                    with st.expander(f"**{t('ui.ai_response_settings')}**", expanded=True):
                        # 限制可選的 Agent 為 "Businessman" 和 "Engineer"
                        available_agents = [get_display_name(tag) for tag in AGENT_CONFIG]

                        selected_agents = st.multiselect(
                            f"**{t('ui.select_agents_for_round', round=st.session_state[f'{user_session_id}_round_num'])}**",
                            options=list(AGENT_CONFIG.keys()),
                            default=list(AGENT_CONFIG.keys()),
                            format_func=lambda tag: get_display_name(tag),
                            key=f"{user_session_id}_selected_agents_{round_num}_free_input"
                        )

                        # 是否要互相給對方Agent的回答
                        if f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input" not in st.session_state:
                            st.session_state[f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input"] = True
                        
                        st.checkbox(
                            f"**{t('ui.enable_ai_feedback')}**",
                            key=f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input",
                            disabled=len(selected_agents) < 2
                        )

                        
                        if len(selected_agents) < 2:
                            st.info(t("ui.ai_feedback_requires_two_agents"))

                    if st.button(t("ui.submit_selection"), key=f"{user_session_id}_submit_{round_num}_free_input"):
                        st.session_state[f"{user_session_id}_agent_restriction"][st.session_state[f"{user_session_id}_round_num"]+1] = selected_agents
                        st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]+1] = "free_input"

                        ai_feedback_enabled = st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input", True)
                        if len(selected_agents) < 2:
                            ai_feedback_enabled = False
                        st.session_state[f"{user_session_id}_ai_feedback_enabled"] = ai_feedback_enabled

                        
                        if user_inputs != "":
                            st.session_state[f"{user_session_id}_user_inputs"][round_num] = user_inputs
                            st.session_state[f"{user_session_id}_selected_technique"][round_num] = ""

                            user_inputs = ""

                            completed = asyncio.run(single_round_discussion(
                                st.session_state[f"{user_session_id}_round_num"], st.session_state[f"{user_session_id}_agents"], st.session_state[f"{user_session_id}_user_proxy"]
                            ))

            elif tab_labels[i] == t("ui.scamper_input"):
                with tab:
                    # **方式 2：使用 selectbox 選擇創意思考技術**
                    with st.container(border=True):
                        st.write(f"**{t('ui.select_creative_technique')}**")
                        idea_source = st.radio(
                            f"**{t('ui.idea_source')}**",
                            [
                                f"**{t('ui.current_round_ideas', round_num=round_num)}**",
                                f"**{t('ui.saved_idea_source')}**"
                            ]
                        )

                        if idea_source == f"**{t('ui.current_round_ideas', round_num=round_num)}**":
                            if st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", []):
                                idea_options = st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", [])
                        else:
                            idea_options = list(st.session_state[f"{user_session_id}_selected_persistent_ideas"].keys())

                        # 🔧 移除 Markdown 格式
                        idea_options_cleaned = [re.sub(r'(\*\*|__)(.*?)\1', r'\2', idea) for idea in idea_options]


                        # 傳入 Idea 的多選選項
                        user_inputs = st.multiselect(
                            f"**{t('ui.select_ideas_to_extend', idea_source=idea_source)}**",
                            idea_options_cleaned
                        )
                        
                    
                        SCAMPER_KEYS = [
                            "substitute",
                            "combine",
                            "modify",
                            "adapt",
                            "put_to_use",
                            "eliminate",
                            "reverse"
                        ]

                        

                        selected_scamper = st.radio(
                            f"**{t('ui.select_creative_technique')}**",
                            SCAMPER_KEYS,
                            format_func=lambda k: t(f"ui.scamper.{k}.label"),
                            horizontal=True
                        )

                        scamper_idea_limits = {
                            "substitute": 1,
                            "combine": 2,
                            "adapt": 1,
                            "modify": 1,
                            "put_to_use": 1,
                            "eliminate": 1,
                            "reverse": 1
                        }

                        # ⛔ 檢查選取的 Idea 數量是否超過限制
                        max_allowed = scamper_idea_limits.get(selected_scamper, 1)

                        st.caption(
                            t(
                                "ui.technique_max_ideas",
                                technique=t(f"ui.scamper.{selected_scamper}.label"),
                                count=max_allowed
                            )
                        )

                        # 顯示說明與例子
                        if selected_scamper:
                            st.success(
                                t(
                                    "ui.scamper_selected_summary",
                                    technique=t(f"ui.scamper.{selected_scamper}.label"),
                                    description=t(f"ui.scamper.{selected_scamper}.description"),
                                    example=t(f"ui.scamper.{selected_scamper}.example")
                                )
                            )
                            

                        if len(user_inputs) > max_allowed:
                            st.warning(t("ui.too_many_ideas_selected", count=max_allowed))
                            st.stop()  # 或者 st.session_state 鎖住送出按鈕
                            
                    with st.expander(f"**{t('ui.ai_response_settings')}**", expanded=True):
                        # 限制可選的 Agent 為 "Businessman" 和 "Engineer"
                        available_agents = [get_display_name(tag) for tag in AGENT_CONFIG]

                        selected_agents = st.multiselect(
                            f"**{t('ui.select_agents_for_round', round=st.session_state[f'{user_session_id}_round_num'])}**",
                            options=list(AGENT_CONFIG.keys()),
                            default=list(AGENT_CONFIG.keys()),
                            format_func=lambda tag: get_display_name(tag),
                            key=f"{user_session_id}_selected_agents_{round_num}_scamper_input"
                        )
                        
                        if f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input" not in st.session_state:
                            st.session_state[f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input"] = True
                        
                        st.checkbox(
                            f"**{t('ui.enable_ai_feedback')}**",
                            key=f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input",
                            disabled=len(selected_agents) < 2
                        )
                        
                        if len(selected_agents) < 2:
                            st.info(t("ui.ai_feedback_requires_two_agents"))

                    if st.button(t("ui.submit_selection"), key=f"{user_session_id}_submit_{round_num}_scamper_input"):
                        ai_feedback_enabled = st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input", False)
                        if len(selected_agents) < 2:
                            ai_feedback_enabled = False
                        st.session_state[f"{user_session_id}_ai_feedback_enabled"] = ai_feedback_enabled

                        
                        
                        st.session_state[f"{user_session_id}_agent_restriction"][st.session_state[f"{user_session_id}_round_num"]+1] = selected_agents
                        st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]+1] = "scamper_input"
                        if selected_scamper and user_inputs is not None:
                            # 保存 Idea 和 Selected Idea
                            st.session_state[f"{user_session_id}_user_inputs"][round_num] = st.session_state[f"{user_session_id}_user_inputs"][round_num] = ", ".join(user_inputs)
                            st.session_state[f"{user_session_id}_selected_technique"][round_num] = selected_scamper

                            selected_main = ""
                            selected_sub = ""

                        completed = asyncio.run(single_round_discussion(
                            st.session_state[f"{user_session_id}_round_num"], st.session_state[f"{user_session_id}_agents"], st.session_state[f"{user_session_id}_user_proxy"]
                        ))


    if completed:
        # 如果該輪完成，進入下一輪
        # st.write(f"已完成第 {st.session_state.round_num} 輪，進入第 {st.session_state.round_num + 1} 輪")
        st.session_state[f"{user_session_id}_round_num"] += 1

        # ✅ 事先為下一輪補上預設值
        next_round = st.session_state[f"{user_session_id}_round_num"]
        if next_round not in st.session_state[f"{user_session_id}_agent_restriction"]:
            st.session_state[f"{user_session_id}_agent_restriction"][next_round] = list(AGENT_CONFIG.keys())

        store_messages(silent=True)  # 儲存對話紀錄到 Supabase
        # time.sleep(1)
        st.rerun()


# 設定 Pop-up 狀態變數
if f"{user_session_id}_show_idea_dialog" not in st.session_state:
    st.session_state[f"{user_session_id}_show_idea_dialog"] = False
if f"{user_session_id}_is_loading" not in st.session_state:
    st.session_state[f"{user_session_id}_is_loading"] = False  # 控制 `st.spinner()` 顯示狀態

with st.sidebar:
    with st.expander(f"**{t('ui.saved_ideas')}**", expanded=True):
        if not st.session_state[f"{user_session_id}_selected_persistent_ideas"]:
            st.info(t("ui.no_saved_ideas"))
        else:
            ideas_to_remove = []
            for idea, round_collected in st.session_state[f"{user_session_id}_selected_persistent_ideas"].items():
                col1, col2 = st.columns([0.85, 0.15])

                with col1:
                    st.write(f"✅ {idea}  \n（{t('ui.saved_idea_round', round=round_collected)}）")

                with col2:
                    if st.button(":material/delete:", key=f"delete_saved_{idea}", help=t("ui.delete_saved_idea"), use_container_width=True):
                        ideas_to_remove.append(idea)

            # 刪除邏輯
            if ideas_to_remove:
                for idea in ideas_to_remove:
                    del st.session_state[f"{user_session_id}_selected_persistent_ideas"][idea]
                    if idea not in st.session_state[f"{user_session_id}_idea_list"]:
                        st.session_state[f"{user_session_id}_idea_list"].append(idea)

                st.warning(t("ui.removed_saved_ideas", count=len(ideas_to_remove)))
                st.rerun()
        
            # 清理 Markdown 的小工具函數
            def strip_markdown(text):
                text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # **粗體**
                text = re.sub(r"\*(.*?)\*", r"\1", text)      # *斜體*
                text = re.sub(r"_(.*?)_", r"\1", text)        # _斜體_
                text = re.sub(r"!\[.*?\]\(.*?\)", "", text)   # ![圖片](url)
                text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [文字](url)
                return text.strip()

            # 將收藏的 Idea 資料轉成 DataFrame
            persistent_ideas = st.session_state.get(f"{user_session_id}_selected_persistent_ideas", {})
            discussion_topic = st.session_state.get(f"{user_session_id}_user_question", t("ui.default_topic"))


            if persistent_ideas:
                df = pd.DataFrame([
                    {
                        t("ui.topic"): discussion_topic,
                        t("ui.idea"): strip_markdown(idea),
                        t("ui.saved_round"): round_collected
                    }
                    for idea, round_collected in persistent_ideas.items()
                ])

                # 加入 UTF-8 BOM（\ufeff）確保 Excel 不會亂碼
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                csv_data = '\ufeff' + csv_buffer.getvalue()
                csv_bytes = csv_data.encode("utf-8")

                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"Collected_Ideas_{now_str}.csv"

                # 建立下載按鈕
                st.download_button(
                    label=t("ui.download_saved_ideas_csv"),
                    data=csv_bytes,
                    file_name=filename,
                    mime="text/csv",
                )


def strip_markdown(text):
    # 去除 Markdown 標記（粗體、斜體、連結、圖片等）
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # **粗體**
    text = re.sub(r"\*(.*?)\*", r"\1", text)      # *斜體*
    text = re.sub(r"_(.*?)_", r"\1", text)        # _斜體_
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)   # ![圖片](url)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [文字](url)
    return text.strip()