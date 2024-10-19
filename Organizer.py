import requests
import asyncio
import random
from search_agent import Research_Tool
from utils import ask_llm
from utils import fetch_videos, perform_image_search
from utils import SUMMRIZATION_PROMPT
from utils import split_corpus
from utils import REPORT_GENERATION_PROMPT, SHORT_ANSWER_FINE_TUNING_PROMPT
from utils import is_article, is_image_url
from dotenv import load_dotenv
import os
load_dotenv()

class Organizer:
    def __init__(self):
        self.researcher = Research_Tool()
        self.session = requests.session()
        self.keys = os.environ.get("SAMBANOVA_KEYS").split()
        self.all_Images = []
        self.all_links = []
        self.full_text = ""

    def get_filtered_urls(self, all_urls, prompt, query = None):
        # print(query)
        # all_urls = self.researcher.search(query, random.randint(10, 15))
        # print(all_urls)
        self.all_urls = [i['url'] for i in all_urls]
        
        urls = ask_llm(query=str(all_urls) + prompt + query, JSON=True, model='Meta-Llama-3.1-405B-Instruct', api_key=random.choice(self.keys))
        # print(urls)
        try:
            if urls.get('status') == 'pending':
                if urls.get('urls'):
                    filtered_urls = [i for i in urls['urls'] if "wikipedia.org/wiki/" in i] \
                                    if "wikipedia.org/wiki/" in str(urls) else urls['urls']
                    # print("filtered_urls: ",filtered_urls)
                    return filtered_urls if filtered_urls else []  
                else:
                    return []  
            elif urls.get('status') == 'code':
                ans = ask_llm(query = query, model = 'Meta-Llama-3.1-405B-Instruct', api_key=random.choice(self.keys))
                return ans
            else:
                # print("url_answer", urls.get('answer'))
                return urls.get('answer') or []  
        except Exception as e:
            print("Exception occurred:", str(e))
            print("except", urls)
            return [] 


    async def summerize(self, data, prompt, model='Meta-Llama-3.1-8B-Instruct', show = False):
        text, query, key = data
        # if show:
        #     print(data)
        if '{"summery": list({"heading": description}, ...), "Images": list({"url": str, "description": str}, ...), "links": list({"url": str, "description": str}, ...)}' in prompt:
            prompt = text+ "\n"+ prompt + "\n" + query
        else:
            prompt = prompt.format(data = text, query = query)
        try:
            data = await asyncio.to_thread(ask_llm, query=prompt, model=model , JSON=False, api_key=key)
            if "[status: failed]" in data:
                return ""
            # print("-"*150,'\n',data,'\n',"-"*150)
            return str(data)
        except:
            return ""

    async def Processor(self, url):
        data = self.researcher.scrape_page(url, Get_Soup=True)
        # print(len(data))
        if data:
            raw, json_response = data
            self.full_text += raw
            return json_response
    
    async def process_text_corpus(self, text_corpus, query, prompt, model = "Meta-Llama-3.1-8B-Instruct"):
        # print(text_corpus)
        chunked_text = split_corpus(text_corpus, max_words=1000)
        # print(len(chunked_text))
        while len(chunked_text) > 1:  
            # print("Here We Go Again")
            text_chunk_list = [(chunk, query, self.keys[m % len(self.keys)]) for m, chunk in enumerate(chunked_text)]
            tasks = [self.summerize(chunk, prompt=prompt, model = model) for chunk in text_chunk_list]
            results = await asyncio.gather(*tasks)
            
            text_corpus = "\n\n".join(results)
            # print(len(text_corpus))  
            chunked_text = split_corpus(text_corpus, max_words=1000)
            # print(len(chunked_text)) 
        
        return text_corpus  
    
    async def mass_check(self, list_of_data, function):
        if function == 'image':
            tasks = [is_image_url(i) for i in list_of_data]

        if function == 'link':
            tasks = [is_article(i) for i in list_of_data]

        filtered_data = await asyncio.gather(*tasks)
        return [i for i in filtered_data if i != None]

    async def process_url(self, filtered_urls):
        tasks = [self.Processor(url) for url in filtered_urls]
        list_of_json = await asyncio.gather(*tasks)

        return {"Crawl Results": list_of_json}

    async def multi_text_processor(self, query):
        text_image_links = await self.process_text_corpus(text_corpus= self.full_text, query = query, prompt = SUMMRIZATION_PROMPT, model='Meta-Llama-3.1-405B-Instruct')
        # print(text_image_links)
        final_report = ask_llm(query= REPORT_GENERATION_PROMPT.format(data = str(text_image_links), question = query), model="Meta-Llama-3.1-405B-Instruct", api_key=random.choice(self.keys))
        # print(final_report)
        return final_report

    def fine_tune_ans(self, query, answer):
        data = ask_llm(query= SHORT_ANSWER_FINE_TUNING_PROMPT.format(query = query, answer = answer), model="Meta-Llama-3.1-405B-Instruct", api_key=random.choice(self.keys))
        print(data)
        return data
    
    def search_internet(self, query):
        text_data = self.researcher.search(query, random.randint(10, 15))
        image_data = perform_image_search(query=query)
        video_data = fetch_videos(query, random.randint(10, 15))

        return {"text":text_data, "image": image_data, "video": video_data}

    def get_key(self):
        return random.choice(self.keys)











    async def search(self, filtered_urls, query):
        tasks = [self.Processor(url) for url in filtered_urls]
        list_of_chunks = await asyncio.gather(*tasks)
        alltext = "\n\n".join(list_of_chunks)

        summery = await self.process_text_corpus(alltext, query, prompt=SUMMRIZATION_PROMPT)
        summery = summery.strip('\n').strip(" ")
        # print(self.all_Images)
        # print(self.all_links)
        # print(self.all_urls)
        # print(len(final_data_list))
        # print(final_data_list)
        # final_data_list = "\n\n".join(final_data_list)
        # final_data = await self.summerize((final_data_list, query, random.choice(self.keys)), bullet=False)
        return summery


    
