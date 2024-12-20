import streamlit as st
from utils import QUICK_SEARCH_PROMPT, LENGTHY_SEARCH_PROMPT, INITIAL_DECISION_PROMPT
from utils import ask_llm
from Organizer import Organizer
import asyncio
import time, random
from streamlit_image_gallery import streamlit_image_gallery

organizer = Organizer()

def load_css():
    st.markdown("""
    <style>
        /* Main background and text colors */
        .stApp {
            background-color: #0E1117;
            color: #E0E0E0;
        }
        
        /* Header styling */
        .stHeader {
            background-color: #1E1E1E;
            padding: 2rem 0;
            border-bottom: 1px solid #2D2D2D;
        }
        
        /* Search input styling */
        .stTextInput > div > div > input {
            background-color: #262730;
            color: #FFFFFF;
            border: 1px solid #4B4B4B;
            border-radius: 8px;
            padding: 12px 20px;
        }
        
        /* Button styling */
        .stButton > button {
            background-color: #4C4CFF;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0.5rem 1rem;
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            background-color: #3939FF;
            box-shadow: 0 4px 12px rgba(76, 76, 255, 0.3);
        }
        
        /* Secondary button */
        .stButton > button[kind="secondary"] {
            background-color: #2D2D2D;
            border: 1px solid #4B4B4B;
        }
        
        .stButton > button[kind="secondary"]:hover {
            background-color: #3D3D3D;
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background-color: #1E1E1E;
            border: 1px solid #2D2D2D;
            border-radius: 6px;
        }
        
        /* JSON display */
        .stJson {
            background-color: #262730 !important;
            border: 1px solid #4B4B4B !important;
            border-radius: 6px;
        }
        
        /* Spinner */
        .stSpinner > div {
            border-color: #4C4CFF transparent transparent !important;
        }
        
        /* Checkbox */
        .stCheckbox > label {
            color: #E0E0E0 !important;
        }
        
        /* Image gallery */
        .image-gallery {
            background-color: #1E1E1E;
            border-radius: 8px;
            padding: 1rem;
        }
        
        /* Markdown text */
        .stMarkdown {
            color: #E0E0E0;
        }
    </style>
    """, unsafe_allow_html=True)

async def main():
    st.set_page_config(layout="centered", page_title="Search-With-GPT")
    load_css()
    st.session_state.SearchEngineStatus = False
    st.session_state.Decision = False
    st.session_state.crawl_status = False
    st.session_state.ready_for_extraction = False
    st.session_state.answer = False
    st.session_state.will_search_status = False
    st.session_state.search_update = False
    

    if "search_query" not in st.session_state:
        st.session_state.search_query = ""

    # LANDING PAGE
    st.header("Search-With-GPT")

    #Search Bar
    st.session_state.search_query = st.text_input("", placeholder="Search Query Here...", key="top_search")


    # Search button, toogle button
    Search, toogle, reset, _ = st.columns([0.1,0.1,0.1,20])
    with Search:
        if st.button("Search", type="primary"):
            if st.session_state.SearchEngineStatus:
                st.session_state.SearchEngineStatus = False
                st.session_state.Decision = False
                st.session_state.crawl_status = False
                st.session_state.ready_for_extraction = False
                st.session_state.answer = False
                st.session_state.will_search_status = False
                st.session_state.search_update = False
                time.sleep(2)

            #Checking if Internet Search is required
            with st.spinner("Deciding If Internet Search is Necessary"):
                query = INITIAL_DECISION_PROMPT+st.session_state.search_query
                data = ask_llm(query=query, model="Meta-Llama-3.1-405B-Instruct", JSON=True, api_key= organizer.get_key())
                if data['status'] == 'success':
                    st.session_state.answer = data['answer']
                else:
                    st.session_state.search_query = data['query']
                    st.session_state.search_update = True

    #Displaying Updated Search Query               
    if st.session_state.search_update == True:
        with st.expander("Updated Search Query"):
            st.json({"Search_Query": st.session_state.search_query})
            st.session_state.will_search_status = True

    if st.session_state.will_search_status == True:
        with st.spinner('Searching The Internet...'):
            #Searching The Internet
            web_search_results = organizer.search_internet(query=st.session_state.search_query)
            st.session_state.SearchEngineStatus = True
    
    #Updating Internet Data
    if st.session_state.SearchEngineStatus:
        with st.expander("Data from the internet"):
            st.json(web_search_results['text'])
            #Quick Search
            if st.session_state.Searching_mode == "quick_search":
                with st.spinner('Deciding If Answer can be Constructed or Need more data...'):
                    temp_ans = organizer.get_filtered_urls(all_urls=web_search_results['text'], prompt=QUICK_SEARCH_PROMPT, query= st.session_state.search_query)
                    st.session_state.Decision = True
                    
            #Research Mode
            if st.session_state.Searching_mode == "research":
                with st.spinner('Filtering Important urls to CRAWL...'):
                    temp_ans = organizer.get_filtered_urls(all_urls=web_search_results['text'], prompt=LENGTHY_SEARCH_PROMPT, query= st.session_state.search_query)
                    st.session_state.Decision = True
                    

    #Updating Quick Search Data
    if st.session_state.Decision == True:
        if not isinstance(temp_ans, str):
            # Meaning it's a list of urls
            if len(temp_ans) == 1:
                with st.expander("Decided To Crawl This Wikipedia for more context."):
                    st.json({"Filtered_Urls":temp_ans})
                    st.session_state.crawl_status = True
            else:
                with st.expander("Decided To Crawl These sites for more context."):
                    st.json({"Filtered_Urls":temp_ans})
                    st.session_state.crawl_status = True
            
        else:
            #Meaning It's the answer
            with st.spinner('Structuring The Answer...'):
                st.session_state.answer = organizer.fine_tune_ans(query = st.session_state.search_query, answer = temp_ans)

    if st.session_state.crawl_status == True:
        with st.spinner('Crawling and Collecting Data...'):
            crawl_results = await organizer.process_url(temp_ans)
            with st.expander("Crawling completed and Data Collected..."):
                st.json(crawl_results)
                st.session_state.ready_for_extraction = True


    if st.session_state.ready_for_extraction == True:
        with st.spinner('Summerizing and Generating Report (30 sec to several minutes)...'):
            processed_data = await organizer.multi_text_processor(st.session_state.search_query)
            st.session_state.answer = processed_data
            # st.markdown(processed_data)
                
    if st.session_state.answer:
        #4 urls & 1 more button

        st.markdown(st.session_state.answer)

        if st.session_state.SearchEngineStatus == True:
            if web_search_results['video'] != []:
                st.subheader("Media Results")
                r1 = [{"src":i['image'], "title":i['url']} for i in web_search_results['video']]
                r2 = [{"src":i['image_url'], "title":i['page_url']} for i in web_search_results['image']]
                image = random.sample(r1, min(len(r1),15)) + random.sample(r2, min(len(r2),15))
                random.shuffle(image)
                streamlit_image_gallery(images=image, max_rows=2, max_width=800, max_cols=3)
                









    with toogle:
        status = st.checkbox("Research Mode", help="Takes 35sec - Several Minutes")
        if status:
            st.session_state.Searching_mode = "research"
        if not status:
            st.session_state.Searching_mode = "quick_search"

    with reset:
        if st.button("Ask Another", type = "secondary"):
            st.rerun()
    















if __name__ == "__main__":
    asyncio.run(main())


