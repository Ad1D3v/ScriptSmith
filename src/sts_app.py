import streamlit as st

# Import Custom Module
import sts_core as stc

##############Interface##################

# Define Page Setup
st.set_page_config(page_title="ScriptSmith", page_icon="🔨")
st.title("ScriptSmith")
st.subheader("Smithing Scripts, Made Effortless!")

# Define Interface Elements
sts_query = st.text_area("Enter your query and let ScriptSmith forge your code!")
sts_process = st.button("Smith It")

# Handle User Input
if sts_process:
    if sts_query is None or sts_query == "":
        st.info("Nothing to Work on...⚠️⚠️⚠️")

    else:
        with st.spinner("Smithing your script...🔄🔄🔄"):
            result = stc.generate_result(sts_query, st.session_state)
        st.info("Here's your Script...✅✅✅")
        st.markdown(result)
