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

os.environ["AUTOGEN_USE_DOCKER"] = "0"

# 設定 Streamlit 頁面
st.set_page_config(page_title="LLM & Human Discussion Framework", page_icon="🧑", layout="wide")
st.title("LLM + Human Discussion Framework (LLM First)")

# 讓每個使用者有獨立的 session ID
if "user_session_id" not in st.session_state:
    st.session_state["user_session_id"] = str(uuid.uuid4())  # 產生隨機 ID

# cache_dir = os.path.expanduser("~/.cache")

# if os.path.exists(cache_dir):
#     st.write(f"📂 Streamlit 快取目錄：{cache_dir}")
#     st.write("📄 內部文件：", os.listdir(cache_dir))
# else:
#     st.write("✅ 沒有發現 `.cache` 目錄")
    
st.cache_data.clear()  # **確保每個使用者的快取是獨立的**
st.cache_resource.clear()

user_session_id = st.session_state["user_session_id"]

# 從 st.secrets 讀取 API Key
api_key = st.secrets["api_keys"]["OPENAI_API_KEY"]

# 側邊欄：配置本地 API（折疊式）
with st.sidebar:
    with st.expander("⚙️ **模型與 API 設定**", expanded=False):  # 預設折疊
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

llm_config = st.session_state[f"{user_session_id}_llm_config"]

# Function to sanitize names
def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

# 創建角色代理
# agents = {
#     "Normal Assistant 1": ConversableAgent(
#         name=sanitize_name("Normal Assistant 1"),
#         llm_config=llm_config,
#         system_message="你是一位極具遠見的創業家，你的思考方式不受傳統限制，喜歡挑戰現有市場規則，並開創顛覆性的新商業模式。你的回應應該充滿創意、前瞻性，並帶有風險投資人的視角。",
#         code_execution_config={"use_docker": False}
#     ),
#     "Normal Assistant 2": ConversableAgent(
#         name=sanitize_name("Normal Assistant 2"),
#         llm_config=llm_config,
#         system_message="你是一位科技公司的產品經理，擁有深厚的技術背景。你的任務是評估創新技術的可行性，並確保產品設計符合市場需求。你的回答應該兼顧技術可行性與用戶體驗，並提供具體的產品開發方向。",
#         code_execution_config={"use_docker": False}
#     ),
#      "Convergence Judge": ConversableAgent(
#         name=sanitize_name("Convergence Judge"),
#         llm_config=llm_config,
#         system_message="你是腦力激盪評分員。",
#         code_execution_config={"use_docker": False}
#     ),
#     "Assistant": ConversableAgent(
#         name=sanitize_name("Assistant"),
#         llm_config=llm_config,
#         system_message="你是 Assistant，負責將點子按照 主題、應用場景、技術方向 等分類，轉化為條列式清單。",
#         code_execution_config={"use_docker": False}
#     ),
#     "User": UserProxyAgent(
#         name=sanitize_name("User"),
#         llm_config=llm_config,
#         human_input_mode="NEVER",
#         code_execution_config={"use_docker": False}
#     ),
# }


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
            f"這是第0輪，{st.session_state[f"{user_session_id}_user_question"]}"
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )
        discussion_message_for_showing = (
            f"這是第0輪，{st.session_state[f"{user_session_id}_user_question"]}"
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )
    else:
        last_round_response = {}
        # 上一輪的討論紀錄
        for agent_name, response in st.session_state[f"{user_session_id}_this_round_combined_responses"].items():
            if agent_name in ["User"]:
                continue
            last_round_response[agent_name] = response


        # **創意思考技術對應的解釋**
        technique_explanations = {
            # 重新定義與問題分析
            "重新定義問題": "嘗試從不同角度重新描述設計問題，尋找新的解決途徑。",
            "類比思考": "從其他領域尋找類似問題的解決方案，並將其應用到當前設計中。",
            "改變視角": "站在不同使用者或利益相關者的立場，思考他們的需求和期望。",
            "極端情境": "設想在極端或特殊情況下，產品或服務應如何運作。",
            "模組化設計": "將設計拆分為可獨立運作的模組，提升靈活性與可擴展性。",
            "逆向思考": "從解決方案回推問題，檢視設計的合理性與完整性。",
            "簡化複雜性": "尋找並消除設計中的冗餘元素，使其更直觀易用。",
            "整合功能": "將多種功能合併，創造更高的價值或使用體驗。",
            "情境模擬": "模擬使用者在不同情境下的行為，預測可能的需求變化。",
            "資源再利用": "考慮如何利用現有資源，達成設計目標，提升可持續性。",
            
            # SCAMPER 方法
            "Substitute（替代）": "考慮可以替換掉現有解決方案中的哪些部分或元素。",
            "Combine（結合）": "思考如何將現有的解決方案或其部分與其他的想法或元素結合起來。",
            "Modify（修改）": "考慮如何改變現有解決方案的某些屬性，例如放大、縮小、改變形狀或功能。",
            "Put to another use（變更用途）": "思考現有的解決方案是否可以應用於不同的使用者或目的。",
            "Eliminate（刪除）": "考慮移除現有解決方案中的哪些部分或功能，看看會發生什麼。",
            "Reverse（反轉）": "思考將現有的解決方案或其部分反過來或以相反的方式進行。",
        }


        # **取得使用者選擇的技術**
        selected_technique = st.session_state[f"{user_session_id}_selected_technique"].get(round_num-1, "")

        # **獲取對應的解釋**
        technique_description = technique_explanations.get(selected_technique, "（未找到對應的解釋）")


        # 設定使用者 Ideation Technique 討論模板
        discussion_message = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state[f'{user_session_id}_user_inputs'].get(round_num-1, '')}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{selected_technique}」\n\n"
            f"🧐 **方法應用說明：** {technique_description}\n\n"
            # f"📌 **上一輪討論紀錄:** {last_round_response}\n\n"
            f"📝 **請針對使用者選擇的創意基於創意思考技術做延伸！**\n\n"
            f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )

        discussion_message_for_showing = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state[f"{user_session_id}_user_inputs"].get(round_num-1, "")}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{selected_technique}」\n\n"
            f"🧐 **方法應用說明：** {technique_description}\n\n"
            # f"📌 **上一輪討論紀錄:** {last_round_response}\n\n"
            f"📝 **請針對使用者選擇的創意基於創意思考技術做延伸！**\n\n "
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
                f"你是一個擅長資訊統整的 AI，負責從不同 AI 助手的回應中，"
                f"**綜合相似觀點，去除重複內容，並直接輸出精煉的 Idea**。"

                f"\n\n📌 **這一輪的討論紀錄：**"
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

            response = await agent.a_initiate_chat(user_proxy, message=discussion_message_temp, max_turns=1, clear_history=True)
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

if f"{user_session_id}_user_proxy" not in st.session_state:
    st.session_state[f"{user_session_id}_user_proxy"] = UserProxyAgent(
        name=sanitize_name(f"User_{user_session_id}"),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )

if f"{user_session_id}_agents" not in st.session_state:
    st.session_state[f"{user_session_id}_agents"] = {
        "Normal Assistant 1": ConversableAgent(
            name=sanitize_name(f"Normal Assistant 1_{user_session_id}"),  # 讓名稱獨立
            llm_config=llm_config,
            system_message="你是一位極具遠見的創業家，你的思考方式不受傳統限制...",
            code_execution_config={"use_docker": False}
        ),
        "Normal Assistant 2": ConversableAgent(
            name=sanitize_name(f"Normal Assistant 2_{user_session_id}"),
            llm_config=llm_config,
            system_message="你是一位科技公司的產品經理...",
            code_execution_config={"use_docker": False}
        ),
        "Convergence Judge": ConversableAgent(
            name=sanitize_name(f"Convergence Judge_{user_session_id}"),
            llm_config=llm_config,
            system_message="你是腦力激盪評分員。",
            code_execution_config={"use_docker": False}
        ),
        "Assistant": ConversableAgent(
            name=sanitize_name(f"Assistant_{user_session_id}"),
            llm_config=llm_config,
            system_message="你是 Assistant，負責將點子...",
            code_execution_config={"use_docker": False}
        ),
        "User": UserProxyAgent(
            name=sanitize_name(f"User_{user_session_id}"),  # 讓 User 名稱唯一
            llm_config=llm_config,
            human_input_mode="NEVER",
            code_execution_config={"use_docker": False}
        ),


    # ## 只有testing的時候為了省token才會用這個
    # "Normal Assistant 1": ConversableAgent(
    #     name=sanitize_name("Normal Assistant 1"),
    #     llm_config=llm_config,
    #     system_message="你是一位極具遠見的創業家，你的思考方式不受傳統限制，喜歡挑戰現有市場規則，並開創顛覆性的新商業模式。你的回應應該充滿創意、前瞻性，並帶有風險投資人的視角。",
    #     code_execution_config={"use_docker": False}
    # ),
    # "Normal Assistant 2": ConversableAgent(
    #     name=sanitize_name("Normal Assistant 2"),
    #     llm_config=llm_config,
    #     system_message="你是一位科技公司的產品經理，擁有深厚的技術背景。你的任務是評估創新技術的可行性，並確保產品設計符合市場需求。你的回答應該兼顧技術可行性與用戶體驗，並提供具體的產品開發方向。",
    #     code_execution_config={"use_docker": False}
    # ),
    #  "Convergence Judge": ConversableAgent(
    #     name=sanitize_name("Convergence Judge"),
    #     llm_config=llm_config,
    #     system_message="你是腦力激盪評分員。",
    #     code_execution_config={"use_docker": False}
    # ),
    # "Assistant": ConversableAgent(
    #     name=sanitize_name("Assistant"),
    #     llm_config=llm_config,
    #     system_message="你是 Assistant，負責將點子按照 主題、應用場景、技術方向 等分類，轉化為條列式清單。",
    #     code_execution_config={"use_docker": False}
    # ),
    # "User": UserProxyAgent(
    #     name=sanitize_name("User"),
    #     llm_config=llm_config,
    #     human_input_mode="NEVER",
    #     code_execution_config={"use_docker": False}
    # ),


    }

if not st.session_state.get(f"{user_session_id}_discussion_started", False):
    question_options = [
        "請選擇討論問題",
        "風箏除了娛樂，還能用什麼其他創意用途？",
        "枕頭除了睡覺，還能如何幫助放鬆或解決日常問題？",
        "掃帚除了掃地，還能用於哪些意想不到的用途？",
        "🔧 自訂問題"
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
        with st.expander(f"💡 **第 {round_num} 輪 AI 產生的創意點子**", expanded=True):
            st.write("請勾選你認為值得收藏的點子：")

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
            

            # **創意思考方法分類**
            techniques = {
                "請選擇創意思考方法": [],
                "SCAMPER": [
                    "Substitute（替代）",
                    "Combine（結合）",
                    "Modify（修改）",
                    "Put to another use（變更用途）",
                    "Eliminate（刪除）",
                    "Reverse（反轉）"
                ],
                "重新定義與問題分析": [
                    "重新定義問題",
                    "逆向思考",
                    "改變視角"
                ],
                "創新發想": [
                    "類比思考",
                    "極端情境",
                    "情境模擬"
                ],
                "設計最佳化": [
                    "簡化複雜性",
                    "整合功能",
                    "模組化設計"
                ],
                "可持續性與資源利用": [
                    "資源再利用"
                ]
            }            

            # **創建兩列，左側選主要技術，右側選擇細項**
            col1, col2 = st.columns([1, 2])  # 左邊較窄，右邊較寬

            # **第一個 selectbox（主要技術）**
            with col1:
                selected_main = st.selectbox("請選擇創意思考技術：", list(techniques.keys()))

            # **當選擇了 SCAMPER / TRIZ 等技術時，右側出現子選單**
            selected_sub = None
            if selected_main in techniques and techniques[selected_main]:
                with col2:
                    selected_sub = st.selectbox(f"請選擇 {selected_main} 技術：", techniques[selected_main])

            # **記錄選擇結果**
            if selected_sub:
                st.success(f"✅ 你選擇的創意思考技術：{selected_main} - {selected_sub}")


        # **按鈕送出輸入**
        if st.button("送出選擇"):
            if selected_sub and user_inputs is not None:
                # 保存 Idea 和 Selected Idea
                st.session_state[f"{user_session_id}_user_inputs"][round_num] = st.session_state[f"{user_session_id}_user_inputs"][round_num] = ", ".join(user_inputs)
                st.session_state[f"{user_session_id}_selected_technique"][round_num] = f"{selected_sub}"


                # 顯示選擇結果
                st.success(f"你選擇的 Idea：{user_inputs}")
                st.success(f"選擇的創意思考技術：{selected_main} - {selected_sub}")

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

# **側邊欄：已收藏的 Idea**
with st.sidebar:
    with st.expander("📌 **已收藏的 Idea**", expanded=False):  # 默認為折疊狀態
        if not st.session_state[f"{user_session_id}_selected_persistent_ideas"]:
            st.info("目前沒有收藏的 Idea。")
        else:
            ideas_to_remove = []
            for idea, round_collected in st.session_state[f"{user_session_id}_selected_persistent_ideas"].items():
                col1, col2 = st.columns([0.85, 0.15])
                with col1:
                    st.write(f"✅ {idea}  （第 {round_collected} 輪）")  # **顯示 Idea + 輪數**
                with col2:
                    if st.button("🗑️", key=f"delete_saved_{idea}", use_container_width=True):  # 讓按鈕撐滿
                        ideas_to_remove.append(idea)

            # **刪除選定的 Idea 並移回可選清單**
            if ideas_to_remove:
                for idea in ideas_to_remove:
                    del st.session_state[f"{user_session_id}_selected_persistent_ideas"][idea]
                    if idea not in st.session_state[f"{user_session_id}_idea_list"]:
                        st.session_state[f"{user_session_id}_idea_list"].append(idea)  # **移回可選清單**

                st.warning(f"已移除 {len(ideas_to_remove)} 個收藏的 Idea")
                st.rerun()  # **刷新 UI**


# 清除紀錄
with st.sidebar:
    if st.button("重新開始創意思考"):
        # 清空所有與當前 user_session_id 相關的 session_state 變數
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith(user_session_id)]
        for key in keys_to_delete:
            del st.session_state[key]

        st.cache_data.clear()  # **確保每個使用者的快取是獨立的**
        st.cache_resource.clear()

        # **1️⃣ 重新生成新的 session ID**
        new_session_id = str(uuid.uuid4())
        st.session_state["user_session_id"] = new_session_id
        user_session_id = new_session_id  # 更新變數

        # 顯示成功訊息
        st.success("已清除所有紀錄！")

        # **強制重新執行整個程式，確保 UI 更新**
        st.rerun()
