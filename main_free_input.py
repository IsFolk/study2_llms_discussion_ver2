import streamlit as st
import asyncio
import re
from autogen import AssistantAgent, UserProxyAgent
from autogen import ConversableAgent
import pandas as pd
import plotly.express as px
import logging

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
        system_message="你是 Normal Assistant 1，你現在要跟其他agent一同進行腦力激盪，"
    ),
    "Normal Assistant 2": ConversableAgent(
        name=sanitize_name("Normal Assistant 2"),
        llm_config=llm_config,
        system_message="你是 Normal Assistant 2。，你現在要跟其他agent一同進行腦力激盪，"
    ),
     "Convergence Judge": ConversableAgent(
        name=sanitize_name("Convergence Judge"),
        llm_config=llm_config,
        system_message="你是腦力激盪評分員。",
    ),
    "Assistant": ConversableAgent(
        name=sanitize_name("Assistant"),
        llm_config=llm_config,
        system_message="你是 Assistant。",
    ),
    "User": UserProxyAgent(
        name=sanitize_name("User"),
        llm_config=llm_config,
        human_input_mode="NEVER",
    ),
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
if "integrated_message" not in st.session_state:
    st.session_state.integrated_message = ""
if "discussion_started" not in st.session_state:
    st.session_state.discussion_started = False
if "round_num" not in st.session_state:
    st.session_state.round_num = 0
# Initialize or retrieve user input storage
if "user_inputs" not in st.session_state:
    st.session_state.user_inputs = {}
if "current_input" not in st.session_state:
    st.session_state.current_input = ""
if "show_input" not in st.session_state:
    st.session_state.show_input = True
if "this_round_combined_responses" not in st.session_state:
    st.session_state.this_round_combined_responses = {}
if "proxy_message_showed" not in st.session_state:
    st.session_state.proxy_message_showed = False

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
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 更新某代理的回覆狀態
def mark_agent_completed(round_num, agent_name):
    st.session_state[f"round_{round_num}_agent_states"][agent_name] = True


async def single_round_discussion(round_num, agents, user_proxy):
    initialize_agent_states(round_num, agents)
    
    # 如果該輪已完成，直接返回 True
    if st.session_state.get(f"round_{round_num}_completed", False):
        return True

    if round_num == 0:
        discussion_message = (
            f"這是第0輪，{question}"
        )
    else:
        # 設定使用者 Ideation Technique 模板
        ideation_tech = "SCAMPER - Combine"

        user_input = "結合 AI 語音助手與時間管理工具"
        # 設定使用者 Ideation Technique 討論模板
        discussion_message = (
            f"🔄 **第 {round_num} 輪討論** 🔄\n\n"
            f"📌 **討論主題：** {question}\n\n"
            f"🎯 **使用者選擇的創意思考技術：{ideation_tech} **\n"
            f"💡 **使用者輸入：**「{st.session_state.user_inputs.get(round_num-1, "")}」\n\n"
            
            f"📝 **請針對上輪討論進行延伸，並基於 {ideation_tech} 提出更多創新發想！**\n"
            f"👉 你可以進一步**細化現有創意、增加應用場景，或挑戰現有假設**。\n\n"
            
            f"📑 **回應格式建議：**\n"
            f"1️⃣ **新觀點或改進**（如何進一步提升這個創意？）\n"
            f"2️⃣ **可能的應用場景**（這個想法可以應用在哪些新的領域？）\n"
            f"3️⃣ **可能的挑戰與解決方案**（有哪些技術、商業或使用者挑戰？如何克服？）\n\n"

            f"💡 **請根據你的創意思考技術進行回應！** 🚀"
        )


    
    this_round_input = st.session_state.user_inputs.get(round_num, "")


    for agent_name, agent in agents.items():
        if st.session_state[f"round_{round_num}_completed"]:
            break

        # st.write("開頭")
        # st.write(st.session_state.messages)
        if agent_name in ["Convergence Judge", "Assistant"]:
            continue


        # 最後一個 agent 後等待user_input後再進行下一輪
        if agent_name == "User":
            # 處理用戶輸入，只針對當前輪次
            if this_round_input != "":
                # Display user message in chat message container
                # st.chat_message("user").markdown(this_round_input)
                # Add user message to chat history
                st.session_state.messages.append({"role": "user", "content": this_round_input})
                st.session_state[f"round_{round_num}_input_completed"] = True
                st.session_state.this_round_combined_responses[agent_name] = this_round_input
                st.session_state.user_inputs[round_num] = this_round_input
                st.write(f"User 輸入完成：{this_round_input}")
                with st.chat_message("user"):
                    st.markdown(this_round_input)
                st.session_state.proxy_message_showed = False
            else:
                # 等待輸入
                return False
        else:
            if not st.session_state.proxy_message_showed:
                with st.chat_message("assistant"):
                    st.markdown(discussion_message)
                st.session_state.proxy_message_showed = True
                
            if st.session_state[f"round_{round_num}_agent_states"][agent_name]:
                continue
            st.write(f"{agent_name} 處理中...")

            st.session_state.messages.append({"role": "assistant", "content": discussion_message})
            response = await agent.a_initiate_chat(user_proxy, message=discussion_message, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state.this_round_combined_responses[agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_name):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": agent_name, "content": response})
            mark_agent_completed(round_num, agent_name)


    
    return True

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
        
        current_input = st.chat_input(f"請輸入第 {st.session_state.round_num} 輪的想法：")
        
        if current_input:
            # 保存输入并重置状态
            st.session_state.user_inputs[st.session_state.round_num] = current_input
            with st.chat_message("user"):
                st.markdown(current_input)

        completed = asyncio.run(single_round_discussion(
            st.session_state.round_num, agents, user_proxy
        ))

    if completed:
        # 如果該輪完成，進入下一輪
        # st.write(f"已完成第 {st.session_state.round_num} 輪，進入第 {st.session_state.round_num + 1} 輪")
        st.session_state.round_num += 1
        # time.sleep(1)
        st.rerun()
