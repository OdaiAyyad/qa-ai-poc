import streamlit as st
from groq import Groq
import os
from dotenv import load_dotenv
import json
from datetime import datetime

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="QA AI Assistant",
    layout="wide"
)

# ---------------- GROQ CLIENT ----------------
load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# ---------------- SIDEBAR ----------------

st.sidebar.title("QA AI Assistant")

st.sidebar.markdown("## Investigation History")

try:
    with open("chat_history/history.json", "r", encoding="utf-8") as file:
        history = json.load(file)

        if not history:
            st.sidebar.write("No history yet.")

        for item in reversed(history):
            ticket_id = item.get("ticket", "Unknown ticket")
            timestamp = item.get("timestamp", "")
            question = item.get("question", "No question")
            response = item.get("response", "No response saved.")
            question_preview = question

            if len(question_preview) > 45:
                question_preview = f"{question_preview[:45]}..."

            with st.sidebar.expander(f"{ticket_id} - {question_preview}"):
                if timestamp:
                    st.caption(timestamp)

                st.markdown("**Question**")
                st.write(question)

                st.markdown("**AI Analysis**")
                st.markdown(response)

except:
    st.sidebar.write("No history yet.")
    st.sidebar.markdown("- Scholarship")
    st.sidebar.markdown("- Orders")
    st.sidebar.markdown("- Discounts")

# ---------------- MAIN UI ----------------

st.image("banner.png", use_container_width=True)

st.title("QA AI Impact Analysis Assistant")

st.markdown(
    "Analyze Jira tickets and identify affected areas, business logic, and regression risks."
)

with st.expander("How QA should search"):
    st.markdown(
        """
        1. Select the testing environment.
        2. Enter the Jira ticket ID, for example `STF-7063`.
        3. Ask one focused QA investigation question.
        4. Use questions about regression, DB checks, APIs, validations, affected areas, or risky dependencies.

        Example questions:
        - What should I regression test in this ticket?
        - Which DB tables or fields should I verify?
        - What hidden dependencies could be affected?
        - What API or business rules should I investigate?
        """
    )

col1, col2 = st.columns(2)

with col1:
    environment = st.selectbox(
        "Environment",
        ["Preprod", "Production", "Staging"]
    )

with col2:
    ticket = st.text_input("Ticket ID")

question = st.text_area(
    "Ask your QA question",
    placeholder="Example: What should I regression test in STF-7063?"
)

# ---------------- BUTTON ----------------

if st.button("Analyze Impact"):

    ticket_content = ""

    try:
        ticket = ticket.strip().upper()

        with open(f"tickets/{ticket}.txt", "r", encoding="utf-8") as file:
            ticket_content = file.read()
    except:
        ticket_content = "Ticket not found."

    # Empty question validation
    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    prompt = f"""
    You are an AI QA investigation assistant.

    Your role is NOT to summarize tickets.

    Your role is to help QA engineers identify:
    - impacted areas
    - affected modules
    - possible database relations
    - important validations
    - risky logic dependencies

    Environment:
    {environment}

    Ticket ID:
    {ticket}

    Ticket Content:
    {ticket_content}

    User Question:
    {question}

    IMPORTANT RULES:
    - Keep answers concise and investigation-focused
    - Avoid repeating ticket details
    - Use bullet points
    - Focus on actionable QA insights
    - Infer likely DB tables/columns if applicable
    - Mention possible hidden dependencies
    - Think like a senior QA investigator

    VALIDATION RULES:

    - If the question is unrelated to QA investigation, politely refuse.
    - If the question is unrelated to the provided ticket context, explain that the investigation should stay related to the selected ticket.
    - Do NOT answer general casual questions.
    - Only answer questions related to:
    - testing
    - regression
    - affected areas
    - business logic
    - DB impact
    - APIs
    - validations
    - dependencies
    - investigations

    Response Format:

    ## Affected Areas
    - ...

    ## Important DB Checks
    - ...

    ## Risky Dependencies
    - ...

    ## Suggested Investigation
    - ...

    ## Regression Focus
    - ...
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    st.success("Analysis Generated Successfully")

    st.markdown("## AI Analysis")

    ai_response = response.choices[0].message.content

    chat_entry = {
    "timestamp": str(datetime.now()),
    "ticket": ticket,
    "question": question,
    "response": ai_response
}

    history_file = "chat_history/history.json"

    try:
        with open(history_file, "r") as file:
            history = json.load(file)
    except:
        history = []

    history.append(chat_entry)

    with open(history_file, "w") as file:
        json.dump(history, file, indent=4)

    st.markdown(ai_response)
