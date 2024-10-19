import re
import openai
import json
from duckduckgo_search import DDGS
import aiohttp
from bs4 import BeautifulSoup
import jsbeautifier
from urllib.parse import urlparse, urljoin, quote_plus
from typing import Dict, Any, List
import requests
from dotenv import load_dotenv
import os
load_dotenv()

DEBUG = False

def log_debug(message):
    if DEBUG:
        print(f"DEBUG: {message}")



headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,/;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }


def extract_query(text: str) -> str:
    pattern = r"```(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches[0] if matches else text

def extract_image_json(text: str) -> str:
    pattern = r"var m = {(.*?)var a = m;"
    matches = re.findall(pattern, text, re.DOTALL)
    data = matches[0] if matches else text
    try:
        data = json.loads("{" + data.strip()[:-1])
    except Exception as e:
        print(e)
        print(data)
    return data

def ask_llm(query, api_key, model = "Meta-Llama-3.1-70B-Instruct", JSON = False):
    for i in range(5):
        SambaNova_Client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.sambanova.ai/v1",
            )
        # print(query)
        response = SambaNova_Client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": "You're a advance data analyst."},{"role":"user","content":query}],
            temperature =  0.1,
            top_p = 0.1,
        )
        ans = response.choices[0].message.content
        # print(ans)
        if not JSON:
            # print(model)
            return ans
        try:
            data = json.loads(extract_query(ans))
            return data
        except Exception as e:
            print(e)
            print(response.choices[0].message.content)


def perform_image_search(query: str) -> List[Dict[str, Any]]:
    encoded_query = quote_plus(query)
    search_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch"
    log_debug(f"Search URL: {search_url}")
    
    try:
        log_debug("Sending GET request to Google")
        response = requests.get(search_url, headers=headers, timeout=5)
        log_debug(f"Response status code: {response.status_code}")
        response.raise_for_status()
        
        log_debug("Parsing HTML with BeautifulSoup")
        soup = BeautifulSoup(response.text, 'html.parser')

        for script in soup.find_all('script'):
            if script.string:  
                pretty_js = jsbeautifier.beautify(script.string)
                script.string.replace_with(pretty_js)  

        pretty_html_with_pretty_js = soup.prettify()
        
        search_results = []
        image_data_json = extract_image_json(pretty_html_with_pretty_js)
        filtered_image_data_list = [image_data_json[i] for i in image_data_json if len(image_data_json[i]) == 8 and "https://" in str(image_data_json[i])]
        for i in filtered_image_data_list:
            dj = {}
            dj['image_url'] = i[1][3][0]
            i = i[1][-1]
            for j in i:
                if "https://" in str(i[j]):
                    for m in i[j]:
                        if m and "https://" in m:
                            dj['description'] = i[j][i[j].index(m)+1]
                            dj['page_url'] = m
                            search_results.append(dj)
                            break
        
        log_debug(f"Successfully retrieved {len(search_results)} search results for query: {query}")
        return search_results
    except requests.RequestException as e:
        log_debug(f"Error performing search: {str(e)}")
        return []

def fetch_videos(query, no_of_results):
    results = DDGS().videos(
        keywords=query,
        region="wt-wt",
        safesearch="off",
        timelimit="w",
        resolution="high",
        duration="medium",
        max_results=no_of_results,
    )
    return [{"url": i['content'], "image": [m for m in [i['images']['large'], i['images']['medium'], i['images']['small']] if m != ''][0] } for i in results]

def split_corpus(corpus, max_words=4000):
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!|\n)\s+', corpus.strip())
    current_list = []
    word_count = 0
    all_splits = []
    for sentence in sentences:
        words_in_sentence = sentence.split()
        sentence_word_count = len(words_in_sentence)
        if word_count + sentence_word_count <= max_words:
            current_list.append(sentence)
            word_count += sentence_word_count
        else:
            all_splits.append(current_list)
            current_list = [sentence]
            word_count = sentence_word_count
    if current_list:
        all_splits.append(current_list)

    return [" ".join(i) for i in all_splits]

async def is_image_url(data):
    url = data['src']
    if url.startswith('//'):
        url = "https:"+url
        data['src'] = url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                # Check if the content type is an image
                if response.headers.get("Content-Type").startswith("image"):
                    return data
                else:
                    return None
    except Exception as e:
        print(f"Error checking URL: {e}")
        return None

async def is_article(data):
    url = data['href']
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                content = await response.text()
                if "<article" in content:
                    return data
                else:
                    return None
    
    except Exception as e:
        print(f"Error fetching or parsing URL: {e}")
        return None


QUICK_SEARCH_PROMPT = """
                            Answer this question in this format:
                            {"status":str, "answer": str, "urls": list(str)}
                            YOU MUST PUT THE JSON ANSWER WITHIN TWO ```

                            if you can answer the question with the provided context, set status to 'success' else it will be as 'pending'
                            if you can't answer the question keep answer as empty.
                            if you are not able to answer with the provided context return a list of urls from the provided ones that you would like to visit for more data. return a list of upto 5 urls.
                            if you are able to answer from the provide context keep the urls empty.
                            if no data provided return a empty list of urls with status 'pending'
                            NOTE: YOU MUST SET THE status to 'code' IF YOURE ASKED TO GENERATE ANY CODE IN THE QUESTION. DO NOT GENERATE ANY CODE EVEN IF YOU KNOW THE ANSWER.
                            Question: 
                        """

LENGTHY_SEARCH_PROMPT = """
                            Answer this question in this format:
                            {"status":"pending", "urls": list(str)}
                            YOU MUST PUT THE JSON ANSWER WITHIN TWO ```

                            Return a list of upto 5 urls from the provided ones that you would like to visit for more Context to answer the following question.
                            If provided less than 5 urls return all the urls as a list
                            Question:

                        """

SHORT_ANSWER_FINE_TUNING_PROMPT = """
                            Question:
                            {query}
                            Answer:
                            {answer}

                            You have been Provided with a question and it's answer. Your job is to make the answer more Humanlike.
                            Please Generate the answer in Markdown Format in a Humanlike way and Professional.
                            NOTE: IF THERE IS ANY CODE INVOLVED THE ANSWER YOU MUST PUT THE CODE BETWEEN TWO ```
                            IF NO CODE IS INVOLVED DO NOT MENTION ABOUT ANY CODES
                            """
REPORT_GENERATION_PROMPT = """
                            {data}
                            You have been provided with some structured data related to this question:
                            {question}

                            your job is to unify them and create a Final report that consists of all three of these in MARKDOWN format.
                            Take the images and the link urls from the provided urls only and don't make them up yourself.
                            Regardless of whatever in the context you will make the report only for the provided question.

                            NOTE: PUT THE IMAGE URLS IN A WAY SO THAT THEY CAN BE DISPLAYED DIRETLY ON THE MARKDOWN.
                                  PUT THE REFERENCE AS YOU SEE FIT.
                                  MAKE THE REPORT LOOK AS HUMAN LIKE AS POSSIBLE.
                                  YOU MAY USE YOUR OWN KNOWLEDGE TO ADD SOMETHING TO THE REPORT, MAINTAINING THE QUALITY.
                                  MAKE THE REPORT DESCRIPTIVE.
                            """


SUMMRIZATION_PROMPT = """Generate me a report within 500 words in JSON format using this schema:
            {"summery": list({"heading": description}, ...), "Images": list({"url": str, "description": str}, ...), "links": list({"url": str, "description": str}, ...)}
            The Images and the Links Must be Present in the context. if no Image or Link found keep the list empty.
            DO NOT USE YOUR KNOWLEDGE TO CONSTRUCT THE ANSWER. USE ONLY WHAT IS PROVIDED IN THE CONTEXT.
            add only the image and links that are strongly related to the report topic.
            in the summery describe the Report topic based on the provided context briefly within 800 words.
            Report Topic:
            """


INITIAL_DECISION_PROMPT = """You will be provided a question.
            Construct the answer in JSON format strictly using this schema:
            {"status": str, "answer": str}
            and Return {"status":"success", "answer": answer} if the question is greetings or it does not require a search on the internet to answer.
            Return {"status": "search", "query": search query} if it require to search the internet or if the query asks to generate any kind of code.
            Question:
            """