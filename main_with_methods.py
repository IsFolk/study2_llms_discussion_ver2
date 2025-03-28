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
import os

# load_dotenv()  # 讀取 .env 文件
# api_key = os.getenv("OPENAI_API_KEY")
api_key = st.secrets["api_keys"]["OPENAI_API_KEY"]

question = "風箏除了娛樂，還能用什麼其他創意用途？"

# 設定 Streamlit 頁面
st.set_page_config(page_title="LLM & Human Discussion Framework", page_icon="🧑", layout="wide")
st.title("LLM + Human Discussion Framework (LLM First)")

# 側邊欄：配置本地 API
with st.sidebar:
    st.header("模型與 API 設定")
    selected_model = st.selectbox("選擇模型", ["llama3-taiwan", "llama-3-taiwan-13.3b-instruct-i1", "gpt-4o-mini", "llama-3.2-1b-instruct", "gpt-4o"], index=0)
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
            "api_key": None,
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
    ),
    "Normal Assistant 2": ConversableAgent(
        name=sanitize_name("Normal Assistant 2"),
        llm_config=llm_config,
        system_message="你是一位科技公司的產品經理，擁有深厚的技術背景。你的任務是評估創新技術的可行性，並確保產品設計符合市場需求。你的回答應該兼顧技術可行性與用戶體驗，並提供具體的產品開發方向。",
    ),
     "Convergence Judge": ConversableAgent(
        name=sanitize_name("Convergence Judge"),
        llm_config=llm_config,
        system_message="你是腦力激盪評分員。",
    ),
    "Assistant": ConversableAgent(
        name=sanitize_name("Assistant"),
        llm_config=llm_config,
        system_message="你是 Assistant，負責將點子按照 主題、應用場景、技術方向 等分類，轉化為條列式清單。",
    ),
    "User": UserProxyAgent(
        name=sanitize_name("User"),
        llm_config=llm_config,
        human_input_mode="NEVER",
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
if "messages" not in st.session_state:
    st.session_state.messages = []
if "discussion_started" not in st.session_state:
    st.session_state.discussion_started = False
if "round_num" not in st.session_state:
    st.session_state.round_num = 0
# Initialize or retrieve user input storage
if "user_inputs" not in st.session_state:
    st.session_state.user_inputs = {}
# if "current_input" not in st.session_state:
#     st.session_state.current_input = ""
if "show_input" not in st.session_state:
    st.session_state.show_input = True
if "this_round_combined_responses" not in st.session_state:
    st.session_state.this_round_combined_responses = {}
if "proxy_message_showed" not in st.session_state:
    st.session_state.proxy_message_showed = False
if "selected_technique" not in st.session_state:
    st.session_state.selected_technique = {}


# 初始化每輪的完成狀態
rounds = 99  # 假設總輪數是 99，可以根據需求調整
for i in range(rounds + 1):  # 包括第 0 輪
    if f"round_{i}_completed" not in st.session_state:
        st.session_state[f"round_{i}_completed"] = False

# 初始化每輪的完成狀態
rounds = 99  # 假設總輪數是 99，可以根據需求調整
for i in range(rounds + 1):  # 包括第 0 輪
    if f"round_{i}_input_completed" not in st.session_state:
        st.session_state[f"round_{i}_input_completed"] = False


# 初始化代理的回覆狀態
def initialize_agent_states(round_num, agents):
    if f"round_{round_num}_agent_states" not in st.session_state:
        st.session_state[f"round_{round_num}_agent_states"] = {
            agent_name: False for agent_name in agents.keys()
        }

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(agent_avatars.get(message["role"], message["role"])):
        st.markdown(message["content"])

# 更新某代理的回覆狀態
def mark_agent_completed(round_num, agent_name):
    st.session_state[f"round_{round_num}_agent_states"][agent_name] = True


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
        for agent_name, response in st.session_state.this_round_combined_responses.items():
            if agent_name in ["User"]:
                continue
            last_round_response[agent_name] = response

        # 設定使用者 Ideation Technique 討論模板
        discussion_message = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            # f"📌 **討論主題：** {question}\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state.user_inputs.get(round_num-1, "")}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{st.session_state.selected_technique.get(round_num-1, "")}」\n\n"
            
            f" 上一輪討論紀錄: {last_round_response}\n"
            f"📝 **請針對上輪討論進行延伸，並基於創意思考技術做延伸！**\n\n "
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )

        discussion_message_for_showing = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            # f"📌 **討論主題：** {question}\n\n"
            f"💡 **使用者選擇的創意：**「{st.session_state.user_inputs.get(round_num-1, "")}」\n\n"
            f"💡 **使用者選擇的創意思考技術：**「{st.session_state.selected_technique.get(round_num-1, "")}」\n\n"
            f"📝 **請針對上輪討論進行延伸，並基於創意思考技術做延伸！**\n\n "
            # f"請用簡潔的方式回應這個問題（或話題）：[你的問題或話題]，語氣像是專業人士在討論，且回答不超過兩句話，重要的地方用粗體呈現。"
        )



    
    this_round_method = st.session_state.selected_technique.get(round_num, "")
    this_round_idea = st.session_state.user_inputs.get(round_num, "")



    for agent_name, agent in agents.items():
        if agent_name in ["Convergence Judge"]:
            continue

        # 最後一個 agent 後等待user_input後再進行下一輪
        if agent_name == "User":            
            # 處理用戶輸入，只針對當前輪次
            if this_round_method != "" and this_round_idea != "":
                # Add user message to chat history
                st.session_state.messages.append({"role": "user", "content": this_round_method})
                st.session_state[f"round_{round_num}_input_completed"] = True
                st.session_state.this_round_combined_responses[agent_name] = this_round_method
                st.session_state.selected_technique[round_num] = this_round_method

                st.session_state.user_inputs[round_num] = this_round_idea
                # st.write(f"User 輸入完成：{this_round_input}")

                # Display user message in chat message container
                with st.chat_message("user"):
                    st.markdown(this_round_method)
                st.session_state.proxy_message_showed = False
                return True

            else:
                # 等待輸入
                return False
        elif agent_name == "Assistant":
            # pass
            if st.session_state[f"round_{round_num}_agent_states"][agent_name]:
                # st.write(f"{agent_name} 已完成")
                continue

            this_round_response = {}
            for agent_name_each, response in st.session_state.this_round_combined_responses.items():
                if agent_name_each in ["User", "Assistant"]:
                    continue
                this_round_response[agent_name_each] = response
            category_prompt = (
                f"你是一個擅長資訊統整的 AI，負責整理來自不同 AI 助手的回應，並確保分類清晰、有條理。"
                f"\n\n💡 **這些 AI 來自不同領域，包括：**"
                f"\n🔹 Normal Assistant 1（{agents['Normal Assistant 1'].system_message}）"
                f"\n🔹 Normal Assistant 2（{agents['Normal Assistant 2'].system_message}）"
                # f"\n🔹 Convergence Judge（{agents['Convergence Judge'].system_message}）"
                f"\n\n📌 **這一輪的討論紀錄：**"
                f"\n{this_round_response}"
                f"\n\n**請按照以下要求統整資訊：**"
                f"\n1️⃣ **標記 AI 來源**：請在每個觀點前標示該 AI 的名稱，例如【Normal Assistant 1】、【Normal Assistant 2】"
                f"\n2️⃣ **主動判斷分類**：根據內容自動選擇最合適的分類，例如「技術創新」、「市場趨勢」、「挑戰與風險」、「未來應用」等"
                f"\n3️⃣ **避免重複**：若多個 AI 提出相似觀點，請合併處理，並標示不同 AI 的補充意見"
                f"\n4️⃣ **總結主要發現**：在最後提供 2-3 句話的摘要，歸納討論的核心重點"
                f"\n\n📌 **格式範例：**"
                f"\n【技術創新】"
                f"\n- 【Normal Assistant 1】提出『風力發電風箏』，強調其能源轉換效率"
                f"\n- 【Normal Assistant 2】補充該技術可搭配 AI 自適應飛行，提高穩定性"
                f"\n- 【Convergence Judge】提醒該技術仍需進一步測試穩定性"
                f"\n\n【市場趨勢】"
                f"\n- 【Normal Assistant 1】認為 NFT 風箏具市場潛力，因為收藏品市場正在成長"
                f"\n- 【Convergence Judge】質疑其長期價值，認為 NFT 市場的不確定性較高"
                f"\n\n📌 **總結**"
                f"\n本輪討論顯示，風力發電風箏在技術上有潛力，但仍需解決穩定性問題。NFT 風箏在市場潛力上存在爭議，值得進一步探討。"
                f"\n\n👉 **請告訴我你想進一步探討哪個部分？我可以提供更多細節！**"
            )

            response = await agent.a_initiate_chat(user_proxy, message=category_prompt, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state.this_round_combined_responses[agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_avatars.get(agent_name, agent_name)):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": agent_name, "content": response})
            
            mark_agent_completed(round_num, agent_name)
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

            if not st.session_state.proxy_message_showed:
                with st.chat_message("assistant"):
                    st.markdown(discussion_message_for_showing)
                # # **顯示上一輪討論紀錄（可展開視窗）**
                # if round_num > 0:
                #     with st.expander(f"📜 查看第 {round_num - 1} 輪討論紀錄", expanded=False):
                #         markdown_content = "\n\n".join([f"### {key}\n{value}" for key, value in last_round_response.items()])
                #         st.markdown(markdown_content, unsafe_allow_html=True)

                st.session_state.proxy_message_showed = True

                st.session_state.messages.append({"role": "assistant", "content": discussion_message})

                
            if st.session_state[f"round_{round_num}_agent_states"][agent_name]:
                # st.write(f"{agent_name} 已完成")
                continue

            response = await agent.a_initiate_chat(user_proxy, message=discussion_message_temp, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state.this_round_combined_responses[agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_avatars.get(agent_name, agent_name)):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": agent_name, "content": response})
            mark_agent_completed(round_num, agent_name)
            # st.write(f"登記 {agent_name} 完成")
 
    # return True

# 初始化 refresh_flag
if "refresh_flag" not in st.session_state:
    st.session_state.refresh_flag = False


# 在輸入框消失後顯示提示，然後再顯示下一輪輸入框
if not st.session_state.show_input:
    st.write(f"已完成第 {st.session_state.round_num - 1} 輪的輸入！")
    st.session_state.show_input = True


if not st.session_state.discussion_started:
    if st.button("開始 LLM 討論"):
        st.session_state.discussion_started = True
        st.session_state.round_num = 0
        st.session_state.integrated_message = f"這是第 0 輪討論，{question}。"

if st.session_state.discussion_started and st.session_state.round_num <= rounds:
    
    round_num = st.session_state.round_num
    # 執行單輪討論
    completed = asyncio.run(single_round_discussion(
        st.session_state.round_num, agents, user_proxy
    ))


    if not st.session_state[f"round_{round_num}_input_completed"]:

        # **輸入原始 Idea**
        # idea_input = st.text_area("請輸入您的 Idea：", key="idea_input")

        # **輸入選定的 Idea**
        user_inputs = st.text_area("請輸入選定的 Idea（可選）：", 
                                   value="")

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
        if st.button("送出選擇") and selected_technique != "請選擇一種創意思考技術" and user_inputs.strip():
            # 保存 Idea 和 Selected Idea
            st.session_state.user_inputs[round_num] = user_inputs
            st.session_state.selected_technique[round_num] = selected_technique


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
            st.session_state.round_num, agents, user_proxy
        ))

    if completed:
        # 如果該輪完成，進入下一輪
        # st.write(f"已完成第 {st.session_state.round_num} 輪，進入第 {st.session_state.round_num + 1} 輪")
        st.session_state.round_num += 1
        # time.sleep(1)
        st.rerun()
