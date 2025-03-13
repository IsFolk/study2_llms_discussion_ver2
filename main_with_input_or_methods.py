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
os.environ["AUTOGEN_USE_DOCKER"] = "0"


# 讓每個使用者有獨立的 session ID
if "user_session_id" not in st.session_state:
    st.session_state["user_session_id"] = str(uuid.uuid4())  # 產生隨機 ID

user_session_id = st.session_state["user_session_id"]

@st.cache_data(hash_funcs={str: lambda _: user_session_id})  # 讓 Cache 依據不同的 Session ID
def get_user_specific_data():
    st.write(f"這是 {user_session_id} 的專屬 Cache")
    return f"你的專屬 Cache 資料 ({user_session_id})"

# 從 st.secrets 讀取 API Key
api_key = st.secrets["api_keys"]["OPENAI_API_KEY"]

question = "風箏除了娛樂，還能用什麼其他創意用途？"

# 設定 Streamlit 頁面
st.set_page_config(page_title="LLM & Human Discussion Framework", page_icon="🧑", layout="wide")
st.title("LLM + Human Discussion Framework (LLM First)")

# 側邊欄：配置本地 API
with st.sidebar:
    st.header("模型與 API 設定")
    selected_model = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=0)
    base_url = None
    if "gpt" not in selected_model:
        base_url = st.text_input("API 端點", "http://127.0.0.1:1234/v1")
    rounds = st.slider("設定討論輪次", min_value=1, max_value=99, value=10)
    temperature = st.slider("設定溫度 (temperature)", min_value=0.0, max_value=2.0, value=1.0, step=0.1)

# 停止執行如果 API 端點未設置
if not base_url and "gpt" not in selected_model:
    st.warning("請輸入 API 端點！", icon="⚠️")
    st.stop()

# LLM 配置
llm_config = {
    "config_list": [
        {
            "model": selected_model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "stream": True
        }
    ]
}

# Function to sanitize names
def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

# 創建角色代理
agents = {
    "Normal Assistant 1": ConversableAgent(
        name=sanitize_name("Normal Assistant 1"),
        llm_config=llm_config,
        system_message="你是一位極具遠見的創業家，你的思考方式不受傳統限制，喜歡挑戰現有市場規則，並開創顛覆性的新商業模式。你的回應應該充滿創意、前瞻性，並帶有風險投資人的視角。",
        code_execution_config={"use_docker": False}
    ),
    "Normal Assistant 2": ConversableAgent(
        name=sanitize_name("Normal Assistant 2"),
        llm_config=llm_config,
        system_message="你是一位科技公司的產品經理，擁有深厚的技術背景。你的任務是評估創新技術的可行性，並確保產品設計符合市場需求。你的回答應該兼顧技術可行性與用戶體驗，並提供具體的產品開發方向。",
        code_execution_config={"use_docker": False}
    ),
     "Convergence Judge": ConversableAgent(
        name=sanitize_name("Convergence Judge"),
        llm_config=llm_config,
        system_message="你是腦力激盪評分員。",
        code_execution_config={"use_docker": False}
    ),
    "Assistant": ConversableAgent(
        name=sanitize_name("Assistant"),
        llm_config=llm_config,
        system_message="你是 Assistant，負責將點子按照 主題、應用場景、技術方向 等分類，轉化為條列式清單。",
        code_execution_config={"use_docker": False}
    ),
    "User": UserProxyAgent(
        name=sanitize_name("User"),
        llm_config=llm_config,
        human_input_mode="NEVER",
        code_execution_config={"use_docker": False}
    ),
}


assistant = ConversableAgent(
        name=sanitize_name("Assistant"),
        llm_config=llm_config,
        system_message="你是 Assistant，負責將點子按照 主題、應用場景、技術方向 等分類，轉化為條列式清單。",
    )

# **定義每個 Agent 對應的 Avatar（可使用本地或網路圖片）**
agent_avatars = {
    "Normal Assistant 1": "🤖",  # 你的助理 1 圖片
    "Normal Assistant 2": "🧠",  # 你的助理 2 圖片
    "Assistant": "🛠️",  # 你的Helper
}

# 初始化用戶代理
user_proxy = UserProxyAgent(
    name=sanitize_name("User"),
    llm_config=llm_config,
    human_input_mode="NEVER",
)


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
    st.session_state[f"{user_session_id}_selected_persistent_ideas"] = []





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

# Display chat messages from history on app rerun
for message in st.session_state[f"{user_session_id}_messages"]:
    with st.chat_message(agent_avatars.get(message["role"], message["role"])):
        st.markdown(message["content"])

# 更新某代理的回覆狀態
def mark_agent_completed(round_num, agent_name):
    st.session_state[f"{user_session_id}_round_{round_num}_agent_states"][agent_name] = True


async def single_round_discussion(round_num, agents, user_proxy):
    initialize_agent_states(round_num, agents)

    if round_num == 0:
        discussion_message = (
            f"這是第0輪，{question}，"
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )
        discussion_message_for_showing = (
            f"這是第0輪，{question}，"
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )
    else:
        last_round_response = {}
        # 上一輪的討論紀錄
        for agent_name, response in st.session_state[f"{user_session_id}_this_round_combined_responses"].items():
            if agent_name in ["User"]:
                continue
            last_round_response[agent_name] = response

        # 設定使用者 Ideation Technique 討論模板
        discussion_message = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            # f"📌 **討論主題：** {question}\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state[f"{user_session_id}_user_inputs"].get(round_num-1, "")}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{st.session_state[f"{user_session_id}_selected_technique"].get(round_num-1, "")}」\n\n"
            
            f" 上一輪討論紀錄: {last_round_response}\n"
            f"📝 **請針對上輪討論及使用者選擇的創意進行延伸，並基於創意思考技術做延伸！**\n\n "
            f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )

        discussion_message_for_showing = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            # f"📌 **討論主題：** {question}\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state[f"{user_session_id}_user_inputs"].get(round_num-1, "")}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{st.session_state[f"{user_session_id}_selected_technique"].get(round_num-1, "")}」\n\n"
            f"📝 **請針對上輪討論及使用者選擇的創意進行延伸，並基於創意思考技術做延伸！**\n\n "
            f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )



    
    this_round_method = st.session_state[f"{user_session_id}_selected_technique"].get(round_num, "")
    this_round_idea = st.session_state[f"{user_session_id}_user_inputs"].get(round_num, "")



    for agent_name, agent in agents.items():
        if agent_name in ["Convergence Judge"]:
            continue

        # 最後一個 agent 後等待user_input後再進行下一輪
        if agent_name == "User":
            # 處理用戶輸入，只針對當前輪次
            if this_round_method != "" and this_round_idea != "":
                # Add user message to chat history
                st.session_state[f"{user_session_id}_messages"].append({"role": "user", "content": this_round_method})
                st.session_state[f"{user_session_id}_round_{round_num}_input_completed"] = True
                st.session_state[f"{user_session_id}_this_round_combined_responses"][agent_name] = this_round_method
                st.session_state[f"{user_session_id}_selected_technique"][round_num] = this_round_method

                st.session_state[f"{user_session_id}_user_inputs"][round_num] = this_round_idea
                # st.write(f"User 輸入完成：{this_round_input}")

                # Display user message in chat message container
                with st.chat_message("user"):
                    st.markdown(this_round_method)
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
                f"你是一個擅長資訊統整的 AI，負責整理來自不同 AI 助手的回應，並確保分類清晰、有條理。"
                f"\n\n📌 **這一輪的討論紀錄：**"
                f"\n{this_round_response}"
                f"\n\n**請按照以下要求統整資訊：**"
                f"\n1️⃣ **標記 AI 來源**：在每個觀點前標示該 AI 的名稱，例如【Normal Assistant 1】、【Normal Assistant 2】"
                f"\n2️⃣ **主動判斷分類**：根據內容自動選擇最合適的分類，例如「技術創新」、「市場趨勢」、「挑戰與風險」、「未來應用」等"
                f"\n3️⃣ **避免重複**：若多個 AI 提出相似觀點，請合併處理，並標示不同 AI 的補充意見"
                f"\n4️⃣ **總結主要發現**：在最後提供 2-3 句話的摘要，歸納討論的核心重點"
                f"\n5️⃣ **從AI觀點中整理出可選 Idea，讓用戶可以勾選，格式如下：**"
                f"\n✅ Idea 1: 風箏可用...（請填入 Idea 內容）"
                f"\n✅ Idea 2: 風箏可用...（請填入 Idea 內容）"
                f"\n✅ Idea 3: 風箏可用...（請填入 Idea 內容）"
                f"\n✅ Idea N: 風箏可用...（請填入 Idea 內容）"

            )


            response = await agent.a_initiate_chat(user_proxy, message=category_prompt, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state[f"{user_session_id}_this_round_combined_responses"][agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_avatars.get(agent_name, agent_name)):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state[f"{user_session_id}_messages"].append({"role": agent_name, "content": response})
            
            mark_agent_completed(round_num, agent_name)

            # **解析 Assistant 產出的可選 Idea**
            idea_options = re.findall(r"✅ Idea \d+: (.+)", response)
            st.session_state[f"{user_session_id}_idea_options"][f"round_{round_num}"] = idea_options

            for idea in idea_options:
                if idea not in st.session_state[f"{user_session_id}_idea_list"]:
                    st.session_state[f"{user_session_id}_idea_list"].append(idea)

            # st.write(f"登記 {agent_name} 完成")
        elif agent_name in ["Normal Assistant 1", "Normal Assistant 2"]:
            discussion_message_temp = discussion_message + (
                f"📢 **請根據你的角色定位來回答！** 🚀\n"
                f"🎭 你是 {agents[agent_name].system_message}。\n"
                f"👉 **請以這個視角提供你的創新見解，並確保你的回答符合你的專業！**\n\n"
            )

            # discussion_message_for_showing += (
            #     f"📢 **請根據你的角色定位來回答！** 🚀\n"
            #     f"🎭 你是 {agents[agent_name].system_message}。\n"
            #     f"👉 **請以這個視角提供你的創新見解，並確保你的回答符合你的專業！**\n\n"
            # )

            if not st.session_state[f"{user_session_id}_proxy_message_showed"]:
                with st.chat_message("assistant"):
                    st.markdown(discussion_message_for_showing)
                # # **顯示上一輪討論紀錄（可展開視窗）**
                # if round_num > 0:
                #     with st.expander(f"📜 查看第 {round_num - 1} 輪討論紀錄", expanded=False):
                #         markdown_content = "\n\n".join([f"### {key}\n{value}" for key, value in last_round_response.items()])
                #         st.markdown(markdown_content, unsafe_allow_html=True)

                st.session_state[f"{user_session_id}_proxy_message_showed"] = True

                st.session_state[f"{user_session_id}_messages"].append({"role": "assistant", "content": discussion_message_for_showing})

                
            if f"{user_session_id}_round_{round_num}_agent_states" in st.session_state and st.session_state[f"{user_session_id}_round_{round_num}_agent_states"][agent_name]:
                # st.write(f"{agent_name} 已完成")
                continue

            response = await agent.a_initiate_chat(user_proxy, message=discussion_message_temp, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state[f"{user_session_id}_this_round_combined_responses"][agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_avatars.get(agent_name, agent_name)):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state[f"{user_session_id}_messages"].append({"role": agent_name, "content": response})
            mark_agent_completed(round_num, agent_name)
            # st.write(f"登記 {agent_name} 完成")
 
    # return True

# 在輸入框消失後顯示提示，然後再顯示下一輪輸入框
if not st.session_state[f"{user_session_id}_show_input"]:
    st.write(f"已完成第 {st.session_state[f"{user_session_id}_round_num"] - 1} 輪的輸入！")
    st.session_state[f"{user_session_id}_show_input"] = True


if not st.session_state[f"{user_session_id}_discussion_started"]:
    if st.button("開始 LLM 討論"):
        st.session_state[f"{user_session_id}_discussion_started"] = True
        st.session_state[f"{user_session_id}_round_num"] = 0
        st.session_state[f"{user_session_id}_integrated_message"] = f"這是第 0 輪討論，{question}。"

if st.session_state[f"{user_session_id}_discussion_started"] and st.session_state[f"{user_session_id}_round_num"] <= rounds:
    
    round_num = st.session_state[f"{user_session_id}_round_num"]
    # 執行單輪討論
    completed = asyncio.run(single_round_discussion(
        st.session_state[f"{user_session_id}_round_num"], agents, user_proxy
    ))


    if not st.session_state[f"{user_session_id}_round_{round_num}_input_completed"]:

        # **透過 st.radio() 限制只能選擇一種輸入方式**
        input_method = st.radio("請選擇輸入方式：", ["輸入創意點子", "選擇創意思考技術"])

        if input_method == "輸入創意點子":
            current_input = st.text_area(f"請輸入第 {st.session_state[f"{user_session_id}_round_num"]} 輪的想法：")

        # **方式 2：使用 selectbox 選擇創意思考技術**
        elif input_method == "選擇創意思考技術":
            # 輸入選定的 Idea
            if st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", []):
                idea_options = st.session_state[f"{user_session_id}_idea_options"].get(f"round_{round_num}", [])
                st.write("### 🔍 AI 產生的創意點子，你可以選擇要延伸的 Idea")
                user_inputs = st.multiselect("請選擇你想延伸的 Idea：", idea_options)
            

            # **選擇創意思考技術**
            techniques = [
                "請選擇一種創意思考技術",  # 預設選項
                "SCAMPER - Substitute（替代）",
                "SCAMPER - Combine（結合）",
                "SCAMPER - Modify（修改）",
                "SCAMPER - Put to another use（變更用途）",
                "SCAMPER - Eliminate（刪除）",
                "SCAMPER - Reverse（反轉）",
                "六頂思考帽 - 白帽（事實）",
                "六頂思考帽 - 黑帽（風險）",
                "六頂思考帽 - 黃帽（優勢）",
                "六頂思考帽 - 綠帽（創意）",
                "TRIZ - 矛盾解決",
                "TRIZ - 功能分離",
                "TRIZ - 逆向思考",
                "TRIZ - 自適應性",
                "10x Thinking（Google 10 倍思維）",
                "First Principles Thinking（第一性原則）"
            ]

            selected_technique = st.selectbox("請選擇創意思考技術：", techniques, index=0)

        # **按鈕送出輸入**
        if st.button("送出選擇") and selected_technique != "請選擇一種創意思考技術" and user_inputs is not None:
            # 保存 Idea 和 Selected Idea
            st.session_state[f"{user_session_id}_user_inputs"][round_num] = st.session_state[f"{user_session_id}_user_inputs"][round_num] = ", ".join(user_inputs)
            st.session_state[f"{user_session_id}_selected_technique"][round_num] = selected_technique


            # 顯示選擇結果
            st.success(f"你選擇的 Idea：{user_inputs}")
            st.success(f"選擇的創意思考技術：{selected_technique}")

            # **重製輸入框**
            # st.session_state.selected_idea_input = ""  # 清空輸入的 Idea
            # st.session_state.selected_technique = techniques[0]  # 重置選擇框為預設

            # with st.chat_message("user"):
            #     st.markdown(f"**Selected Idea：** {selected_idea_input}" if selected_idea_input else "**未提供選定 Idea**")
            # with st.chat_message("user"):
            #     st.markdown(f"**選擇的技術：** {selected_technique}")

        completed = asyncio.run(single_round_discussion(
            st.session_state[f"{user_session_id}_round_num"], agents, user_proxy
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

# **顯示「選擇 Idea」按鈕**
with st.sidebar:
    if st.button("📌 選擇要加入收藏的 Idea"):
        st.session_state[f"{user_session_id}_show_idea_dialog"] = True

if st.session_state[f"{user_session_id}_show_idea_dialog"]:
    def show_idea_dialog():
        """彈出 Pop-up，讓用戶選擇 AI 產生的 Idea"""
                # **顯示轉圈圈 Loading 狀態**
        if st.session_state[f"{user_session_id}_is_loading"]:
            with st.spinner("處理中，請稍候..."):
                time.sleep(0.8)  # 模擬處理時間
            st.session_state[f"{user_session_id}_is_loading"] = False  # **關閉 Loading 狀態**
            # st.rerun()  # **刷新 Pop-up 內容**

        st.write("### 💡 你可以選擇以下 AI 產生的創意點子")

        if f"{user_session_id}_idea_list" not in st.session_state or not st.session_state[f"{user_session_id}_idea_list"]:
            st.warning("目前沒有可選的 Idea")
            return

        selected_ideas = []
        ideas_to_remove = []

        # **列出所有 AI 產生的 Idea，讓用戶選擇**
        for idea in st.session_state[f"{user_session_id}_idea_list"]:
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                if st.checkbox(f"{idea}", key=f"popup_{idea}"):
                    selected_ideas.append(idea)
            with col2:
                if st.button("🗑️", key=f"delete_{idea}"):
                    ideas_to_remove.append(idea)
                    st.session_state[f"{user_session_id}_is_loading"] = True


        # **移除不需要的 Idea**
        if ideas_to_remove:
            for idea in ideas_to_remove:
                st.session_state[f"{user_session_id}_idea_list"].remove(idea)
            st.warning(f"已移除 {len(ideas_to_remove)} 個 Idea")
            st.rerun()

        # **確認選擇後，加入收藏夾**
        if st.button("確認選擇"):
            st.session_state[f"{user_session_id}_selected_persistent_ideas"].extend(selected_ideas)
            st.success(f"已收藏的 Idea：{selected_ideas}")

            # **啟動 `st.spinner()`**
            st.session_state[f"{user_session_id}_is_loading"] = True
            st.session_state[f"{user_session_id}_show_idea_dialog"] = False  # **關閉 Pop-up**

            st.rerun()

    # **呼叫 `st.dialog()` 來開啟 Pop-up**
    @st.dialog("📌 選擇要加入收藏的 Idea", width="large")
    def idea_dialog():
        show_idea_dialog()

    idea_dialog()


# 清除紀錄
with st.sidebar:
    st.write("你的User Session ID：", user_session_id)
    if st.button("🗑️ 清除所有紀錄"):
        # 清空所有與當前 user_session_id 相關的 session_state 變數
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith(user_session_id)]
        for key in keys_to_delete:
            del st.session_state[key]
        
        # 清除 Streamlit 快取
        st.cache_data.clear()

        # 顯示成功訊息
        st.success("已清除所有紀錄！")

        # **強制重新執行整個程式，確保 UI 更新**
        st.rerun()
