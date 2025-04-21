import streamlit as st
import asyncio
import re
from autogen import AssistantAgent, UserProxyAgent
from autogen import ConversableAgent
import pandas as pd
import plotly.express as px
import logging
import os
from dotenv import load_dotenv
import textwrap
import time
import uuid

import os
import shutil
import markdown2
import io
import datetime
import streamlit.components.v1 as components



os.environ["AUTOGEN_USE_DOCKER"] = "0"


# 設定 Streamlit 頁面
st.set_page_config(page_title="LLM + Human Discussion Framework", page_icon="🧑", layout="wide")

# 讓每個使用者有獨立的 session ID
if "user_session_id" not in st.session_state:
    st.session_state["user_session_id"] = str(uuid.uuid4())  # 產生隨機 ID
    
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
    st.title("功能設定")

    st.write("請先讓實驗人員選擇要啟用哪些功能：")

    # ❗用中繼變數來接收 checkbox 狀態
    use_persona_temp = st.checkbox(
        "啟用角色設定（影響語氣與觀點）",
        value=st.session_state.get(f"{user_session_id}_use_persona", True)
    )
    enable_scamper_temp = st.checkbox(
        "啟用 SCAMPER 創意思考技術",
        value=st.session_state.get(f"{user_session_id}_enable_scamper_input", True)
    )

    if st.button("設定完成"):
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



@st.dialog("系統說明", width="large")
def show_onboarding_tabs():
    st.html("<span class='big-dialog'></span>")
    st.warning("**請先閱讀完所有說明。**\n\n每次要關閉視窗都使用 **「開始使用！」** 按鈕關閉，**不要使用右上角的「❌」**，否則說明會一直重覆出現喔！")

    # 構建頁面
    pages = build_onboarding_pages()
    tab_titles = [p["title"] for p in pages]

    tabs = st.tabs(tab_titles)
    for tab, page in zip(tabs, pages):
        with tab:
            st.write(page["content"])
            # if "image" in page:
            #     st.image(page["image"], width=1500)
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

    if st.button("開始使用！", type="primary"):
        st.session_state[f"{user_session_id}_show_onboarding_modal"] = False
        st.rerun()




def build_onboarding_pages():
    pages = []


    if st.session_state.get(f"{user_session_id}_use_persona", True):
        pages.append({
            "title": "歡迎來到創意討論平台",
            "content": "這是一個「AI 多角色討論框架」系統，幫助使用者快速發想創新點子，透過角色對話，激盪出更多點子！",
            "image": "personas_main_ui.png"
        })

        pages.append({
            "title": "角色互動",
            "content": (
                        "你會看到兩個 AI 角色一同參與討論，具有不同專業背景：\n"
                        "創業家（Businessman） 注重「這能不能賣」、「吸不吸引人」，\n"
                        "工程師（Engineer） 注重「這能不能做」、「技術會不會太難」。\n"
                    ),
            "image": "personas_intro.png"
        })
        
    else:
        pages.append({
            "title": "歡迎來到創意討論平台",
            "content": "這是一個「AI 多角色討論框架」系統，幫助使用者快速發想創新點子，透過角色對話，激盪出更多點子！",
            "image": "no_personas_main_ui.png"
        })

        pages.append({
            "title": "角色互動",
            "content": "你將與兩位虛擬角色（Agent A & Agent B）進行討論，每輪會收到不同觀點的創意想法。",
            "image": "no_personas_intro.png"
        })

    pages.append({
            "title": "AI 互相回饋",
            "content": (f"你可以選擇是否讓兩位角色互相回饋彼此的觀點。"
                        f"這樣的設定能讓他們針對你的想法進行更深入的延伸與對話，激發出更多靈感！"
                        f"同時根據討論的情況，也可以指定只讓其中一位角色參與回應。"),
            "image": "persona_ai_feedback.png"
    })

    pages.append({
        "title": "收藏點子 & 導出",
        "content": "跟角色互動後出現某些喜歡某個點子嗎？可以勾選收藏之後留著之後討論！",
        "image": "collect.gif"
    })

    if st.session_state.get(f"{user_session_id}_enable_scamper_input", True):
        pages.append({
        "title": "自由輸入",
        "content": "你可以自由輸入想法，就像跟 ChatGPT 互動一樣，Agent 會依據你想法繼續跟你討論。",
        "image": "free_text.png"
        })


        pages.append({
            "title": "SCAMPER 創意思考工具",
            "content": "你可以選擇創意思考技術（SCAMPER）來延伸你選定的 idea，例如：替代、結合、修改等。",
            "image": "scamper.png"
        })
    else:
        pages.append({
            "title": "自由輸入",
            "content": "你可以自由輸入想法，就像跟 ChatGPT 互動一樣，Agent 會依據你想法繼續跟你討論。",
            "image": "free_text.png"
        })

    return pages

if st.session_state.get(f"{user_session_id}_show_onboarding_modal", True):
    show_onboarding_tabs()  # 原本那一段顯示多頁的流程邏輯
    

# 側邊欄：配置本地 API（折疊式）
with st.sidebar:
    with st.expander("**模型與 API 設定**", expanded=False):  # 預設折疊
        st.header("模型與 API 設定")
        selected_model = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=1, disabled=is_locked)
        base_url = None
        if "gpt" not in selected_model:
            base_url = st.text_input("API 端點", "http://127.0.0.1:1234/v1")
        rounds = st.slider("設定討論輪次", min_value=1, max_value=999, value=999, disabled=is_locked)
        temperature = st.slider("設定溫度 (temperature)", min_value=0.0, max_value=2.0, value=1.0, step=0.1, disabled=is_locked)
        

        if is_locked:
            st.info("已開始討論，設定已鎖定。")

        
with st.sidebar:
    with st.expander("**使用說明**", expanded=True):
        st.markdown("""
        這是一個結合 LLM 與多角色討論的創意發想工具，幫助你探索不同觀點、刺激靈感！

        ### 你可以怎麼用？
        - 每一輪提供你的想法
        - AI 角色根據不同角度給出回饋與延伸想法
        - 收藏你喜歡的 Idea 並繼續討論，或是以你的想法為主導
        
        """)
        if st.button("再看一次說明"):
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
    st.warning("請輸入 API 端點！", icon="⚠️")
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

Businessman_prompt = (
    "你是 Businessman。你是一位在矽谷創業的創辦人，具備出色的產品直覺與商業敏銳度，曾參與多次 seed round 募資。"
    "你習慣使用的語言包括：market-fit、user pain point、growth loop、viral trigger、pivot、go-to-market strategy、early adopters、unit economics。"
    "當你提出想法時，請以創投簡報（pitch deck）語氣表達，重點是能否引起使用者共鳴、快速測試商業模式、創造市場話題。"

    "🎯 你的目標是："
    "1️⃣ 找到具有 **使用者吸引力** 和 **潛在成長性** 的市場切入點\n"
    "2️⃣ 提出點子要能支撐 **故事性**，讓投資人、媒體、使用者會興奮地想參與\n"
    "3️⃣ 評估每個點子的 go-to-market 可行性與潛在 revenue stream"

    "🚫 請避免："
    "談論技術實作細節、工程可行性或開發負擔；你只關心『這東西會不會紅』。"

    "💬 常用語氣範例："
    "- 『這是一個有潛力切入 Z 世代市場的 viral loop』\n"
    "- 『這解法非常 pitchable，而且容易吸引早期 media coverage』\n"
    "- 『我們可以用 freemium 模型驗證 user retention，再逐步轉向付費方案』"
)


Engineer_prompt = (
    "你是 Engineer。你是這家新創的首席工程師，負責產品的技術落地與資源調度，熟悉 MVP 開發、模組化設計與系統效能考量。"
    "你重視的是：**可行性、可擴充性、技術負債控制、維護性、以及團隊 bandwidth 是否足夠實作**。"

    "你慣用的詞彙包括：tech stack、latency、code debt、CI/CD、RESTful API、data pipeline、load test、edge case、resource constraint、infra cost。"

    "🎯 你的目標是："
    "1️⃣ 在預算與時間（2 週內）限制下，找出 **可以做出來的版本**\n"
    "2️⃣ 評估每個點子從技術觀點有無『高風險地雷』或明顯 impractical 的設計\n"
    "3️⃣ 主動提出替代技術方案或更快的技術驗證方法"

    "🚫 請避免："
    "過度關注市場、品牌或使用者成長策略；你只關心『這東西 build 不 build 得出來』。"

    "💬 常用語氣範例："
    "- 『這個需要 edge device 做數據前處理，否則 cloud latency 太高』\n"
    "- 『我傾向先用 Python 快速測 MVP，再重構成更穩的堆疊』\n"
    "- 『這個想法不錯，但我們沒足夠 bandwidth 支援 BLE 通訊與 UI 同時開發』"
)

neutral_prompt = (
    "你是討論創意問題的中立參與者，目標是提出清晰、有邏輯且具啟發性的創新建議。"
    "請根據使用者的主題與思考方法，提出合理、有創新潛力的觀點，不需考慮特定專業或立場。"
)


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
            self_line = f"🧠 **你上一輪提到的觀點：**\n{resp.strip()}"
        elif name != "User":
            peer_lines.append(f"💬 **{display_name} 說：**\n{resp.strip()}")

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

# if f"{user_session_id}_current_input" not in st.session_state:
#     st.session_state[f"{user_session_id}_current_input"] = ""

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
    st.session_state[f"{user_session_id}_current_input_method"] = {1: "自由輸入"}

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
    # elif message["role"] == "history":
    #      with st.expander(f"對話紀錄", expanded=False):
    #         st.markdown(message["content"], unsafe_allow_html=True)
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

    if round_num == 0:
        discussion_message = (
            f"**第 {round_num} 輪討論**\n\n"
            f"請直接列出與『{st.session_state[f'{user_session_id}_user_question']}』相關的創新點子，每個點子請附上一句簡短的主要用途，最多 **不超過兩句**。\n\n"
        )


        # 用於顯示給使用者的內容（簡化版）
        discussion_message_for_showing = f"請提供與 **{st.session_state[f"{user_session_id}_user_question"]}** 相關的創意點子，每個點子附加簡單用途即可。"
    else:

        # 上一輪的討論紀錄  
        last_round_response = {}
        for agent_name, response in st.session_state[f"{user_session_id}_this_round_combined_responses"].items():
            if agent_name in ["User"]:
                continue
            last_round_response[agent_name] = response

        if st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]] == "選擇創意思考技術":
            # **創意思考技術對應的解釋**
            technique_explanations = {                
                # SCAMPER 方法
                "SCAMPER - Substitute（替代）": "用另一種材料或方法替代原本的某個部分。",
                "SCAMPER - Combine（結合）": "把兩個不同的產品或功能合併成新的東西。",
                "SCAMPER - Adapt（適應）": "將一個產品的特性應用到另一個產品上。",
                "SCAMPER - Modify（修改）": "改變尺寸、形狀、顏色等，讓它更吸引人。",
                "SCAMPER - Put to another use（變更用途）": "讓一個東西變成完全不同的用途。",
                "SCAMPER - Eliminate（刪除）": "移除某些不必要的部分，讓產品更簡單。",
                "SCAMPER - Reverse（反轉）": "顛倒順序、角色，產生新的可能性。",
            }

            # **取得使用者選擇的技術**
            selected_technique = st.session_state[f"{user_session_id}_selected_technique"].get(round_num-1, "")

            # **獲取對應的解釋**
            technique_description = technique_explanations.get(selected_technique, "（未找到對應的解釋）")


            discussion_message = (
                f"這輪我們持續延伸「{st.session_state[f'{user_session_id}_user_question']}」這個主題的創意。\n\n"
                f"- **第 {round_num} 輪討論** \n\n"
                f"- **請聚焦在以下創意進行延伸思考：**\n\n"
                f"- 使用者選擇的創意：**{st.session_state[f'{user_session_id}_user_inputs'].get(round_num-1, '')}**\n\n"
                f"- 使用的創意思考技術：**{selected_technique}**\n\n"
                f"- 方法應用說明：{technique_description}\n\n"
            )


            # discussion_message_for_showing = (
            #     f"這輪我們持續延伸「{st.session_state[f'{user_session_id}_user_question']}」這個主題的創意。\n\n"
            #     f"- **第 {round_num} 輪討論** 🔄\n\n"
            #     f"- **請聚焦在以下創意進行延伸思考：**\n\n"
            #     f"- 使用者選擇的創意：**{st.session_state[f'{user_session_id}_user_inputs'].get(round_num-1, '')}**\n\n"
            #     f"- 使用的創意思考技術：**{selected_technique}**\n\n"
            #     f"- 方法應用說明：{technique_description}\n\n"
            #     f"- 請從你的專業視角出發，針對這個創意延伸一個有價值的新想法。\n"
            # )
        
        elif st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]] == "自由輸入":
            discussion_message = (
                f"這輪我們持續延伸「{st.session_state[f'{user_session_id}_user_question']}」這個主題的創意。\n\n"
                f"第 {round_num} 輪討論 \n\n"
                f"使用者的想法： 「{st.session_state[f'{user_session_id}_user_inputs'].get(round_num-1, '')}」 \n\n"
                # f"📌 **上一輪討論紀錄:** {last_round_response}\n\n"
                # f"📝 **請基於上一輪的討論和使用者的想法做延伸！**\n\n "
            )
            discussion_message_for_showing = st.session_state[f"{user_session_id}_user_inputs"].get(round_num-1, "")

    for agent_name, agent in agents.items():
        # 最後一個 agent 後等待user_input後再進行下一輪
        if agent_name == "User":
            this_round_method = st.session_state[f"{user_session_id}_selected_technique"].get(round_num, "")
            this_round_idea = st.session_state[f"{user_session_id}_user_inputs"].get(round_num, "")

            # st.write(f"this_round_method: {this_round_method}")
            # st.write(f"this_round_idea: {this_round_idea}")

            technique_explanations = {                
                # SCAMPER 方法
                "SCAMPER - Substitute（替代）": "用另一種材料或方法替代原本的某個部分。",
                "SCAMPER - Combine（結合）": "把兩個不同的產品或功能合併成新的東西。",
                "SCAMPER - Adapt（適應）": "將一個產品的特性應用到另一個產品上。",
                "SCAMPER - Modify（修改）": "改變尺寸、形狀、顏色等，讓它更吸引人。",
                "SCAMPER - Put to another use（變更用途）": "讓一個東西變成完全不同的用途。",
                "SCAMPER - Eliminate（刪除）": "移除某些不必要的部分，讓產品更簡單。",
                "SCAMPER - Reverse（反轉）": "顛倒順序、角色，產生新的可能性。",
            }



            # 處理用戶輸入，只針對當前輪次
            if this_round_idea != "":
                if this_round_method == "":
                    next_round = st.session_state.get(f"{user_session_id}_round_num", 0) + 1
                    agents = st.session_state[f"{user_session_id}_agent_restriction"].get(next_round, ["未選擇"])

                    this_round_user_idea = (f"{this_round_idea}\n\n")
                    this_round_user_idea_show_feedback = (f"- **使用者輸入：**{this_round_idea}\n\n"
                    f"- **選擇回答的 Agent：**{', '.join([get_display_name(a) for a in agents])}\n\n"
                    f"- **是否開啟 Agent 互相回饋：** {'是' if st.session_state[f'{user_session_id}_ai_feedback_enabled'] else '否'}\n\n"
                    # f"- **是否啟用 Agent Personas：** {'是' if st.session_state[f'{user_session_id}_use_persona'] else '否'}\n\n"
                    )

                else:                    
                    next_round = st.session_state.get(f"{user_session_id}_round_num", 0) + 1
                    agents = st.session_state[f"{user_session_id}_agent_restriction"].get(next_round, ["未選擇"])

                    this_round_user_idea = (
                    f"- **使用者選擇的創意：**「{this_round_idea}」\n\n"
                    f"- **使用者選擇的創意思考技術：**「{this_round_method}」\n\n"
                    f"- **方法應用說明：** {technique_explanations[this_round_method]}\n\n"
                    f"- **選擇回答的 Agent：**{', '.join([get_display_name(a) for a in agents])}\n\n"
                    f"- **是否開啟 Agent 互相回饋：** {'是' if st.session_state[f'{user_session_id}_ai_feedback_enabled'] else '否'}\n\n"
                    # f"- **是否啟用 Agent Personas：** {'是' if st.session_state[f'{user_session_id}_use_persona'] else '否'}\n\n"
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

            category_prompt = (
                f"你是一個擅長資訊統整的 AI，負責從不同 AI 助手的回應中，"
                f"**綜合相似觀點，去除重複內容，並直接輸出精煉的 Idea**。"

                f"\n\n**這一輪的討論紀錄：**"
                f"\n{this_round_response}"

                f"\n\n**請根據以下規則統整 Idea，並且回應格式只包含整理過的 Idea 清單：**"
                f"\n1️⃣ **合併相似的 Idea**：如果多個 AI 提出了類似的想法，請合併它們，使內容更簡潔有力。"
                f"\n2️⃣ **刪除冗餘內容**：去除任何相同或過於接近的 Idea，避免重複。"
                f"\n3️⃣ **確保每個 Idea 具有清晰的描述**，使其可以獨立理解。"
                f"\n4️⃣ **格式要求**：回應時請只輸出以下格式，**不要添加其他文字、說明或總結**。"

                f"\n **統整後的可選 Idea（請以「概念: 說明」的格式回應）：**\n"
                f"\n✅ Idea 1: **概念 1**，這裡請填入合併後的說明"
                f"\n✅ Idea 2: **概念 2**，這裡請填入合併後的說明"
                f"\n✅ Idea 3: **概念 3**，這裡請填入合併後的說明"
                f"\n✅ Idea N: **概念 N**，這裡請填入合併後的說明"

                f"\n\n⚠️ **請確保你的回應只包含這些整理後的 Idea，並在最後提供 2-3 句話的摘要，歸納討論的核心重點。"
                f"不要額外補充說明、分析或其他內容。**"
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

                discussion_message_temp = discussion_message + (
                    f"**請確保：**\n"
                    f"1.  **每個創意點子名稱清楚**\n"
                    f"2.  **用途簡明扼要（1 句話最佳，最多 2 句話）**\n"
                    f" {persona_info}\n\n"
                    f"請用以上的角色設定來發想點子，並確保格式如下：\n"
                    f"✅ **Idea 1** - 主要用途（最多兩句）\n"
                    f"✅ **Idea 2** - 主要用途（最多兩句）\n"
                    f"✅ **Idea 3** - 主要用途（最多兩句）\n"
                    f"✅ **Idea N** - 主要用途（最多兩句）\n"
                    f"確保以zh-TW語言回應。\n\n"

                )
                discussion_message_for_showing = discussion_message_for_showing + (
                    f"\n\n- 請根據你的專業視角回答！\n\n"
                    # f"\n\n🎭 {agents[agent_name].system_message}\n\n"
                    f"\n\n- 請僅從你的專業領域知識出發，不要提供一般性的回答！\n\n"
                    f"\n\n- 請勿脫離你的專業範圍，不要提供非專業的建議或回應。\n\n"
                )

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
                        peer_feedback_block += (
                            f"---\n\n"
                            f"你自己的觀點：\n\n「{self_response.strip()}」\n\n"
                            f"👀 你也看到其他 Agent 的一些觀點，例如：\n\n「{peer_feedback.strip()}」\n\n"
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


                if st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]] == "自由輸入":
                    section1 = (
                        f"**1. 我覺得**：請以一句粗體句子到句點開頭，回應使用者的輸入內容（用第一人稱），"
                        f"清楚表達你這輪的創新主張，表達你這輪的創新主張與延伸（用第一人稱），並且換兩行，接著補充說明，總長度約 2～3 句。\n\n"
                    )
                else:
                    technique = st.session_state[f"{user_session_id}_selected_technique"].get(round_num, "（未指定技術）")
                    section1 = (
                        f"**1. 我覺得**：請以一句粗體句子到句點開頭，應用 {technique} 的邏輯來延伸使用者的選擇創意（用第一人稱），"
                        f"表達你這輪的創新主張與延伸（用第一人稱），並且換兩行，接著補充說明，總長度約 2～3 句。\n\n"
                    )

                # 🔹 第三段：身份與風格提醒（結尾固定加）
                if st.session_state[f"{user_session_id}_use_persona"]:
                    # 有 persona 的 Agent, 有 peer feedback
                    if st.session_state[f'{user_session_id}_ai_feedback_enabled']:
                        identity_block = (
                            f"---\n\n"
                            f"- 你的角色設定：{agents[agent_name].system_message}\n\n"
                            f"請根據以下格式，依序完成兩段角色回應，並務必遵守格式規定：\n\n"
                            f"{section1}"
                            f"**2. 對另一位角色的回應**：用一句粗體句子到句點開頭，點出你對上輪某角色觀點的認同、質疑、或補充，並且加上，接著補述你的延伸觀點，總長度約 2～3 句。\n\n"
                            f"請絕對遵守不要寫出「主張內容：」或「對另一位角色的回應：」等提示文字，只輸出內容本身。\n\n"
                            f"`1.` 和 `2.` 段落標號請務必寫出來，**不能省略！**\n\n"
                            f"請務必按照上面格式，每段都以「粗體主張句」開頭（用句號結尾），其後用自然語言補充描述。\n\n"
                            f"不需要加入任何 emoji 或多餘開頭語（如：以下是我的建議）。"
                            f"格式範例如下：\n\n"
                            f"**1. 我主張應結合風箏文化與節慶活動來創造品牌識別。**\n\n"
                            f"這樣不僅能讓消費者更有情感連結，也能利用節慶集中曝光，強化市場話題性。\n\n"
                            f"**2. 我認同 Engineer 提出的模組化概念，但建議以教育活動來強化理解。**\n\n"
                            f"模組化雖具彈性，但若能配合實體教學或展示活動，能幫助用戶更快上手，也更利於推廣。"
                            f"---\n\n"
                        )
                    # 有 persona 的 Agent, 沒有 peer feedback
                    elif st.session_state[f'{user_session_id}_ai_feedback_enabled'] == False:
                        identity_block = (
                            f"---\n\n"
                            f"- 你的角色設定：{agents[agent_name].system_message}\n\n"
                            f"請根據以下格式，依序完成兩段角色回應，並務必遵守格式規定：\n\n"
                            f"{section1}"
                            f"請絕對遵守不要寫出「主張內容：」或「對另一位角色的回應：」等提示文字，只輸出內容本身。\n\n"
                            f"`1.` 和 `2.` 段落標號請務必寫出來，**不能省略！**\n\n"
                            f"請務必按照上面格式，每段都以「粗體主張句」開頭（用句號結尾），其後用自然語言補充描述。\n\n"
                            f"不需要加入任何 emoji 或多餘開頭語（如：以下是我的建議）。"
                            f"格式範例如下：\n\n"
                            f"**1. 我主張應結合風箏文化與節慶活動來創造品牌識別。**\n\n"
                            f"這樣不僅能讓消費者更有情感連結，也能利用節慶集中曝光，強化市場話題性。\n\n"
                            f"---\n\n"
                        )
                elif st.session_state[f"{user_session_id}_use_persona"] == False:
                    # 沒有 persona 的 Agent, 有 peer feedback
                    if st.session_state[f'{user_session_id}_ai_feedback_enabled']:
                        identity_block = (
                            f"請根據以下格式，依序完成角色回應，並務必遵守格式規定：\n\n"
                            f"{section1}"
                            f"**2. 對另一位角色的回應**：用一句粗體句子到句點開頭，點出你對上輪某角色觀點的認同、質疑、或補充，並且加上\n\n，接著補述你的延伸觀點，總長度約 2～3 句。\n\n"
                            f"請絕對遵守不要寫出「主張內容：」等提示文字，只輸出內容本身。\n\n"
                            f"`1.` 和 `2.` 段落標號請務必寫出來，**不能省略！**\n\n"
                            f"請務必按照上面格式，每段都以「粗體主張句」開頭（用句號結尾），其後用自然語言補充描述。\n\n"
                            f"不需要加入任何 emoji 或多餘開頭語（如：以下是我的建議）。"
                            f"格式範例如下：\n\n"
                            f"**1. 我主張應結合風箏文化與節慶活動來創造品牌識別。**\n\n"
                            f"這樣不僅能讓消費者更有情感連結，也能利用節慶集中曝光，強化市場話題性。\n\n"
                            f"**2. 我認同 Engineer 提出的模組化概念，但建議以教育活動來強化理解。**\n\n"
                            f"模組化雖具彈性，但若能配合實體教學或展示活動，能幫助用戶更快上手，也更利於推廣。"
                            f"---\n\n"
                        )
                    elif st.session_state[f'{user_session_id}_ai_feedback_enabled'] == False:
                        # 沒有 persona 的 Agent, 沒有 peer feedback
                        identity_block = (
                            f"請根據以下格式，完成角色回應，並務必遵守格式規定：\n\n"
                            f"{section1}"
                            f"請絕對遵守不要寫出「主張內容：」等提示文字，只輸出內容本身。\n\n"
                            f"`1.` 和 `2.` 段落標號請務必寫出來，**不能省略！**\n\n"
                            f"請務必按照上面格式，每段都以「粗體主張句」開頭（用句號結尾），其後用自然語言補充描述。\n\n"
                            f"不需要加入任何 emoji 或多餘開頭語（如：以下是我的建議）。"
                            f"格式範例如下：\n\n"
                            f"**1. 我主張應結合風箏文化與節慶活動來創造品牌識別。**\n\n"
                            f"這樣不僅能讓消費者更有情感連結，也能利用節慶集中曝光，強化市場話題性。\n\n"
                            f"---\n\n"
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
    st.write(f"已完成第 {st.session_state[f"{user_session_id}_round_num"] - 1} 輪的輸入！")
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
        system_message="你是 Assistant，負責將點子...",
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
        "請選擇討論問題",
        # "風箏除了娛樂，還能用什麼其他創意用途？",
        # "枕頭除了睡覺，還能如何幫助放鬆或解決日常問題？",
        "如果穿越空間技術存在，可能會有哪些全新的交通方式？",
        # "如果穿越時間技術存在，可能會有哪些全新的交通方式？",
        "磚頭除了蓋房子，還能有哪些意想不到的用途？",
        "掃帚除了掃地，還能有哪些意想不到的用途？",
        # "🔧 自訂問題"
    ]
    
    selected_question = st.selectbox("請選擇討論問題：", question_options)

    # **如果選擇 "🔧 自訂問題"，顯示輸入框**
    if selected_question == "🔧 自訂問題":
        custom_question = st.text_input("請輸入你的問題：", value=st.session_state.get(f"{user_session_id}_user_question", ""))
        question = custom_question if custom_question else "請輸入你的問題"
    else:
        question = selected_question

    # **確保 question 存入 session_state**
    if question != "請選擇討論問題":
        st.session_state[f"{user_session_id}_user_question"] = question

        # **開始按鈕**
        if st.button("開始 LLM 討論"):
            for agent in st.session_state[f"{user_session_id}_agents"].values():
                agent.clear_history()  # 清空內部記憶

            st.session_state[f"{user_session_id}_discussion_started"] = True
            st.session_state[f"{user_session_id}_round_num"] = 0
            st.session_state[f"{user_session_id}_integrated_message"] = f"這是第 0 輪討論，{st.session_state[f"{user_session_id}_user_question"]}。"
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
        with st.expander(f"**第 {round_num} 輪 AI 產生的創意點子**", expanded=True):
            st.write("經過這輪的討論，總結出以下幾個點子，有哪些想先收藏的嗎？")

            for idea in idea_options:
                if idea in st.session_state[f"{user_session_id}_selected_persistent_ideas"]:
                    continue  # **如果 Idea 已收藏，就不顯示在這裡**

                # **使用 Checkbox 來選擇收藏**
                if st.checkbox(f"{idea}", key=f"select_{round_num}_{idea}"):
                    # **加入收藏並記錄輪數**
                    st.session_state[f"{user_session_id}_selected_persistent_ideas"][idea] = round_num
                    st.toast(f"已收藏：{idea}（第 {round_num} 輪）")  # 顯示通知
                    st.rerun()  # **重新刷新頁面**

    if not st.session_state[f"{user_session_id}_round_{round_num}_input_completed"]:

        enable_scamper_input = st.session_state[f"{user_session_id}_enable_scamper_input"]
    
        tab_labels = ["自由輸入", "選擇創意思考技術"] if enable_scamper_input else ["自由輸入"]
        tabs = st.tabs(tab_labels)


        for i, tab in enumerate(tabs):
            if tab_labels[i] == "自由輸入":
                with tab:
                    with st.container(border=True):
                        user_inputs = st.text_area(f"**請輸入第 {st.session_state[f"{user_session_id}_round_num"]} 輪的想法：**")
                    
                    with st.expander(f"**AI 回應設定**", expanded=True):
                        # 限制可選的 Agent 為 "Businessman" 和 "Engineer"
                        available_agents = [get_display_name(tag) for tag in AGENT_CONFIG]

                        # 更新 multiselect 讓使用者只能選這兩個角色
                        # selected_agents = st.multiselect(
                        #     f"**請選擇第 {st.session_state[f'{user_session_id}_round_num']} 輪回應的 Agent：**",
                        #     available_agents,  # 只允許這兩個選項
                        #     default=available_agents,  # 預設都勾選
                        #     key=f"{user_session_id}_selected_agents_{round_num}_free_input"
                        # )


                        selected_agents =  st.multiselect(
                            f"**請選擇第 {st.session_state[f'{user_session_id}_round_num']} 輪回應的 Agent：**",
                            options=list(AGENT_CONFIG.keys()),  # 真正用的是 tag
                            default=list(AGENT_CONFIG.keys()),
                            format_func=lambda tag: get_display_name(tag), # 顯示 persona/neutral name
                            key=f"{user_session_id}_selected_agents_{round_num}_free_input"
                        )

                        # 是否要互相給對方Agent的回答
                        # ai_feedback_enabled = st.checkbox("開啟 AI 互相回饋", value=st.session_state[f"{user_session_id}_ai_feedback_enabled"], key=f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input", disabled=len(selected_agents) < 2)
                        if f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input" not in st.session_state:
                            st.session_state[f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input"] = True
                        
                        st.checkbox(
                            "開啟 AI 互相回饋",
                            key=f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input",
                            disabled=len(selected_agents) < 2
                        )

                        # ai_feedback_enabled = st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_free_input", False)
                        
                        if len(selected_agents) < 2:
                            st.info("⚠️ 至少需要選擇兩位 Agent 才能啟用互相回饋功能")
                        #     ai_feedback_enabled = False
                        # st.session_state[f"{user_session_id}_ai_feedback_enabled"] = ai_feedback_enabled

                    if st.button("送出選擇", key=f"{user_session_id}_submit_{round_num}_free_input"):
                        st.session_state[f"{user_session_id}_agent_restriction"][st.session_state[f"{user_session_id}_round_num"]+1] = selected_agents
                        st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]+1] = "自由輸入"

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

            elif tab_labels[i] == "選擇創意思考技術":
                with tab:
                    # **方式 2：使用 selectbox 選擇創意思考技術**
                    with st.container(border=True):
                        idea_source = st.radio(f"**選擇創意來源**", [f"**第 {round_num} 輪 AI 產生的創意點子**", "**已收藏的 Idea**"])
                        if idea_source == f"**第 {round_num} 輪 AI 產生的創意點子**":
                            if st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", []):
                                idea_options = st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", [])
                        else:
                            idea_options = list(st.session_state[f"{user_session_id}_selected_persistent_ideas"].keys())

                        # 🔧 移除 Markdown 格式
                        idea_options_cleaned = [re.sub(r'(\*\*|__)(.*?)\1', r'\2', idea) for idea in idea_options]


                        # 傳入 Idea 的多選選項
                        user_inputs = st.multiselect(f"**請選擇您想延伸的Idea（來源：{idea_source}）**", idea_options_cleaned)
                        
                    

                        technique_explanations = {                
                            # SCAMPER 方法
                            "SCAMPER - Substitute（替代）": "用另一種材料或方法替代原本的某個部分。",
                            "SCAMPER - Combine（結合）": "把兩個不同的產品或功能合併成新的東西。",
                            "SCAMPER - Modify（修改）": "改變尺寸、形狀、顏色等，讓它更吸引人。",
                            "SCAMPER - Adapt（適應）": "將一個產品的特性應用到另一個產品上。",
                            "SCAMPER - Put to another use（變更用途）": "讓一個東西變成完全不同的用途。",
                            "SCAMPER - Eliminate（刪除）": "移除某些不必要的部分，讓產品更簡單。",
                            "SCAMPER - Reverse（反轉）": "顛倒順序、角色，產生新的可能性。",
                        }

                        technique_examples = {
                            "SCAMPER - Substitute（替代）": "用地瓜取代馬鈴薯，做出「地瓜薯條」。",
                            "SCAMPER - Combine（結合）": "耳機+帽子，做成「內建藍牙耳機的毛帽」。",
                            "SCAMPER - Adapt（適應）": "將運動鞋的設計靈感用在辦公拖鞋上，讓久站的工作者也能獲得支撐和舒適。",
                            "SCAMPER - Modify（修改）": "縮小漢堡，變成迷你漢堡，適合派對小食！",
                            "SCAMPER - Put to another use（變更用途）": "用舊行李箱變成寵物床，回收再利用！",
                            "SCAMPER - Eliminate（刪除）": "拿掉遊戲手柄的按鍵，改用體感控制，像是 Switch！",
                            "SCAMPER - Reverse（反轉）": "內餡放外面的「內倒披薩」，讓起司包住餅皮！",
                        }

                        # SCAMPER 技術選項
                        scamper_options = [
                            "Substitute（替代）",
                            "Combine（結合）",
                            "Modify（修改）",
                            "Adapt（適應）",
                            "Put to another use（變更用途）",
                            "Eliminate（刪除）",
                            "Reverse（反轉）"
                        ]

                        # SCAMPER 方法對應的最大 Idea 數量限制
                        scamper_idea_limits = {
                            "Substitute（替代）": 1,
                            "Combine（結合）": 2,
                            "Adapt（適應）": 1,
                            "Modify（修改）": 1,
                            "Put to another use（變更用途）": 1,
                            "Eliminate（刪除）": 1,
                            "Reverse（反轉）": 1
                        }


                        # 建立水平選單
                        cols = st.columns(len(scamper_options))  # 建立 N 個欄位
                        selected_scamper = None  # 初始化選擇變數

                        # 讓 radio 水平排列
                        selected_scamper = st.radio(
                            f"**請選擇要使用的創意技術：**",
                            scamper_options,
                            horizontal=True  # 💡 讓選項橫向排列
                        )

                        # ⛔ 檢查選取的 Idea 數量是否超過限制
                        max_allowed = scamper_idea_limits.get(selected_scamper, 1)

                        st.caption(f"⚙️ 技術「{selected_scamper}」最多只能選擇 {max_allowed} 個創意點子")

                        # 顯示說明與例子
                        if selected_scamper:
                            st.success(
                                f"- 你選擇的 SCAMPER 技術：SCAMPER - {selected_scamper}\n\n"
                                f"- 解釋：{technique_explanations[f"SCAMPER - {selected_scamper}"]}\n\n"
                                f"- 例子：{technique_examples[f"SCAMPER - {selected_scamper}"]}"
                        )
                            

                        if len(user_inputs) > max_allowed:
                            st.warning(f"⚠️ 已超過最大選擇數量（{max_allowed} 個），請減少選擇的 Idea。")
                            st.stop()  # 或者 st.session_state 鎖住送出按鈕
                            
                    with st.expander(f"**AI 回應設定**", expanded=True):
                        # 限制可選的 Agent 為 "Businessman" 和 "Engineer"
                        available_agents = [get_display_name(tag) for tag in AGENT_CONFIG]

                        # # 更新 multiselect 讓使用者只能選這兩個角色
                        # selected_agents = st.multiselect(
                        #     f"**請選擇第 {st.session_state[f'{user_session_id}_round_num']} 輪回應的 Agent：**",
                        #     available_agents,  # 只允許這兩個選項
                        #     default=available_agents,  # 預設都勾選
                        #     key=f"{user_session_id}_selected_agents_{round_num}_scamper_input"
                        # )

                        selected_agents =  st.multiselect(
                            f"**請選擇第 {st.session_state[f'{user_session_id}_round_num']} 輪回應的 Agent：**",
                            options=list(AGENT_CONFIG.keys()),  # 真正用的是 tag
                            default=list(AGENT_CONFIG.keys()),
                            format_func=lambda tag: get_display_name(tag), # 顯示 persona/neutral name
                            key=f"{user_session_id}_selected_agents_{round_num}_scamper_input"
                        )


                        # 是否要互相給對方Agent的回答
                        # ai_feedback_enabled = st.checkbox("開啟 AI 互相回饋", value=st.session_state[f"{user_session_id}_ai_feedback_enabled"], disabled=len(selected_agents) < 2, key=f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input")
                        
                        if f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input" not in st.session_state:
                            st.session_state[f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input"] = True
                        
                        st.checkbox(
                            "開啟 AI 互相回饋",
                            key=f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input",
                            disabled=len(selected_agents) < 2
                        )

                        # ai_feedback_enabled = st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input", False)
                        
                        if len(selected_agents) < 2:
                            st.info("⚠️ 至少需要選擇兩位 Agent 才能啟用互相回饋功能")
                        #     ai_feedback_enabled = False
                        # st.session_state[f"{user_session_id}_ai_feedback_enabled"] = ai_feedback_enabled

                    if st.button("送出選擇", key=f"{user_session_id}_submit_{round_num}_scamper_input"):
                        ai_feedback_enabled = st.session_state.get(f"{user_session_id}_ai_feedback_enabled_{round_num}_scamper_input", False)
                        if len(selected_agents) < 2:
                            ai_feedback_enabled = False
                        st.session_state[f"{user_session_id}_ai_feedback_enabled"] = ai_feedback_enabled

                        
                        
                        st.session_state[f"{user_session_id}_agent_restriction"][st.session_state[f"{user_session_id}_round_num"]+1] = selected_agents
                        st.session_state[f"{user_session_id}_current_input_method"][st.session_state[f"{user_session_id}_round_num"]+1] = "選擇創意思考技術"
                        if selected_scamper and user_inputs is not None:
                            # 保存 Idea 和 Selected Idea
                            st.session_state[f"{user_session_id}_user_inputs"][round_num] = st.session_state[f"{user_session_id}_user_inputs"][round_num] = ", ".join(user_inputs)
                            st.session_state[f"{user_session_id}_selected_technique"][round_num] = f"SCAMPER - {selected_scamper}"

                            selected_main = ""
                            selected_sub = ""

                        completed = asyncio.run(single_round_discussion(
                            st.session_state[f"{user_session_id}_round_num"], st.session_state[f"{user_session_id}_agents"], st.session_state[f"{user_session_id}_user_proxy"]
                        ))


    if completed:
        # 如果該輪完成，進入下一輪
        # st.write(f"已完成第 {st.session_state.round_num} 輪，進入第 {st.session_state.round_num + 1} 輪")
        st.session_state[f"{user_session_id}_round_num"] += 1
        # time.sleep(1)
        st.rerun()


# 設定 Pop-up 狀態變數
if f"{user_session_id}_show_idea_dialog" not in st.session_state:
    st.session_state[f"{user_session_id}_show_idea_dialog"] = False
if f"{user_session_id}_is_loading" not in st.session_state:
    st.session_state[f"{user_session_id}_is_loading"] = False  # 控制 `st.spinner()` 顯示狀態

with st.sidebar:
    with st.expander("**已收藏的 Idea**", expanded=True):
        if not st.session_state[f"{user_session_id}_selected_persistent_ideas"]:
            st.info("目前沒有收藏的 Idea。")
        else:
            ideas_to_remove = []
            for idea, round_collected in st.session_state[f"{user_session_id}_selected_persistent_ideas"].items():
                col1, col2 = st.columns([0.85, 0.15])

                with col1:
                    st.write(f"✅ {idea}  \n（第 {round_collected} 輪）")

                with col2:
                    if st.button(":material/delete:", key=f"delete_saved_{idea}", help="刪除這個 Idea", use_container_width=True):
                        ideas_to_remove.append(idea)

            # 刪除邏輯
            if ideas_to_remove:
                for idea in ideas_to_remove:
                    del st.session_state[f"{user_session_id}_selected_persistent_ideas"][idea]
                    if idea not in st.session_state[f"{user_session_id}_idea_list"]:
                        st.session_state[f"{user_session_id}_idea_list"].append(idea)

                st.warning(f"🗑️ 已移除 {len(ideas_to_remove)} 個收藏的 Idea")
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
            discussion_topic = st.session_state.get(f"{user_session_id}_user_question", "（無題目）")


            if persistent_ideas:
                df = pd.DataFrame([
                    {
                        "討論題目": discussion_topic,
                        "Idea": strip_markdown(idea),
                        "收藏輪數": round_collected
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
                    label="下載收藏的 Ideas（CSV）",
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