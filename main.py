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
st.title("LLM + Human Discussion Framework (Human First)")

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
        "在討論時考慮以下指標，為創意評估標準，越高越好：\n"
        "- **Originality**: 要想出新奇、有創意的回答，既不是老套也不是奇怪，而是跟問題相關的。\n"
        "- **Elaboration**: 回答的時候提供的細節越多越好。\n"
        "- **Fluency**: 回答中能給出相關於題目的內容越多越好。\n"
        "- **Flexibility**: 回答中包含的種類或方向越多越好。\n\n。",
    ),
    "Normal Assistant 2": ConversableAgent(
        name=sanitize_name("Normal Assistant 2"),
        llm_config=llm_config,
        system_message="你是 Normal Assistant 2。，你現在要跟其他agent一同進行腦力激盪，"
        "在討論時考慮以下指標，為創意評估標準，越高越好：\n"
        "- **Originality**: 要想出新奇、有創意的回答，既不是老套也不是奇怪，而是跟問題相關的。\n"
        "- **Elaboration**: 回答的時候提供的細節越多越好。\n"
        "- **Fluency**: 回答中能給出相關於題目的內容越多越好。\n"
        "- **Flexibility**: 回答中包含的種類或方向越多越好。\n\n。",
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
if "passed_ideas" not in st.session_state:
    st.session_state.passed_ideas = []
if "full_scores" not in st.session_state:
    st.session_state.full_scores = []


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
async def check_novelty_and_feasibility(round_num, integrated_history_with_categories, current_round_responses, if_zero_round=False):

    current_round_message = (
        "以下是本輪對話，請幫我總結創意部分，忽略問候語與無關內容，請忽略所有 Markdown 格式化符號（如 `#`, `*`, `**` 等），僅提取討論中的有用內容。"
        f"{current_round_responses}"
        "請輸出簡潔版，僅保留創意。"
    )

    print("XXXXXXXXXXXXXXXXXXXXXX")
    print(current_round_message)
    print("XXXXXXXXXXXXXXXXXXXXXX")

    current_round_responses = await agents["Assistant"].a_initiate_chat(user_proxy, message=current_round_message, max_turns=1)
    current_round_responses = current_round_responses.chat_history[-1]["content"].strip()

    print("OOOOOOOOOOOOOOOO")
    print(current_round_responses)
    print("OOOOOOOOOOOOOOOO")

    if if_zero_round:
        integrated_history_message = ""
    else:
        integrated_history_message = (
            "以下是整合歷史討論內容，請幫我總結創意部分，忽略問候語與無關內容，請忽略所有 Markdown 格式化符號（如 `#`, `*`, `**` 等），僅提取討論中的有用內容。"
            f"{integrated_history_with_categories}"
            "請輸出簡潔版，僅保留創意。"
        )
        integrated_history_message = await agents["Assistant"].a_initiate_chat(user_proxy, message=integrated_history_message, max_turns=1)
        integrated_history_message = integrated_history_message.chat_history[-1]["content"].strip()

    st.markdown("---")
    categorize_message = (
        "請將討論內容進行整合分類，並評估創意的質量："
        "## 指標定義：\n"
        "- **Originality**: 要想出新奇、有創意的回答，既不是老套也不是奇怪，而是跟問題相關的。\n"
        "- **Elaboration**: 回答的時候提供的細節越多越好。\n"
        "- **Fluency**: 回答中能給出相關於題目的內容越多越好。\n"
        "- **Flexibility**: 回答中包含的種類或方向越多越好。\n\n"
        "## 問題：\n"
        f"{question}\n\n"

        "目標："
        "1. 對本輪回應中的每個創意，根據四個指標進行逐項評估並給出分數（0-100）。\n"
        "2. 提供本輪回應的平均分數（精確到小數點）。\n"
        "3. 請基於歷史回應分類，將新一輪的創意按照功能進行分類。\n"
        "4. 上一輪的分類不做更動，直接使用完整的歷史記錄。\n"
        "5. 新一輪的創意直接按功能分類，保持原始描述，不對內容進行簡化或整理。\n"
        "6. 如有必要，可新增分類，並說明新增分類的原因。\n"

        f"## 第{round_num-1}輪歷史分類：\n"
        f"{integrated_history_message}\n\n"
        f"## 第{round_num}輪回應：\n"
        f"{current_round_responses}\n\n"


        f"\n\n回應格式：(請嚴格遵守回傳方式)\n"
        f"\n## 第{round_num}輪回應創意評分：(請嚴格遵守回傳方式)\n"
        "- {創意 1項目}_{創意 1的具體執行方式}(例子: 叉子_使用叉子拿來做餐具): Originality {分數}/100, Elaboration {分數}/100, Fluency {分數}/100, Flexibility {分數}/100\n"
        "- {創意 2項目}_{創意 2的具體執行功能}(例子: 叉子_使用叉子拿來做餐具): Originality {分數}/100, Elaboration {分數}/100, Fluency {分數}/100, Flexibility {分數}/100\n"
        f"\n## 第{round_num}輪回應平均分數：\n"
        "Originality：{本輪回應Originality平均分數(小數點)}\n"
        "Elaboration：{本輪回應Elaboration平均分數(小數點)}\n"
        "Fluency：{本輪回應Fluency平均分數(小數點)}\n"
        "Flexibility：{本輪回應Flexibility平均分數(小數點)}\n"
        f"\n## 第{round_num-1}輪的回應：\n"
        f"{integrated_history_message}\n"
        f"\n## 第{round_num-1}輪歷史回應的分類：\n"
        f"- 分類 1: \n"
        f"  - 原始創意: [創意內容 1 (來自第 X 輪), 創意內容 2 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 1 (來自第 X 輪), 新增創意內容 2 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"- 分類 2: \n"
        f"  - 原始創意: [創意內容 3 (來自第 X 輪), 創意內容 4 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 3 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"- 分類 3: \n"
        f"  - 原始創意: [創意內容 5 (來自第 X 輪), 創意內容 6 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 4 (來自第 X 輪), 新增創意內容 5 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"\n## 第{round_num}輪的回應：\n"
        f"{current_round_responses}\n"
        f"\n## 第{round_num}輪整合後的分類說明：\n"
        f"- 分類 1: \n"
        f"  - 原始創意: [創意內容 1 (來自第 X 輪), 創意內容 2 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 1 (來自第 X 輪), 新增創意內容 2 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"- 分類 2: \n"
        f"  - 原始創意: [創意內容 3 (來自第 X 輪), 創意內容 4 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 3 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"- 分類 3: \n"
        f"  - 原始創意: [創意內容 5 (來自第 X 輪), 創意內容 6 (來自第 X 輪)]（原因：請具體描述原因）\n"
        f"  - 新增創意: [新增創意內容 4 (來自第 X 輪), 新增創意內容 5 (來自第 X 輪)]（原因：請具體描述原因）\n"
    )
    # st.write(categorize_message)
    st.markdown("---")



    # 代理進行分類
    response = await agents["Convergence Judge"].a_initiate_chat(user_proxy, message=categorize_message, max_turns=1)

    # 從 chat_history 提取最後一條訊息（代理的回應）
    final_message = response.chat_history[-1]["content"].strip()

    st.write("### 出來的新指標")
    st.write(final_message)

    st.markdown("---")
    # 正則匹配所有回應平均分數段落
    pattern = r"## 第(\d+)輪回應平均分數：\s*([\s\S]*?)(?=##|$)"

    # 获取所有匹配
    matches = re.finditer(pattern, final_message, re.DOTALL)
    matches_list = list(matches)

    # 获取第一个匹配段落
    if matches_list:
        matches_text = matches_list[0].group(2)  # 获取第一个匹配的内容部分
    else:
        raise ValueError("未找到任何匹配段落")


 # 正則表達式提取指標分數
    match = re.search(
        r"Originality[:：]\s*([\d.]+)|"
        r"Elaboration[:：]\s*([\d.]+)|"
        r"Fluency[:：]\s*([\d.]+)|"
        r"Flexibility[:：]\s*([\d.]+)",
        matches_text,
        re.MULTILINE
    )

    # 如果匹配到了指標分數，逐一提取
    if match:
        originality_match = re.search(r"Originality[:：]\s*([\d.]+)", matches_text)
        if originality_match:
            originality_score = float(originality_match.group(1))

        elaboration_match = re.search(r"Elaboration[:：]\s*([\d.]+)", matches_text)
        if elaboration_match:
            elaboration_score = float(elaboration_match.group(1))

        fluency_match = re.search(r"Fluency[:：]\s*([\d.]+)", matches_text)
        if fluency_match:
            fluency_score = float(fluency_match.group(1))

        flexibility_match = re.search(r"Flexibility[:：]\s*([\d.]+)", matches_text)
        if flexibility_match:
            flexibility_score = float(flexibility_match.group(1))


    # 匹配每個創意的創意分數
    # 正則表達式：匹配每一行創意及其四個指標
    pattern = r"-\s*(.*?)\s*(?:\n)?(?:-)?\s*Originality\s*[：:]?\s*(\d+)(?:/100)?,?\s*Elaboration\s*[：:]?\s*(\d+)(?:/100)?,?\s*Fluency\s*[：:]?\s*(\d+)(?:/100)?,?\s*Flexibility\s*[：:]?\s*(\d+)(?:/100)?"




    # 指定篩選條件
    originality_threshold = 80
    flexibility_threshold = 80

    # 初始化一個列表來存儲符合條件的創意
    ideas = []

    # 使用 re.finditer 遍歷所有創意
    matches = re.finditer(pattern, final_message)

    for match in matches:
        # st.write(match)
        idea = match.group(1).strip()  # 捕获从短横线到 Originality 之间的内容
        originality = int(match.group(2))
        elaboration = int(match.group(3))
        fluency = int(match.group(4))
        flexibility = int(match.group(5))

        # 檢查是否符合篩選條件
        if originality >= originality_threshold and flexibility >= flexibility_threshold:
            # 將符合條件的創意加入列表
            ideas.append({
                "idea": idea,
                "scores": {
                    "Originality": originality,
                    "Elaboration": elaboration,
                    "Fluency": fluency,
                    "Flexibility": flexibility
                }
            })

    return final_message, originality_score, elaboration_score, fluency_score, flexibility_score, ideas



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

st.write("已經累積" + str(len(st.session_state.passed_ideas)) + "個創意")
if len(st.session_state.passed_ideas) >= 3:
    st.write(st.session_state.passed_ideas)
    st.write(st.session_state.full_scores)

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
        # 設定討論內容
        discussion_message = (
            f"這是第 {round_num} 輪討論。\n\n"
            f"上一輪的討論內容：\n\n{st.session_state.integrated_message}\n\n"
            f"針對原本討論內容進行延伸（提示：題目為 {question}）\n\n"
            f"以下是回應格式:\n\n"
            f"剛剛提到（創意內容），我覺得依據題目（怎麼樣），那其實也可以有（延伸創意）"
        )

    
    this_round_input = st.session_state.user_inputs.get(round_num, "")

    for agent_name, agent in agents.items():
        if st.session_state[f"round_{round_num}_completed"]:
            break

        # st.write("開頭")
        # st.write(st.session_state.messages)
        if agent_name in ["Convergence Judge", "Assistant"]:
            continue


        if agent_name == "Normal Assistant 1":
            if st.session_state[f"round_{round_num}_agent_states"][agent_name]:
                continue
            with st.chat_message("assistant"):
                st.markdown(discussion_message)
            this_round_input = st.chat_input(f"請輸入第 {st.session_state.round_num} 輪的想法：")

            # 處理用戶輸入，只針對當前輪次
            if this_round_input:
                st.session_state.messages.append({"role": "assistant", "content": discussion_message})

                # Display user message in chat message container
                with st.chat_message("user"):
                    st.markdown(this_round_input)
                # Add user message to chat history
                st.session_state.messages.append({"role": "user", "content": this_round_input})
                st.session_state[f"round_{round_num}_input_completed"] = True
                st.session_state.this_round_combined_responses[agent_name] = this_round_input
                st.session_state.user_inputs[round_num] = this_round_input
            else:
                # 等待輸入
                return False
        else:
            if st.session_state[f"round_{round_num}_agent_states"][agent_name]:
                continue
            response = await agent.a_initiate_chat(user_proxy, message=discussion_message, max_turns=1)
            response = response.chat_history[-1]["content"].strip()
            st.session_state.this_round_combined_responses[agent_name] = response
            # Display assistant response in chat message container
            with st.chat_message(agent_name):
                st.markdown(response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": agent_name, "content": response})
            mark_agent_completed(round_num, agent_name)

    # # 更新整合的歷史訊息
    # st.session_state.integrated_message = "\n\n".join([
    #     f"{msg['role']}: {msg['content']}" for msg in st.session_state.messages
    # ])


    if round_num == 0:
        # 檢查是否完成
        st.session_state.integrated_message, originality_score, elaboration_score, fluency_score, flexibility_score, ideas = await check_novelty_and_feasibility(0, "", st.session_state.this_round_combined_responses, if_zero_round=True)
    else:
        st.session_state.integrated_message, originality_score, elaboration_score, fluency_score, flexibility_score, ideas = await check_novelty_and_feasibility(round_num, st.session_state.integrated_message, st.session_state.this_round_combined_responses)
    
    st.session_state.messages.append({"role": "Convergence Judge", "content": st.session_state.integrated_message})
    st.session_state.full_scores.append({"round": round_num, "originality": originality_score, "elaboration": elaboration_score, "fluency": fluency_score, "flexibility": flexibility_score})

    # 將通過篩選的創意加入 passed_ideas 列表
    for idea in ideas:
        st.session_state.passed_ideas.append(idea)
    
    if len(st.session_state.passed_ideas) >= 3:
        st.write(st.session_state.passed_ideas)
        st.write(st.session_state.full_scores)
        return True
    
    # st.write("結束")
    # st.write(st.session_state.messages)

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


    # if not st.session_state[f"round_{round_num}_input_completed"]:
    #     current_input = st.chat_input(f"請輸入第 {st.session_state.round_num} 輪的想法：")
        
    #     if current_input:
    #         # 保存输入并重置状态
    #         st.session_state.user_inputs[st.session_state.round_num] = current_input
    #         with st.chat_message("user"):
    #             st.markdown(current_input)

    #     completed = asyncio.run(single_round_discussion(
    #         st.session_state.round_num, agents, user_proxy
    #     ))

    if completed:
        # 如果該輪完成，進入下一輪
        # st.write(f"已完成第 {st.session_state.round_num} 輪，進入第 {st.session_state.round_num + 1} 輪")
        st.session_state.round_num += 1
        # time.sleep(1)
        st.rerun()
